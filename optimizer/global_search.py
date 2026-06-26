"""
Ottimizzatore GLOBALE per massimizzare il profitto totale (Total R) della
strategia FX Multi-Regime su una coppia.

A differenza di param_search.py (che si ferma al primo ottimo locale), questo usa
ITERATED LOCAL SEARCH: ottimizza fino a un ottimo locale, poi PERTURBA / RIPARTE
da punti casuali e riprova, all'infinito, tenendo SEMPRE il migliore trovato.
Pensato per girare a lungo (ore/giorni): salva il best su disco a ogni
miglioramento, quindi puoi fermarlo quando vuoi (Ctrl+C) senza perdere nulla.

Ottimizza sia le SOGLIE sia i PERIODI degli indicatori.

Obiettivo: massimo Total R, con guardia minima (trade>=MIN_TRADES, PF>=MIN_PF)
per evitare soluzioni degeneri con pochissime operazioni.

Uso:
  python -m optimizer.global_search --symbol EURJPY --years 4
  python -m optimizer.global_search --symbol EURJPY --years 4 --max-evals 100000
"""
from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb

# --- Obiettivo ---------------------------------------------------------------
MIN_TRADES = 30
MIN_PF = 1.10

# --- Spazio di ricerca: nome -> (min, max, step, is_int) ----------------------
# Soglie
THRESHOLDS = {
    "rr":                       (1.0, 5.0, 0.25, False),
    "max_bars_open":            (30, 300, 10, True),
    "trend_adx_h1_min":         (12.0, 38.0, 1.0, False),
    "trend_adx_h4_min":         (12.0, 38.0, 1.0, False),
    "trend_atr_stop_mult":      (0.8, 4.0, 0.1, False),
    "range_adx_h1_max":         (10.0, 28.0, 1.0, False),
    "range_adx_h4_max":         (10.0, 30.0, 1.0, False),
    "range_near_ema_atr":       (0.4, 2.5, 0.1, False),
    "range_atr_max_ratio":      (0.85, 1.60, 0.05, False),
    "mean_rsi_long_max":        (2.0, 25.0, 1.0, False),
    "mean_rsi_short_min":       (75.0, 98.0, 1.0, False),
    "mean_atr_stop_mult":       (0.8, 3.0, 0.1, False),
    "compression_percentile":   (8.0, 45.0, 1.0, False),
    "vol_adx_max":              (10.0, 30.0, 1.0, False),
    "vol_atr_stop_mult":        (0.8, 3.5, 0.1, False),
    "asia_min_range_atr":       (0.15, 0.90, 0.05, False),
    "asia_max_range_atr":       (0.80, 2.00, 0.05, False),
    "asia_breakout_buffer_atr": (0.02, 0.35, 0.01, False),
    "asia_max_stop_atr":        (1.20, 3.50, 0.10, False),
    "asia_width_percentile":    (25.0, 65.0, 1.0, False),
}
# Periodi indicatori
PERIODS = {
    "fast_ema":     (8, 35, 1, True),
    "medium_ema":   (25, 80, 1, True),
    "slow_ema":     (60, 160, 2, True),
    "long_ema":     (120, 280, 5, True),
    "adx_period":   (7, 25, 1, True),
    "atr_period":   (7, 25, 1, True),
    "atr_long":     (60, 160, 5, True),
    "bb_period":    (10, 35, 1, True),
    "rsi_period":   (2, 8, 1, True),
    "donchian":     (10, 35, 1, True),
    "bbw_pct_bars": (60, 180, 10, True),
}
SPACE = {**THRESHOLDS, **PERIODS}
PERIOD_NAMES = set(PERIODS)


def snap(v, lo, hi, step, is_int):
    v = max(lo, min(hi, v))
    v = round((v - lo) / step) * step + lo
    v = max(lo, min(hi, v))
    return int(round(v)) if is_int else round(v, 6)


def default_vector() -> dict:
    v = dict(fb.DEFAULT_PARAMS)
    v.update(fb.DEFAULT_PERIODS)
    return v


def random_vector() -> dict:
    return {name: snap(random.uniform(lo, hi), lo, hi, step, is_int)
            for name, (lo, hi, step, is_int) in SPACE.items()}


def split(vector: dict):
    periods = {k: int(vector[k]) for k in PERIOD_NAMES}
    thresholds = {k: vector[k] for k in vector if k not in PERIOD_NAMES}
    return periods, thresholds


class Evaluator:
    """Valuta un vettore completo; mette in cache i precompute per insieme di periodi."""
    def __init__(self, h1, h4, cache_size=64):
        self.h1, self.h4 = h1, h4
        self.cache: dict = {}
        self.cache_size = cache_size
        self.n_evals = 0

    def _pc(self, periods: dict):
        key = tuple(sorted(periods.items()))
        pc = self.cache.get(key)
        if pc is None:
            pc = fb.precompute(self.h1, self.h4, periods)
            if len(self.cache) >= self.cache_size:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = pc
        return pc

    def evaluate(self, vector: dict) -> dict:
        self.n_evals += 1
        periods, thresholds = split(vector)
        pc = self._pc(periods)
        return fb.evaluate(pc, thresholds)


def objective(stats: dict) -> float:
    n = stats["num_trades"]
    if n < MIN_TRADES:
        return -1e6 + n
    if stats["pf"] < MIN_PF:
        return -1e5 + stats["total_r"]
    return stats["total_r"]


def coordinate_descent(ev: Evaluator, vector: dict, best_score: float, scale: float, log):
    """Line-search su ogni parametro con step*scale. Ritorna (vector, score, improved)."""
    improved_any = False
    for name, (lo, hi, step, is_int) in SPACE.items():
        s = max(1, int(round(step * scale))) if is_int else step * scale
        for direction in (+1, -1):
            moved = False
            while True:
                cand = dict(vector)
                newval = snap(cand[name] + direction * s, lo, hi, step, is_int)
                if newval == cand[name]:
                    break
                cand[name] = newval
                score = objective(ev.evaluate(cand))
                if score > best_score + 1e-9:
                    vector, best_score = cand, score
                    improved_any = moved = True
                    log(vector, best_score, name, newval)
                else:
                    break
            if moved:
                break
    return vector, best_score, improved_any


def local_optimize(ev: Evaluator, vector: dict, score: float, log):
    """Coordinate descent multi-risoluzione fino a stabilità."""
    for scale in (1.0, 0.5, 0.25):
        while True:
            vector, score, improved = coordinate_descent(ev, vector, score, scale, log)
            if not improved:
                break
    return vector, score


def perturb(vector: dict) -> dict:
    """Calcio casuale: sposta un sottoinsieme di parametri di +/- alcuni step."""
    cand = dict(vector)
    names = random.sample(list(SPACE), k=random.randint(3, 8))
    for name in names:
        lo, hi, step, is_int = SPACE[name]
        kick = random.choice([-3, -2, -1, 1, 2, 3]) * step
        cand[name] = snap(cand[name] + kick, lo, hi, step, is_int)
    return cand


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Ottimizzazione globale (ILS) per max profitto")
    ap.add_argument("--symbol", default=config.PAIR)
    ap.add_argument("--years", type=float, default=4.0)
    ap.add_argument("--max-evals", type=int, default=50000)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()
    random.seed(args.seed)

    out_dir = Path(__file__).parent
    log_path = out_dir / f"global_{args.symbol}.log"
    best_path = out_dir / f"best_params_{args.symbol}.json"
    log_lines: list[str] = []

    def writeln(msg):
        print(msg, flush=True)
        log_lines.append(msg)
        log_path.write_text("\n".join(log_lines), encoding="utf-8")

    h1_bars = int(args.years * 252 * 24)
    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")

    h1 = client.rates(args.symbol, "H1", h1_bars)
    h4 = client.rates(args.symbol, "H4", h1_bars // 4)
    writeln(f"=== GLOBAL SEARCH {args.symbol} [{datetime.utcnow():%Y-%m-%d %H:%M} UTC] ===")
    writeln(f"H1={len(h1)} ({h1['time'].iloc[0].date()} -> {h1['time'].iloc[-1].date()}), max_evals={args.max_evals}")
    writeln(f"Obiettivo: MAX Total R | guardia trade>={MIN_TRADES}, PF>={MIN_PF}\n")

    ev = Evaluator(h1, h4)

    # punto di partenza: best salvato (se esiste) altrimenti i parametri attuali
    start_vec = default_vector()
    if best_path.exists():
        try:
            prev = json.loads(best_path.read_text(encoding="utf-8"))
            saved = {**prev.get("params", {}), **prev.get("periods", {})}
            for k in SPACE:
                if k in saved:
                    lo, hi, step, is_int = SPACE[k]
                    start_vec[k] = snap(saved[k], lo, hi, step, is_int)
            writeln("Ripartenza dal best precedente salvato su disco.")
        except Exception:
            pass

    global_best = dict(start_vec)
    global_stats = ev.evaluate(global_best)
    global_score = objective(global_stats)
    writeln(f"Start: {_fmt(global_stats)}  score={global_score:.2f}\n")

    state = {"stop": False}

    def on_sigint(*_):
        state["stop"] = True
    try:
        signal.signal(signal.SIGINT, on_sigint)
    except Exception:
        pass

    def log_improve(vec, score, name, newval):
        st = ev.evaluate(vec)
        writeln(f"  [+] {name} -> {newval:g} | {_fmt(st)} score={score:.2f}")

    current = dict(global_best)
    current_score = global_score
    restart = 0
    t0 = time.time()

    while ev.n_evals < args.max_evals and not state["stop"]:
        current, current_score = local_optimize(ev, current, current_score, log_improve)

        if current_score > global_score + 1e-9:
            global_best, global_score = dict(current), current_score
            global_stats = ev.evaluate(global_best)
            _save_best(best_path, args, global_stats, global_best)
            writeln(f"*** NUOVO BEST: {_fmt(global_stats)} score={global_score:.2f} "
                    f"(eval {ev.n_evals}, restart {restart}) ***")

        restart += 1
        # alterna: perturbazione del best globale, oppure ripartenza totalmente casuale
        if random.random() < 0.6:
            current = perturb(global_best)
        else:
            current = random_vector()
        current_score = objective(ev.evaluate(current))

        if restart % 20 == 0:
            rate = ev.n_evals / max(1e-9, time.time() - t0)
            writeln(f"... eval={ev.n_evals} restart={restart} bestR={global_stats['total_r']:.1f} "
                    f"({rate:.0f} eval/s)")

    writeln(f"\n=== FINE (eval={ev.n_evals}, restart={restart}) ===")
    writeln(f"BEST: {_fmt(global_stats)}")
    writeln("Parametri modificati rispetto alla strategia attuale:")
    defv = default_vector()
    for k in SPACE:
        if global_best[k] != defv[k]:
            tag = "[periodo]" if k in PERIOD_NAMES else "[soglia] "
            writeln(f"  {tag} {k}: {defv[k]:g} -> {global_best[k]:g}")
    writeln(f"\nBest salvato in: {best_path}")
    client.disconnect()


def _fmt(s: dict) -> str:
    return (f"trade={s['num_trades']:>3} PF={s['pf']:>5.2f} WR={s['win_rate']:>4.0%} "
            f"R={s['total_r']:>7.1f} Sharpe={s['sharpe']:>6.2f} DD={s['max_dd_r']:>5.1f}R")


def _save_best(path: Path, args, stats: dict, vector: dict):
    periods, thresholds = split(vector)
    path.write_text(json.dumps({
        "symbol": args.symbol,
        "years": args.years,
        "timestamp": datetime.utcnow().isoformat(),
        "objective": "max_total_r",
        "stats": stats,
        "params": thresholds,
        "periods": periods,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
