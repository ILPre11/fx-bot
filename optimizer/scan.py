"""
Scanner multi-coppia: cerca dove c'è un edge VERO e STABILE.

Per ogni coppia e ogni modulo (Trend, MeanRev, Vol, Asia), con parametri DEFAULT
(zero ottimizzazione = zero overfitting), misura:
  - performance complessiva (Total R, PF, n trade)
  - quanti anni su N sono positivi (stabilità nel tempo)
  - performance negli ULTIMI 2 ANNI (proxy del "funziona ancora oggi?")

Poi ordina le combinazioni (coppia, modulo) per robustezza, così si vede subito
dove vale la pena approfondire.

Uso:
  python -m optimizer.scan
  python -m optimizer.scan --symbols EURJPY,GBPJPY,USDJPY --years 8
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

DEFAULT_SYMBOLS = ["EURJPY", "USDJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY",
                   "EURUSD", "GBPUSD", "AUDUSD", "USDCHF", "USDCAD", "NZDUSD", "EURGBP"]


def stat(pnls):
    if not pnls:
        return 0, 0.0, 0.0
    gp = sum(p for p in pnls if p > 0)
    gl = -sum(p for p in pnls if p < 0)
    pf = gp / gl if gl > 0 else 9.99
    return len(pnls), round(sum(pnls), 1), round(min(pf, 9.99), 2)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Scanner multi-coppia per trovare l'edge")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--years", type=float, default=8.0)
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    h1_bars = int(args.years * 252 * 24)

    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")

    rows = []
    for sym in symbols:
        try:
            h1 = client.rates(sym, "H1", h1_bars)
            h4 = client.rates(sym, "H4", h1_bars // 4)
        except Exception:
            print(f"[{sym}] non disponibile, salto.")
            continue
        if h1 is None or len(h1) < 5000:
            print(f"[{sym}] dati insufficienti ({0 if h1 is None else len(h1)} barre), salto.")
            continue
        pc = fb.precompute(h1, h4)
        times = pd.DatetimeIndex(h1["time"].to_numpy())
        years = sorted(set(times.year))
        recent_cut = int(len(h1) - 2 * 252 * 24)

        for mod_id, name in MODULES:
            trades = fb.collect_trades(pc, {}, modules=(mod_id,))
            allp = [t["pnl"] for t in trades]
            n, r, pf = stat(allp)
            rec = [t["pnl"] for t in trades if t["idx"] >= recent_cut]
            rn, rr_, rpf = stat(rec)
            pos_years = sum(1 for y in years
                            if sum(t["pnl"] for t in trades if times[t["idx"]].year == y) > 0)
            rows.append({
                "sym": sym, "mod": name, "n": n, "r": r, "pf": pf,
                "pos": pos_years, "ny": len(years),
                "rn": rn, "rr": rr_, "rpf": rpf,
            })
        print(f"[{sym}] fatto ({times[0].date()} -> {times[-1].date()}).")
    client.disconnect()

    # punteggio robustezza: premia edge recente positivo + stabilità storica
    def score(row):
        s = row["rr"]                       # profitto recente (R)
        if row["rpf"] >= 1.3 and row["rn"] >= 10:
            s += 20                          # bonus: edge recente solido
        s += (row["pos"] / max(1, row["ny"])) * 15  # bonus stabilità storica
        if row["r"] <= 0:
            s -= 20                          # penalità: storia complessiva negativa
        return s

    rows.sort(key=score, reverse=True)

    print("\n" + "=" * 92)
    print("CLASSIFICA (default params, ordinata per robustezza: edge recente + stabilità)")
    print("=" * 92)
    print(f"{'COPPIA':<8} {'MOD':<8} | {'TUTTA STORIA':^22} | {'ULTIMI 2 ANNI':^20} | anni+")
    print(f"{'':8} {'':8} | {'tr':>5} {'R':>7} {'PF':>5}     | {'tr':>4} {'R':>6} {'PF':>5}  |")
    print("-" * 92)
    for row in rows:
        flag = "  <<<" if (row["rpf"] >= 1.3 and row["rn"] >= 10 and row["pos"] >= row["ny"] * 0.6) else ""
        print(f"{row['sym']:<8} {row['mod']:<8} | {row['n']:>5} {row['r']:>7.1f} {row['pf']:>5.2f}     "
              f"| {row['rn']:>4} {row['rr']:>6.1f} {row['rpf']:>5.2f}  | {row['pos']}/{row['ny']}{flag}")

    print("\n<<< = candidati robusti (PF recente >=1.3, >=10 trade recenti, >=60% anni positivi)")


if __name__ == "__main__":
    main()
