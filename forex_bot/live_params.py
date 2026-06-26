"""
Carica i parametri ottimizzati per-simbolo (prodotti da optimizer/global_search
o param_search) e li rende disponibili al path live.

File attesi: optimizer/best_params_<SYMBOL>.json con chiavi:
  - "params"  : soglie + rr + max_bars_open
  - "periods" : periodi indicatori
  - "stats"   : statistiche del backtest (informative)
"""
from __future__ import annotations

import json
from pathlib import Path

_OPT_DIR = Path(__file__).parent.parent / "optimizer"


def load_optimized(symbol: str) -> dict | None:
    """Ritorna un dict piatto {param: valore} per il simbolo, o None se assente.

    Unisce 'params' e 'periods'. Pronto per FxMultiRegimeStrategy.apply_optimized().
    """
    path = _OPT_DIR / f"best_params_{symbol}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    flat: dict = {}
    flat.update(data.get("periods", {}))
    flat.update(data.get("params", {}))
    return flat or None


def optimized_summary(symbol: str) -> str | None:
    """Riga riassuntiva (stats) per il log, o None se non c'e' un file ottimizzato."""
    path = _OPT_DIR / f"best_params_{symbol}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = data.get("stats", {})
        return (f"{symbol}: ottimizzato (trade={s.get('num_trades','?')}, "
                f"PF={s.get('pf','?')}, R={s.get('total_r','?')})")
    except Exception:
        return None
