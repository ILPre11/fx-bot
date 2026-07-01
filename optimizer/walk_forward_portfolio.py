"""
Walk-forward del PORTAFOGLIO combinato (piu' strategie validate insieme).

Le gambe singole (NZDUSD Trend, USDJPY VOL, ...) sono gia' validate una per una
(vedi optimizer/walk_forward.py, walkforward_*.json/log). Qui si verifica la
COMBINAZIONE: le gambe unite, pesate per il rischio reale per-modulo
(risk_*_pct del profilo attivo in config.py), restano positive e stabili nel
tempo? E soprattutto: il drawdown COMBINATO e' davvero piu' basso della somma
dei drawdown delle gambe prese singolarmente nello stesso periodo (vera
diversificazione), o le gambe sono correlate e il vantaggio e' illusorio?

IMPORTANTE: se PIU' MODULI sono attivi sullo STESSO simbolo (es. NZDUSD Trend +
NZDUSD Vol), nel live vengono arbitrati da ChooseSignal (una sola posizione per
simbolo alla volta, vedi risk/portfolio_layer.py "Max 1 posizione per simbolo")
-> qui si raggruppano per simbolo e si passano TUTTI i moduli di quel simbolo
insieme a collect_trades(), che applica la stessa arbitrarietà/priorita' e lo
stesso vincolo "una posizione alla volta" del motore originale. NON si sommano
le gambe come se fossero indipendenti quando condividono il simbolo: sarebbe
irrealistico (nella realta' non potrebbero mai essere aperte insieme).

Nessuna ottimizzazione qui: si usano SOLO i parametri DEFAULT gia' validati per
ciascun modulo (verificato altrove che ottimizzare peggiora l'OOS). Le fette
sono calendariali (non per indice barra: simboli diversi hanno storie non
perfettamente allineate per indice).

Uso:
  python -m optimizer.walk_forward_portfolio
  python -m optimizer.walk_forward_portfolio --legs NZDUSD:trend,USDJPY:vol --years 8 --folds 3
  python -m optimizer.walk_forward_portfolio --legs NZDUSD:trend,USDJPY:vol,NZDUSD:vol
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

import config
from forex_bot.mt5_client import Mt5Client, Mt5Error
from optimizer import fast_backtest as fb

RISK_KEY = {"trend": "risk_trend_pct", "vol": "risk_vol_pct",
            "meanrev": "risk_mean_pct", "asia": "risk_asia_pct"}
MODULE_MAP = {"trend": fb.MODULE_TREND, "meanrev": fb.MODULE_MEANREV,
              "vol": fb.MODULE_VOL, "asia": fb.MODULE_ASIA}
MODULE_NAME = {v: k for k, v in MODULE_MAP.items()}


def parse_legs(spec: str) -> list[tuple[str, str]]:
    legs = []
    for chunk in spec.split(","):
        sym, mod = chunk.split(":")
        legs.append((sym.strip().upper(), mod.strip().lower()))
    return legs


def default_legs() -> list[tuple[str, str]]:
    out = []
    for sym, mods in config.VALIDATED_STRATEGIES.items():
        for m in mods:
            out.append((sym, m))
    return out


class SymbolGroup:
    """Un simbolo con 1+ moduli attivi, arbitrati insieme come nel live
    (ChooseSignal + una posizione alla volta) -> una sola serie di trade."""

    def __init__(self, symbol: str, module_names: list[str], h1: pd.DataFrame,
                 h4: pd.DataFrame, risk_by_mod: dict[str, float]):
        self.symbol = symbol
        self.module_names = module_names
        self.risk_by_mod = risk_by_mod  # nome modulo -> frazione equity (pct/100)
        self.pc = fb.precompute(h1, h4)
        module_ids = tuple(MODULE_MAP[m] for m in module_names)
        raw = fb.collect_trades(self.pc, fb.DEFAULT_PARAMS, modules=module_ids)
        self.trades = []
        for t in raw:
            mod_name = MODULE_NAME[t["mod"]]
            risk = risk_by_mod[mod_name]
            entry_time = pd.Timestamp(self.pc.h1_time[t["idx"]])
            exit_idx = min(t["idx"] + t["bars"], self.pc.n - 1)
            self.trades.append({
                "time": entry_time, "exit_time": pd.Timestamp(self.pc.h1_time[exit_idx]),
                "symbol": symbol, "mod": mod_name,
                "r": t["pnl"], "w": t["pnl"] * risk,
            })
        self.start_time = pd.Timestamp(self.pc.h1_time[self.pc.start])
        self.end_time = pd.Timestamp(self.pc.h1_time[-1])

    @property
    def label(self) -> str:
        return f"{self.symbol}({'+'.join(self.module_names)})"

    def module_breakdown(self) -> dict[str, int]:
        counts = defaultdict(int)
        for t in self.trades:
            counts[t["mod"]] += 1
        return dict(counts)


def _stats(rows: list[dict], key: str = "w") -> dict:
    if not rows:
        return {"num_trades": 0, "pf": 0.0, "total": 0.0, "sharpe": 0.0, "max_dd": 0.0}
    arr = np.array([r[key] for r in rows], dtype=float)
    wins, losses = arr[arr > 0], arr[arr < 0]
    gp, gl = wins.sum(), -losses.sum()
    pf = gp / gl if gl > 0 else float("inf")
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    std = arr.std()
    sharpe = float(arr.mean() / std * np.sqrt(252)) if std > 0 else 0.0
    return {
        "num_trades": len(rows),
        "pf": round(pf, 3) if pf != float("inf") else 999.0,
        "total": round(float(arr.sum()) * 100, 2),   # in % equity
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd * 100, 2),             # in % equity
    }


def _fmt(s: dict) -> str:
    return (f"trade={s['num_trades']:>3} PF={s['pf']:>5.2f} "
            f"tot={s['total']:>7.2f}% Sharpe={s['sharpe']:>5.2f} DD={s['max_dd']:>5.2f}%")


def daily_series(rows: list[dict]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    return df.groupby(df["time"].dt.date)["w"].sum()


def concurrency_stats(rows: list[dict]) -> dict:
    """Numero di posizioni aperte simultaneamente (sweep line su entry/exit_time).
    Conta per SIMBOLO distinto (non per trade): due trade sullo stesso simbolo non
    possono mai sovrapporsi (arbitrati/1-per-simbolo), quindi la concorrenza reale
    che conta per l'esposizione/margine e' quella tra simboli diversi."""
    if not rows:
        return {"max_concurrent": 0, "avg_concurrent": 0.0, "pct_time_with_2plus": 0.0}
    events = []
    for t in rows:
        events.append((t["time"], 1))
        events.append((t["exit_time"], -1))
    events.sort(key=lambda e: (e[0], -e[1]))  # alle entrate: prima +1 se stesso istante
    cur = 0
    max_c = 0
    weighted_sum = 0.0
    time_with_2plus = pd.Timedelta(0)
    prev_t = events[0][0]
    for t, delta in events:
        dt = t - prev_t
        if dt.total_seconds() > 0:
            weighted_sum += cur * dt.total_seconds()
            if cur >= 2:
                time_with_2plus += dt
        cur += delta
        max_c = max(max_c, cur)
        prev_t = t
    total_span = (events[-1][0] - events[0][0]).total_seconds()
    avg_c = weighted_sum / total_span if total_span > 0 else 0.0
    pct2 = time_with_2plus.total_seconds() / total_span * 100 if total_span > 0 else 0.0
    return {"max_concurrent": max_c, "avg_concurrent": round(avg_c, 3),
            "pct_time_with_2plus": round(pct2, 2)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Walk-forward del portafoglio combinato")
    ap.add_argument("--legs", default=None,
                    help="es. 'NZDUSD:trend,USDJPY:vol' (default: config.VALIDATED_STRATEGIES)")
    ap.add_argument("--years", type=float, default=8.0)
    ap.add_argument("--folds", type=int, default=3)
    args = ap.parse_args()

    leg_specs = parse_legs(args.legs) if args.legs else default_legs()
    profile = config.RISK_PROFILES[config.RISK_PROFILE]

    # Raggruppa per simbolo: se un simbolo ha piu' moduli, vanno arbitrati insieme.
    by_symbol: dict[str, list[str]] = defaultdict(list)
    for sym, mod in leg_specs:
        by_symbol[sym].append(mod)

    out_dir = Path(__file__).parent
    tag = "_".join(f"{s}-{'+'.join(mods)}" for s, mods in by_symbol.items())
    log_path = out_dir / f"walkforward_portfolio_{tag}.log"
    lines: list[str] = []

    def w(msg):
        print(msg, flush=True)
        lines.append(msg)
        log_path.write_text("\n".join(lines), encoding="utf-8")

    legs_desc = ", ".join(f"{s}:{'+'.join(mods)}" for s, mods in by_symbol.items())
    w(f"=== WALK-FORWARD PORTAFOGLIO [{datetime.utcnow():%Y-%m-%d %H:%M} UTC] ===")
    w(f"Gambe: {legs_desc} | profilo rischio: {config.RISK_PROFILE}")

    h1_bars = int(args.years * 252 * 24)
    try:
        client = Mt5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER, config.MT5_PATH)
        client.connect()
    except Mt5Error as exc:
        raise SystemExit(f"MT5 error: {exc}")

    groups: list[SymbolGroup] = []
    for sym, mods in by_symbol.items():
        h1 = client.rates(sym, "H1", h1_bars)
        h4 = client.rates(sym, "H4", h1_bars // 4)
        risk_by_mod = {m: profile[RISK_KEY[m]] / 100.0 for m in mods}
        grp = SymbolGroup(sym, mods, h1, h4, risk_by_mod)
        groups.append(grp)
        bd = grp.module_breakdown()
        bd_str = ", ".join(f"{m}={n}" for m, n in bd.items()) if len(mods) > 1 else ""
        w(f"  {grp.label}: {len(grp.trades)} trade" + (f" ({bd_str})" if bd_str else "") +
          f" | storia utile {grp.start_time.date()} -> {grp.end_time.date()}")
    client.disconnect()

    overall_start = max(g.start_time for g in groups)
    overall_end = min(g.end_time for g in groups)
    w(f"\nSovrapposizione calendariale usabile: {overall_start.date()} -> {overall_end.date()}")

    all_trades = [t for g in groups for t in g.trades
                  if overall_start <= t["time"] <= overall_end]
    all_trades.sort(key=lambda t: t["time"])

    edges = pd.date_range(overall_start, overall_end, periods=args.folds + 1)

    w(f"\nConfronto per fetta: gambe (per simbolo, moduli arbitrati come nel live) "
      f"vs COMBINATO (stessa size reale).\n")

    fold_combined = []
    for k in range(args.folds):
        lo, hi = edges[k], edges[k + 1]
        w(f"--- Fetta {k+1}/{args.folds}: {lo.date()} -> {hi.date()} ---")
        per_leg_dd_sum = 0.0
        for grp in groups:
            rows = [t for t in grp.trades if lo <= t["time"] < hi]
            s = _stats(rows)
            per_leg_dd_sum += s["max_dd"]
            w(f"  {grp.label:<20} {_fmt(s)}")
        combo_rows = [t for t in all_trades if lo <= t["time"] < hi]
        combo_stats = _stats(combo_rows)
        fold_combined.append(combo_stats)
        w(f"  {'COMBINATO':<20} {_fmt(combo_stats)}")
        diversif = per_leg_dd_sum - combo_stats["max_dd"]
        w(f"  DD somma gambe = {per_leg_dd_sum:.2f}% | DD combinato = {combo_stats['max_dd']:.2f}% | "
          f"beneficio diversificazione = {diversif:+.2f}%\n")

    # Correlazione giornaliera tra le gambe (per simbolo, sull'intera sovrapposizione)
    w("=== Correlazione giornaliera tra le gambe (intera sovrapposizione) ===")
    series = {}
    for grp in groups:
        rows = [t for t in grp.trades if overall_start <= t["time"] <= overall_end]
        series[grp.label] = daily_series(rows)
    labels = list(series)
    if len(labels) >= 2:
        idx = pd.date_range(overall_start.date(), overall_end.date(), freq="D")
        aligned = {lb: series[lb].reindex(idx, fill_value=0.0) for lb in labels}
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                a, b = aligned[labels[i]], aligned[labels[j]]
                corr = float(np.corrcoef(a.values, b.values)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0
                w(f"  corr({labels[i]}, {labels[j]}) = {corr:+.3f}")
    else:
        w("  (una sola gamba: nessuna correlazione da calcolare)")

    # Concorrenza: quante posizioni aperte simultaneamente nel portafoglio combinato
    w("\n=== Posizioni aperte simultaneamente (portafoglio combinato, intera sovrapposizione) ===")
    cc = concurrency_stats(all_trades)
    w(f"  Max posizioni aperte insieme: {cc['max_concurrent']} (limite live: "
      f"config.PORTFOLIO_MAX_POSITIONS={config.PORTFOLIO_MAX_POSITIONS})")
    w(f"  Media posizioni aperte (pesata nel tempo): {cc['avg_concurrent']}")
    w(f"  % di tempo con 2+ posizioni aperte insieme: {cc['pct_time_with_2plus']}%")

    # Verdetto
    n_pos = sum(1 for s in fold_combined if s["total"] > 0)
    recent = fold_combined[-1]
    w("\n=== SINTESI ===")
    for k, s in enumerate(fold_combined):
        w(f"  Fetta {k+1}: {_fmt(s)}")
    w(f"  Fette combinate positive: {n_pos}/{len(fold_combined)} | piu' recente: "
      f"tot={recent['total']:.2f}% PF={recent['pf']:.2f} DD={recent['max_dd']:.2f}%")
    if recent["total"] <= 0:
        verdict = ("NON VALIDA: la fetta piu' recente del portafoglio combinato e' in perdita "
                   "-> non validare la combinazione.")
    elif n_pos == len(fold_combined):
        verdict = "VALIDA: il portafoglio combinato e' positivo e consistente in TUTTE le fette."
    elif n_pos >= (len(fold_combined) + 1) // 2:
        verdict = "INCERTA: il portafoglio combinato e' positivo solo in parte delle fette."
    else:
        verdict = "NON VALIDA: il portafoglio combinato e' negativo nella maggioranza delle fette."
    w(f"  VERDETTO: {verdict}")

    json_path = out_dir / f"walkforward_portfolio_{tag}.json"
    json_path.write_text(json.dumps({
        "legs": [grp.label for grp in groups],
        "risk_profile": config.RISK_PROFILE,
        "years": args.years, "folds": args.folds,
        "overlap_start": str(overall_start.date()), "overlap_end": str(overall_end.date()),
        "fold_combined": fold_combined,
        "concurrency": cc,
        "verdict": verdict,
        "timestamp": datetime.utcnow().isoformat(),
    }, indent=2), encoding="utf-8")
    w(f"\nRisultati salvati in: {log_path.name} e {json_path.name}")


if __name__ == "__main__":
    main()
