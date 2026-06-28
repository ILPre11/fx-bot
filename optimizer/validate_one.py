"""
Validazione APPROFONDITA di UNA singola strategia (coppia + modulo), parametri DEFAULT.

Non ottimizza nulla. Risponde a: "questo edge è ROBUSTO o un colpo di fortuna?"
con tre check:
  1. PROFILO DI RISCHIO reale (full history): equity in R, max drawdown, serie di
     perdite più lunga, payoff, win rate, long vs short, performance anno per anno.
  2. SENSIBILITÀ AI PARAMETRI: varia ogni parametro chiave di +/- alcuni step e
     verifica che la strategia resti positiva su un INTERVALLO (= plateau = edge
     vero) invece di funzionare solo in un punto isolato (= overfitting/fortuna).

Uso:
  python -m optimizer.validate_one --symbol NZDUSD --module trend
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb

MOD = {"trend": fb.MODULE_TREND, "meanrev": fb.MODULE_MEANREV,
       "vol": fb.MODULE_VOL, "asia": fb.MODULE_ASIA}

# Parametri chiave da testare in sensibilità, per modulo
SENS = {
    "trend": ["trend_adx_h1_min", "trend_adx_h4_min", "trend_atr_stop_mult", "rr", "max_bars_open"],
    "vol": ["compression_percentile", "vol_adx_max", "vol_atr_stop_mult", "rr", "max_bars_open"],
    "meanrev": ["range_adx_h1_max", "mean_rsi_long_max", "mean_atr_stop_mult", "rr", "max_bars_open"],
}
STEP = {"trend_adx_h1_min": 2, "trend_adx_h4_min": 2, "trend_atr_stop_mult": 0.25,
        "rr": 0.25, "max_bars_open": 20, "compression_percentile": 5, "vol_adx_max": 2,
        "vol_atr_stop_mult": 0.25, "range_adx_h1_max": 2, "mean_rsi_long_max": 2,
        "mean_atr_stop_mult": 0.2}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Validazione approfondita di una strategia")
    ap.add_argument("--symbol", default="NZDUSD")
    ap.add_argument("--module", default="trend", choices=list(MOD))
    ap.add_argument("--years", type=float, default=8.0)
    args = ap.parse_args()
    mod_id = MOD[args.module]

    h1_bars = int(args.years * 252 * 24)
    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")
    h1 = client.rates(args.symbol, "H1", h1_bars)
    h4 = client.rates(args.symbol, "H4", h1_bars // 4)
    client.disconnect()

    pc = fb.precompute(h1, h4)
    times = pd.DatetimeIndex(h1["time"].to_numpy())

    print(f"=== VALIDAZIONE {args.symbol} / {args.module.upper()} (parametri DEFAULT) ===")
    print(f"Storia: {times[0].date()} -> {times[-1].date()}\n")

    # ---------- 1) PROFILO DI RISCHIO ----------
    trades = fb.collect_trades(pc, {}, modules=(mod_id,))
    pnls = np.array([t["pnl"] for t in trades])
    if len(pnls) == 0:
        print("Nessun trade.")
        return
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    max_dd = float((peak - eq).max())
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    # serie di perdite consecutive più lunga
    streak = mx = 0
    for p in pnls:
        streak = streak + 1 if p < 0 else 0
        mx = max(mx, streak)
    avg_w = wins.mean() if len(wins) else 0.0
    avg_l = losses.mean() if len(losses) else 0.0
    payoff = (avg_w / abs(avg_l)) if avg_l != 0 else 0.0
    pf = wins.sum() / -losses.sum() if losses.sum() != 0 else 9.99
    longs = [t["pnl"] for t in trades if t["side"] == fb.BUY]
    shorts = [t["pnl"] for t in trades if t["side"] == fb.SELL]

    print("1) PROFILO DI RISCHIO (8 anni, default)")
    print(f"   Trade totali     : {len(pnls)}   ({len(longs)} long / {len(shorts)} short)")
    print(f"   Total R          : {eq[-1]:+.1f} R")
    print(f"   Profit Factor    : {pf:.2f}")
    print(f"   Win rate         : {len(wins)/len(pnls):.0%}")
    print(f"   Vincita media    : +{avg_w:.2f} R   Perdita media: {avg_l:.2f} R   Payoff: {payoff:.2f}")
    print(f"   Max drawdown     : {max_dd:.1f} R")
    print(f"   Perdite di fila  : {mx} (peggior serie)")
    print(f"   Recupero (R/DD)  : {eq[-1]/max_dd:.2f}x" if max_dd > 0 else "")
    print(f"   Long  : {sum(1 for p in longs if p>0)}/{len(longs)} vinti, {sum(longs):+.1f} R")
    print(f"   Short : {sum(1 for p in shorts if p>0)}/{len(shorts)} vinti, {sum(shorts):+.1f} R")

    # per anno
    years = sorted(set(times.year))
    print("   Anno  : " + " ".join(f"{y%100:>4}" for y in years))
    yr = [sum(t["pnl"] for t in trades if times[t["idx"]].year == y) for y in years]
    print("   R     : " + " ".join(f"{v:>4.0f}" for v in yr))
    print(f"   -> anni positivi: {sum(1 for v in yr if v>0)}/{len(years)}\n")

    # ---------- 2) SENSIBILITÀ AI PARAMETRI ----------
    print("2) SENSIBILITÀ AI PARAMETRI (il default e' robusto o un punto fortunato?)")
    print("   Per ogni parametro: Total R variando di +/- step attorno al default.\n")
    base = fb.DEFAULT_PARAMS
    for name in SENS[args.module]:
        st = STEP[name]
        base_val = base[name]
        cells = []
        for mult in (-2, -1, 0, 1, 2):
            val = base_val + mult * st
            if val <= 0:
                cells.append("   n/a")
                continue
            s = fb.evaluate(pc, {name: val}, modules=(mod_id,))
            tag = "*" if mult == 0 else " "
            cells.append(f"{s['total_r']:>5.0f}{tag}")
        vals = [base_val + m * st for m in (-2, -1, 0, 1, 2)]
        hdr = " ".join(f"{v:>6g}" for v in vals)
        print(f"   {name:<22} valori: {hdr}")
        print(f"   {'':22} TotalR: {' '.join(cells)}")
    print("\n   (* = valore default).  Se i numeri restano positivi attorno al default")
    print("   = PLATEAU = edge robusto. Se solo il default e' positivo = fragile/fortuna.")


if __name__ == "__main__":
    main()
