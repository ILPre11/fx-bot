"""
Ciclo di ottimizzazione continua (hill-climbing / coordinate descent) per la
strategia FX Multi-Regime su una singola coppia.

Algoritmo:
  1. Parte dai parametri attuali (DEFAULT_PARAMS) e ne misura la performance.
  2. Per ogni parametro prova a spostarlo di uno step (line-search nella direzione
     che migliora). Se la nuova strategia è MIGLIORE la tiene, altrimenti TORNA
     allo stato precedente.
  3. Ripete passate complete finché una passata intera non produce miglioramenti
     (= ottimo locale, strategia "stabile") o si raggiunge MAX_EVALS.

Obiettivo (cosa significa "migliore"): Total R (profitto netto in R) con guardia
-> servono almeno MIN_TRADES operazioni e PF >= MIN_PF, altrimenti la soluzione è
penalizzata (evita ottimi "fortunati" con pochissimi trade).

Uso:
  python -m optimizer.param_search                 # EURJPY, 4 anni
  python -m optimizer.param_search --symbol USDJPY --years 3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb

# --- Obiettivo ----------------------------------------------------------------
MIN_TRADES = 20
MIN_PF = 1.2
MAX_EVALS = 600

# --- Spazio di ricerca: nome -> (min, max, step) ------------------------------
SEARCH_SPACE: dict[str, tuple[float, float, float]] = {
    # Uscita (le leve più importanti secondo l'analisi: R:R e time-stop)
    "rr":                     (1.0, 4.0, 0.25),
    "max_bars_open":          (40, 240, 20),
    # Trend
    "trend_adx_h1_min":       (15.0, 34.0, 2.0),
    "trend_adx_h4_min":       (15.0, 34.0, 2.0),
    "trend_atr_stop_mult":    (1.0, 3.5, 0.25),
    # Mean reversion
    "range_adx_h1_max":       (12.0, 25.0, 1.0),
    "range_adx_h4_max":       (12.0, 28.0, 2.0),
    "range_near_ema_atr":     (0.5, 2.0, 0.25),
    "range_atr_max_ratio":    (0.90, 1.50, 0.05),
    "mean_rsi_long_max":      (3.0, 20.0, 2.0),
    "mean_rsi_short_min":     (80.0, 97.0, 2.0),
    "mean_atr_stop_mult":     (1.0, 2.5, 0.20),
    # Vol breakout
    "compression_percentile": (10.0, 40.0, 5.0),
    "vol_adx_max":            (12.0, 28.0, 2.0),
    "vol_atr_stop_mult":      (1.0, 3.0, 0.25),
    # Asia breakout
    "asia_min_range_atr":     (0.20, 0.80, 0.10),
    "asia_max_range_atr":     (0.90, 1.80, 0.10),
    "asia_breakout_buffer_atr": (0.05, 0.30, 0.05),
    "asia_max_stop_atr":      (1.50, 3.00, 0.20),
    "asia_width_percentile":  (30.0, 60.0, 5.0),
}


def objective(stats: dict) -> float:
    """Più alto = meglio. Total R con guardia su numero trade e PF."""
    n = stats["num_trades"]
    if n < MIN_TRADES:
        return -1e6 + n  # prima di tutto: raggiungi abbastanza operazioni
    score = stats["total_r"]
    if stats["pf"] < MIN_PF:
        score -= 50.0     # penalità morbida se il PF è sotto soglia
    return score


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def hill_climb(pc, log_path: Path) -> tuple[dict, dict]:
    params = dict(fb.DEFAULT_PARAMS)
    base_stats = fb.evaluate(pc, params)
    best_score = objective(base_stats)
    evals = 1

    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

    log(f"=== Hill-climbing avviato [{datetime.utcnow():%Y-%m-%d %H:%M} UTC] ===")
    log(f"Baseline (strategia attuale): {_fmt(base_stats)}  score={best_score:.2f}")
    log(f"Obiettivo: max Total R | guardia: trade>={MIN_TRADES}, PF>={MIN_PF}\n")

    pass_n = 0
    improved = True
    while improved and evals < MAX_EVALS:
        pass_n += 1
        improved = False
        log(f"--- Passata {pass_n} (eval finora: {evals}) ---")

        for name, (lo, hi, step) in SEARCH_SPACE.items():
            # line-search: trova la direzione che migliora e continua finché va su
            for direction in (+1, -1):
                moved_in_dir = False
                while evals < MAX_EVALS:
                    cand = dict(params)
                    newval = _clip(cand[name] + direction * step, lo, hi)
                    if newval == cand[name]:
                        break
                    cand[name] = newval
                    stats = fb.evaluate(pc, cand)
                    evals += 1
                    score = objective(stats)
                    if score > best_score + 1e-9:
                        params = cand
                        best_score = score
                        improved = True
                        moved_in_dir = True
                        log(f"  [+] {name} -> {newval:g}  | {_fmt(stats)}  score={score:.2f}")
                    else:
                        break  # peggiora o pari: torna allo stato precedente
                if moved_in_dir:
                    break  # già migliorato in questa direzione, passa al prossimo parametro

        if not improved:
            log(f"\nNessun miglioramento nella passata {pass_n}: ottimo locale raggiunto (stabile).")

    if evals >= MAX_EVALS:
        log(f"\nRaggiunto MAX_EVALS={MAX_EVALS}.")

    final_stats = fb.evaluate(pc, params)
    log(f"\n=== RISULTATO ({evals} valutazioni) ===")
    log(f"Baseline: {_fmt(base_stats)}")
    log(f"Ottimo  : {_fmt(final_stats)}")
    log("\nParametri modificati rispetto alla strategia attuale:")
    for k in SEARCH_SPACE:
        if params[k] != fb.DEFAULT_PARAMS[k]:
            log(f"  {k}: {fb.DEFAULT_PARAMS[k]:g} -> {params[k]:g}")
    return params, final_stats


def _fmt(s: dict) -> str:
    return (f"trade={s['num_trades']:>3} PF={s['pf']:>5.2f} WR={s['win_rate']:>4.0%} "
            f"R={s['total_r']:>7.1f} Sharpe={s['sharpe']:>6.2f} DD={s['max_dd_r']:>5.1f}R")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # evita crash cp1252 su Windows
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Ottimizzazione continua hill-climbing")
    ap.add_argument("--symbol", default=config.PAIR)
    ap.add_argument("--years", type=float, default=4.0)
    args = ap.parse_args()

    h1_bars = int(args.years * 252 * 24)  # ~ore di trading l'anno
    out_dir = Path(__file__).parent
    log_path = out_dir / f"opt_{args.symbol}.log"

    try:
        with Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD,
                       config.MT5_SERVER, config.MT5_PATH) as client:
            print(f"Scarico {args.symbol}: {h1_bars} barre H1 (~{args.years} anni)...")
            h1 = client.rates(args.symbol, "H1", h1_bars)
            h4 = client.rates(args.symbol, "H4", h1_bars // 4)
            print(f"  H1={len(h1)} ({h1['time'].iloc[0].date()} -> {h1['time'].iloc[-1].date()}), H4={len(h4)}")

            t0 = time.time()
            pc = fb.precompute(h1, h4)
            print(f"  Precompute: {time.time()-t0:.1f}s, start bar={pc.start}\n")

            params, stats = hill_climb(pc, log_path)

            best_path = out_dir / f"best_params_{args.symbol}.json"
            best_path.write_text(json.dumps({
                "symbol": args.symbol,
                "years": args.years,
                "timestamp": datetime.utcnow().isoformat(),
                "stats": stats,
                "params": params,
            }, indent=2), encoding="utf-8")
            print(f"\nParametri ottimi salvati in: {best_path}")
            print(f"Log completo in: {log_path}")
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")


if __name__ == "__main__":
    main()
