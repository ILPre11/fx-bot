"""
Analisi MODULO-PER-MODULO e per REGIME su una coppia, con parametri DEFAULT.

Scopo: invece di ottimizzare (rischio overfitting), capire quale dei 4 moduli
(Trend, MeanRev, VolBreakout, Asia) ha un edge VERO e STABILE nel tempo, e in
quali condizioni di mercato (trend vs range). Usa i parametri default => zero
gradi di libertà adattati ai dati => risultato onesto e generalizzabile.

Mostra, per ciascun modulo:
  - performance complessiva su tutta la storia
  - performance ANNO PER ANNO (stabilità nel tempo)
  - performance per REGIME (ADX H4: trending vs range)

Uso:
  python -m optimizer.module_analysis --symbol EURJPY --years 8
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb

MODULES = [(fb.MODULE_TREND, "TREND"), (fb.MODULE_MEANREV, "MEANREV"),
           (fb.MODULE_VOL, "VOL"), (fb.MODULE_ASIA, "ASIA")]

ADX_TREND = 25.0   # H4 ADX >= -> mercato in trend
ADX_RANGE = 18.0   # H4 ADX <  -> mercato in range


def stat(pnls: list[float]) -> tuple[int, float, float]:
    """(num_trade, total_r, profit_factor)."""
    if not pnls:
        return 0, 0.0, 0.0
    gp = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    pf = gp / gl if gl > 0 else float("inf")
    return len(pnls), round(sum(pnls), 1), (round(pf, 2) if pf != float("inf") else 9.99)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Analisi modulo-per-modulo e per regime")
    ap.add_argument("--symbol", default=config.PAIR)
    ap.add_argument("--years", type=float, default=8.0)
    args = ap.parse_args()

    h1_bars = int(args.years * 252 * 24)
    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")
    h1 = client.rates(args.symbol, "H1", h1_bars)
    h4 = client.rates(args.symbol, "H4", h1_bars // 4)
    client.disconnect()

    pc = fb.precompute(h1, h4)  # parametri/periodi DEFAULT
    times = pd.DatetimeIndex(h1["time"].to_numpy())
    years = sorted(set(times.year))

    print(f"=== ANALISI MODULI {args.symbol} (parametri DEFAULT, no ottimizzazione) ===")
    print(f"Storia: {times[0].date()} -> {times[-1].date()} ({len(h1)} barre H1)")
    print(f"Regime via ADX H4: TREND>={ADX_TREND:.0f}, RANGE<{ADX_RANGE:.0f}\n")

    # indice di confine per "ultimi 2 anni" (proxy del live di oggi)
    recent_cut = int(len(h1) - 2 * 252 * 24)

    for mod_id, name in MODULES:
        trades = fb.collect_trades(pc, {}, modules=(mod_id,))
        all_pnls = [t["pnl"] for t in trades]
        n, r, pf = stat(all_pnls)

        recent = [t["pnl"] for t in trades if t["idx"] >= recent_cut]
        rn, rr_, rpf = stat(recent)

        print(f"########## {name} ##########")
        print(f"  TUTTA LA STORIA : trade={n:>4}  Total R={r:>7.1f}  PF={pf}")
        print(f"  ULTIMI 2 ANNI   : trade={rn:>4}  Total R={rr_:>7.1f}  PF={rpf}   <- proxy live oggi")

        # --- per anno ---
        print("  Anno  :  " + "  ".join(f"{y}" for y in years))
        per_year_r = []
        for y in years:
            pnls_y = [t["pnl"] for t in trades if times[t["idx"]].year == y]
            _, ry, _ = stat(pnls_y)
            per_year_r.append(ry)
        print("  TotalR:  " + "  ".join(f"{ry:>4.0f}" for ry in per_year_r))
        pos_years = sum(1 for ry in per_year_r if ry > 0)
        print(f"  -> anni positivi: {pos_years}/{len(years)}")

        # --- per regime (ADX H4 all'ingresso) ---
        buckets = {"TREND": [], "RANGE": [], "MID": []}
        for t in trades:
            adx4 = pc.h4_adx[t["m"] - 1]
            if adx4 != adx4:
                continue
            key = "TREND" if adx4 >= ADX_TREND else ("RANGE" if adx4 < ADX_RANGE else "MID")
            buckets[key].append(t["pnl"])
        print("  Regime:")
        for key in ("TREND", "MID", "RANGE"):
            bn, br, bpf = stat(buckets[key])
            print(f"     {key:<6}: trade={bn:>4}  Total R={br:>7.1f}  PF={bpf}")
        print()


if __name__ == "__main__":
    main()
