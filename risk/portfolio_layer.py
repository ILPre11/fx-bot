"""
Risk layer di portafoglio per il trading live su demo.

Controlli implementati:
  - DD giornaliero: se equity scende >10% dal picco intraday → ferma tutto
  - Max posizioni aperte in portafoglio (default 6)
  - Max 1 posizione per simbolo
  - Friday cutoff: venerdì dopo le 20 UTC chiude tutto e blocca nuovi trade
"""
from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5

MAX_DAILY_DD: float = 0.10    # -10% dal picco giornaliero
MAX_OPEN_POSITIONS: int = 6
MAX_PER_SYMBOL: int = 1
FRIDAY_CUTOFF_HOUR: int = 20  # UTC

_equity_peak: float | None = None
_peak_date: str = ""


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def update_equity_peak(equity: float) -> None:
    global _equity_peak, _peak_date
    today = _today_utc()
    if _peak_date != today:
        # nuovo giorno: reset del picco
        _equity_peak = equity
        _peak_date = today
    elif _equity_peak is None or equity > _equity_peak:
        _equity_peak = equity


def is_daily_dd_breached(equity: float) -> bool:
    if _equity_peak is None or _equity_peak <= 0:
        return False
    return equity < _equity_peak * (1.0 - MAX_DAILY_DD)


def is_friday_cutoff() -> bool:
    now = datetime.now(timezone.utc)
    return now.weekday() == 4 and now.hour >= FRIDAY_CUTOFF_HOUR


def count_open_positions(magic: int | None = None) -> int:
    positions = mt5.positions_get()
    if not positions:
        return 0
    if magic is None:
        return len(positions)
    return sum(1 for p in positions if p.magic == magic)


def count_symbol_positions(symbol: str, magic: int | None = None) -> int:
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return 0
    if magic is None:
        return len(positions)
    return sum(1 for p in positions if p.magic == magic)


def can_trade(symbol: str, equity: float, magic: int | None = None) -> tuple[bool, str]:
    """Controlla tutti i filtri. Ritorna (True, '') se si può tradare, altrimenti (False, motivo)."""
    update_equity_peak(equity)

    if is_friday_cutoff():
        return False, "Friday cutoff (venerdì ≥20 UTC): nessun nuovo trade"

    if is_daily_dd_breached(equity):
        return False, (
            f"DD giornaliero superato: equity {equity:.2f} < picco "
            f"{_equity_peak:.2f} × {1-MAX_DAILY_DD:.0%}"
        )

    open_count = count_open_positions(magic)
    if open_count >= MAX_OPEN_POSITIONS:
        return False, f"Max posizioni raggiunte ({open_count}/{MAX_OPEN_POSITIONS})"

    sym_count = count_symbol_positions(symbol, magic)
    if sym_count >= MAX_PER_SYMBOL:
        return False, f"Già in posizione su {symbol}"

    return True, ""


def close_all_bot_positions(magic: int = 555000) -> int:
    """Chiude tutte le posizioni aperte dal bot (identificate dal magic number)."""
    closed = 0
    positions = mt5.positions_get()
    if not positions:
        return 0

    for pos in positions:
        if pos.magic != magic:
            continue
        if _close_position(pos, magic, "friday_cutoff"):
            closed += 1
    return closed


def _close_position(pos, magic: int, comment: str) -> bool:
    """Chiude una singola posizione a mercato. Ritorna True se eseguito."""
    tick = mt5.symbol_info_tick(pos.symbol)
    if tick is None:
        return False
    if pos.type == mt5.ORDER_TYPE_BUY:
        price, order_type = tick.bid, mt5.ORDER_TYPE_SELL
    else:
        price, order_type = tick.ask, mt5.ORDER_TYPE_BUY
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 20,
        "magic": magic,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(req)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"  [Portfolio] Chiuso {pos.symbol} ticket={pos.ticket} ({comment})")
        return True
    err = getattr(result, "comment", mt5.last_error()) if result else mt5.last_error()
    print(f"  [Portfolio] Errore chiusura {pos.symbol}: {err}")
    return False


def close_expired_positions(max_bars_by_symbol: dict, magic: int = 555000) -> int:
    """Time-stop: chiude le posizioni del bot aperte da piu' di max_bars barre H1.

    max_bars_by_symbol: {symbol: numero_massimo_di_barre_H1}.
    L'eta' si stima da (ora server - ora apertura) / 3600s.
    """
    positions = mt5.positions_get()
    if not positions:
        return 0
    closed = 0
    for pos in positions:
        if pos.magic != magic:
            continue
        limit = max_bars_by_symbol.get(pos.symbol)
        if not limit:
            continue
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None or not tick.time:
            continue
        elapsed_bars = (tick.time - pos.time) / 3600.0
        if elapsed_bars >= limit:
            if _close_position(pos, magic, f"time_stop_{int(elapsed_bars)}h"):
                closed += 1
    return closed
