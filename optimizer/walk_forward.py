"""
Validazione WALK-FORWARD della strategia FX Multi-Regime su una coppia.

Scopo: stimare se i parametri ottimizzati REGGONO su dati MAI VISTI (out-of-sample),
non solo sul periodo su cui sono stati ottimizzati. È il test che distingue un
edge reale dall'overfitting.

Metodo (anchored walk-forward, più fette):
  - Scarica una storia lunga (default ~8 anni).
  - Per ogni fetta: OTTIMIZZA i parametri solo sul blocco TRAIN (ILS), poi li
    CONGELA e li valuta sul blocco TEST successivo, che l'ottimizzatore non ha
    mai visto.
  - Confronta in-sample (train) vs out-of-sample (test) per ogni fetta + medie.

Gli indicatori sono calcolati su tutta la storia continua: train e test sono
separati per INDICE di ingresso, quindi al confine gli indicatori sono già caldi.

Uso:
  python -m optimizer.walk_forward                       # EURJPY, 8 anni, 3 fette
  python -m optimizer.walk_forward --symbol EURJPY --years 8 --folds 3 --evals-per-fold 1500
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb
from optimizer import global_search as gs

WARMUP_LEAD = 1300  # barre di riscaldamento prima di poter contare i trade

MODULE_MAP = {"trend": fb.MODULE_TREND, "meanrev": fb.MODULE_MEANREV,
              "vol": fb.MODULE_VOL, "asia": fb.MODULE_ASIA}

# Spazi di ricerca RISTRETTI per modulo (pochi gradi di libertà = poco overfit).
SPACE_SUBSETS = {
    "vol": ["rr", "max_bars_open", "compression_percentile",
            "vol_adx_max", "vol_atr_stop_mult"],
    "trend": ["rr", "max_bars_open", "trend_adx_h1_min",
              "trend_adx_h4_min", "trend_atr_stop_mult"],
    "meanrev": ["rr", "max_bars_open", "range_adx_h1_max", "mean_rsi_long_max",
                "mean_rsi_short_min", "mean_atr_stop_mult"],
}


class RangeEvaluator:
    """Valuta un vettore su un intervallo fisso [lo,hi); cache precompute per periodi."""
    def __init__(self, h1, h4, modules=(1, 2, 3, 4)):
        self.h1, self.h4 = h1, h4
        self.modules = modules
        self.cache: dict = {}
        self.lo = None
        self.hi = None
        self.n_evals = 0

    def _pc(self, periods: dict):
        key = tuple(sorted(periods.items()))
        pc = self.cache.get(key)
        if pc is None:
            pc = fb.precompute(self.h1, self.h4, periods)
            if len(self.cache) >= 96:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = pc
        return pc

    def evaluate(self, vector: dict) -> dict:
        self.n_evals += 1
        return self.eval_range(vector, self.lo, self.hi)

    def eval_range(self, vector: dict, lo: int, hi: int) -> dict:
        periods, thr = gs.split(vector)
        pc = self._pc(periods)
        return fb.evaluate(pc, thr, modules=self.modules, lo=lo, hi=hi)


def _noop(*_a, **_k):
    pass


def _restart_vector() -> dict:
    """Vettore COMPLETO (default per le chiavi non cercate) con valori casuali sulle
    sole chiavi dello spazio di ricerca attivo (gs.SPACE). Necessario quando lo
    spazio è ristretto: gs.random_vector() darebbe un vettore parziale."""
    v = gs.default_vector()
    for name, (lo, hi, step, is_int) in gs.SPACE.items():
        v[name] = gs.snap(random.uniform(lo, hi), lo, hi, step, is_int)
    return v


def optimize_on(ev: RangeEvaluator, lo: int, hi: int, max_evals: int, seed: int) -> dict:
    """ILS (riuso global_search) sull'intervallo train [lo,hi). Ritorna il best vector."""
    random.seed(seed)
    ev.lo, ev.hi = lo, hi
    ev.n_evals = 0

    best = gs.default_vector()
    best_score = gs.objective(ev.evaluate(best))
    current = dict(best)
    current_score = best_score

    while ev.n_evals < max_evals:
        current, current_score = gs.local_optimize(ev, current, current_score, _noop)
        if current_score > best_score + 1e-9:
            best, best_score = dict(current), current_score
        current = gs.perturb(best) if random.random() < 0.6 else _restart_vector()
        current_score = gs.objective(ev.evaluate(current))
    return best


def _fmt(s: dict) -> str:
    return (f"trade={s['num_trades']:>3} PF={s['pf']:>5.2f} WR={s['win_rate']:>4.0%} "
            f"R={s['total_r']:>7.1f} Sharpe={s['sharpe']:>6.2f} DD={s['max_dd_r']:>5.1f}R")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Validazione walk-forward (out-of-sample)")
    ap.add_argument("--symbol", default=config.PAIR)
    ap.add_argument("--years", type=float, default=8.0)
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--evals-per-fold", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=2024)
    ap.add_argument("--modules", default="all",
                    help="moduli attivi: 'all' o lista es. 'vol' / 'trend,vol'")
    ap.add_argument("--space", default="full", choices=["full"] + list(SPACE_SUBSETS),
                    help="full=tutti i parametri, oppure il nome modulo (vol/trend/meanrev)")
    args = ap.parse_args()

    # selezione moduli
    if args.modules == "all":
        modules = (1, 2, 3, 4)
    else:
        modules = tuple(MODULE_MAP[m.strip().lower()] for m in args.modules.split(","))
    # spazio di ricerca (restringe i gradi di libertà = meno overfitting)
    if args.space in SPACE_SUBSETS:
        gs.SPACE = {k: gs.SPACE[k] for k in SPACE_SUBSETS[args.space]}
        gs.MIN_TRADES = 15  # i singoli moduli sono a frequenza più bassa dell'ensemble

    out_dir = Path(__file__).parent
    mod_tag = args.modules.replace(",", "+") if args.modules != "all" else "all"
    tag = f"{args.symbol}_{mod_tag}"
    log_path = out_dir / f"walkforward_{tag}.log"
    lines: list[str] = []

    def w(msg):
        print(msg, flush=True)
        lines.append(msg)
        log_path.write_text("\n".join(lines), encoding="utf-8")

    h1_bars = int(args.years * 252 * 24)
    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")
    h1 = client.rates(args.symbol, "H1", h1_bars)
    h4 = client.rates(args.symbol, "H4", h1_bars // 4)
    client.disconnect()

    import pandas as pd
    N = len(h1)
    times = h1["time"].to_numpy()

    def d(idx):  # data leggibile per un indice
        idx = max(0, min(N - 1, idx))
        return str(pd.Timestamp(times[idx]).date())

    w(f"=== WALK-FORWARD {args.symbol} [{datetime.utcnow():%Y-%m-%d %H:%M} UTC] ===")
    w(f"Storia: H1={N} ({d(0)} -> {d(N-1)}) | fette={args.folds} | "
      f"eval/fetta={args.evals_per_fold} | moduli={args.modules} | spazio={args.space}")
    w("Per ogni fetta confronto DEFAULT (no opt) e OTTIMIZZATO, sempre testati OOS.\n")

    # Fette anchored: il test copre l'ultima parte della storia, diviso in N finestre.
    usable = N - WARMUP_LEAD
    test_span = usable // (args.folds + 1)  # i test occupano l'ultima frazione
    ev = RangeEvaluator(h1, h4, modules=modules)
    default_vec = gs.default_vector()

    is_results, oos_results = [], []        # ottimizzati
    def_oos_results = []                    # default (no opt) su test
    for k in range(args.folds):
        # anchored: train = [WARMUP, test_lo), test = la fetta successiva
        test_lo = WARMUP_LEAD + (k + 1) * test_span
        train_lo, train_hi = WARMUP_LEAD, test_lo
        test_hi = test_lo + test_span if k < args.folds - 1 else N - 2

        w(f"--- Fetta {k+1}/{args.folds} ---")
        w(f"  TRAIN: {d(train_lo)} -> {d(train_hi)}   |   TEST: {d(test_lo)} -> {d(test_hi)}")

        # 1) DEFAULT (nessuna ottimizzazione): il riferimento onesto
        def_train = ev.eval_range(default_vec, train_lo, train_hi)
        def_test = ev.eval_range(default_vec, test_lo, test_hi)
        def_oos_results.append(def_test)
        w(f"  DEFAULT    train: {_fmt(def_train)}")
        w(f"  DEFAULT    TEST : {_fmt(def_test)}   <- OOS senza ottimizzazione")

        # 2) OTTIMIZZATO sui soli parametri dello spazio scelto
        best = optimize_on(ev, train_lo, train_hi, args.evals_per_fold, args.seed + k)
        opt_train = ev.eval_range(best, train_lo, train_hi)
        opt_test = ev.eval_range(best, test_lo, test_hi)
        is_results.append(opt_train)
        oos_results.append(opt_test)
        w(f"  OTTIMIZZATO train: {_fmt(opt_train)}")
        w(f"  OTTIMIZZATO TEST : {_fmt(opt_test)}   <- OOS dopo ottimizzazione")
        ret = (opt_test["total_r"] / opt_train["total_r"]
               if opt_train["total_r"] > 0 else 0.0)
        w(f"  -> tenuta OOS/IS (ottimizzato): {ret:.0%}\n")

    # Sintesi
    def avg(rs, key):
        vals = [r[key] for r in rs]
        return sum(vals) / len(vals) if vals else 0.0

    w("=== SINTESI ===")
    w(f"  DEFAULT (no opt)  OOS medio: R={avg(def_oos_results,'total_r'):.1f}  "
      f"PF={avg(def_oos_results,'pf'):.2f}  | fette+ {sum(1 for r in def_oos_results if r['total_r']>0)}/{len(def_oos_results)}")
    w(f"  OTTIMIZZATO  IN-SAMPLE medio: R={avg(is_results,'total_r'):.1f}  PF={avg(is_results,'pf'):.2f}")
    w(f"  OTTIMIZZATO  OUT-OF-SAMPLE  : R={avg(oos_results,'total_r'):.1f}  PF={avg(oos_results,'pf'):.2f}")
    oos_pf = avg(oos_results, "pf")
    n_pos = sum(1 for r in oos_results if r["total_r"] > 0)
    recent = oos_results[-1]  # la fetta piu' recente = miglior proxy del live di oggi
    # La MEDIA inganna: conta la consistenza tra fette e soprattutto la piu' recente.
    if recent["total_r"] <= 0:
        verdict = ("NON PRONTA: la fetta piu' recente (proxy del live attuale) e' in "
                   "perdita -> edge decaduto/overfitting. Non andare live con questi params.")
    elif n_pos == len(oos_results) and oos_pf >= 1.3:
        verdict = "PROMETTENTE: edge positivo e consistente in TUTTE le fette OOS."
    elif n_pos >= (len(oos_results) + 1) // 2:
        verdict = "INCERTA: edge OOS instabile (positivo solo in parte delle fette)."
    else:
        verdict = "DEBOLE: edge OOS assente nella maggioranza delle fette."
    w(f"  Fette OOS positive: {n_pos}/{len(oos_results)} | piu' recente: "
      f"R={recent['total_r']:.1f} PF={recent['pf']:.2f}")
    w(f"  VERDETTO: {verdict}")

    (out_dir / f"walkforward_{tag}.json").write_text(json.dumps({
        "symbol": args.symbol, "modules": args.modules, "years": args.years, "folds": args.folds,
        "default_out_of_sample": def_oos_results,
        "in_sample": is_results, "out_of_sample": oos_results,
        "timestamp": datetime.utcnow().isoformat(),
    }, indent=2), encoding="utf-8")
    w(f"\nRisultati salvati in: walkforward_{tag}.json e .log")


if __name__ == "__main__":
    main()
