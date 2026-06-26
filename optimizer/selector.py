"""
Seleziona le combo (module_id, symbol) con edge statistico dal backtest rolling.

Criteri configurabili:
  - PF >= MIN_PF
  - num_trades >= MIN_TRADES

Output: dict {module_id: [symbols_attivi]} da passare alla strategia live.
"""
from __future__ import annotations

import json
from pathlib import Path

MIN_PF = 1.5
MIN_TRADES = 15

RESULTS_PATH = Path(__file__).parent / "results.json"


def load_results() -> list[dict]:
    if not RESULTS_PATH.exists():
        return []
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_results(results: list[dict]) -> None:
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def select_active(
    results: list[dict],
    min_pf: float = MIN_PF,
    min_trades: int = MIN_TRADES,
) -> dict[int, list[str]]:
    """Ritorna {module_id: [symbols_attivi]} per le combo che passano i criteri."""
    active: dict[int, list[str]] = {}
    for r in results:
        if r.get("num_trades", 0) >= min_trades and r.get("pf", 0.0) >= min_pf:
            mod = r["module_id"]
            active.setdefault(mod, []).append(r["symbol"])
    return active


def print_table(results: list[dict]) -> None:
    header = f"{'Modulo':<12} {'Simbolo':<10} {'Trade':>6} {'PF':>6} {'WR':>6} {'Sharpe':>7} {'TotalR':>8} {'OK?':>5}"
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda x: x.get("pf", 0), reverse=True):
        ok = "✓" if r.get("num_trades", 0) >= MIN_TRADES and r.get("pf", 0.0) >= MIN_PF else ""
        print(
            f"{r.get('module_name','?'):<12} {r.get('symbol','?'):<10} "
            f"{r.get('num_trades',0):>6} {r.get('pf',0.0):>6.2f} "
            f"{r.get('win_rate',0.0):>6.1%} {r.get('sharpe',0.0):>7.2f} "
            f"{r.get('total_r',0.0):>8.1f} {ok:>5}"
        )
