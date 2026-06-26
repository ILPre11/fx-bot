"""
Lancia il backtest su tutte le combo (module, symbol) e aggiorna results.json.

Uso standalone (richiede MT5 aperto e connesso):
  python -m optimizer.run_optimizer

Oppure invocato automaticamente da main.py --live ogni 24h a mezzanotte.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# assicura che la root del progetto sia in path se eseguito da linea di comando
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from forex_bot.strategies.fx_multi_regime import (
    MODULE_TREND, MODULE_ASIA, MODULE_MEANREV, MODULE_VOL,
)
from optimizer.backtest import run, compute_stats
from optimizer.selector import print_table, save_results, select_active

MODULES = {
    MODULE_TREND: "TREND",
    MODULE_MEANREV: "MEANREV",
    MODULE_VOL: "VOL",
    MODULE_ASIA: "ASIA",
}

BACKTEST_H1_BARS = 15000   # ~2,4 anni di H1 (campione confrontabile coi backtest EA)


def run_optimizer(client) -> dict[int, list[str]]:
    """Testa tutte le combo e ritorna il mapping module→symbols attivi."""
    all_results: list[dict] = []
    symbols = config.SYMBOLS

    print(f"\n=== Optimizer avviato [{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC] ===")
    print(f"Simboli: {symbols}  |  Barre H1: {BACKTEST_H1_BARS}\n")

    for symbol in symbols:
        print(f"[{symbol}] scarico dati...", end=" ", flush=True)
        try:
            h1 = client.rates(symbol, "H1", BACKTEST_H1_BARS)
            h4 = client.rates(symbol, "H4", BACKTEST_H1_BARS // 4)
            print(f"OK ({len(h1)} barre H1, {len(h4)} H4)")
        except Exception as exc:
            print(f"ERRORE: {exc}")
            continue

        for mod_id, mod_name in MODULES.items():
            print(f"  {mod_name}×{symbol}... ", end="", flush=True)
            try:
                trades = run(symbol, h1, h4, mod_id)
                stats = compute_stats(trades)
            except Exception as exc:
                print(f"ERRORE: {exc}")
                continue

            stats["module_id"] = mod_id
            stats["module_name"] = mod_name
            stats["symbol"] = symbol
            stats["timestamp"] = datetime.utcnow().isoformat()
            all_results.append(stats)
            print(
                f"trade={stats['num_trades']:>3}  PF={stats['pf']:.2f}  "
                f"WR={stats['win_rate']:.0%}  Sharpe={stats['sharpe']:.2f}"
            )

    print()
    print_table(all_results)
    save_results(all_results)

    active = select_active(all_results)
    if active:
        print(f"\n[Optimizer] Combo ATTIVE (PF≥1.5, trade≥15): {active}")
    else:
        print("\n[Optimizer] Nessuna combo supera i criteri: bot in standby.")
    return active


if __name__ == "__main__":
    try:
        with Mt5Client(
            config.MT5_LOGIN, config.MT5_PASSWORD,
            config.MT5_SERVER, config.MT5_PATH,
        ) as client:
            run_optimizer(client)
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")
