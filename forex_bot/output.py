"""Formattazione leggibile di un segnale per la console."""
from __future__ import annotations

from forex_bot.models import Side, Signal


def _pip_size(symbol_info) -> float:
    # 1 pip = 10 punti sui simboli a 3/5 decimali, altrimenti 1 punto.
    point = symbol_info.point
    return point * (10 if symbol_info.digits in (3, 5) else 1)


def format_signal(signal: Signal, symbol_info=None) -> str:
    if signal.side is Side.FLAT:
        return f"[{signal.symbol} {signal.timeframe}] Nessun segnale al momento."

    has_tp = signal.take_profit and signal.take_profit > 0

    if symbol_info is not None:
        pip = _pip_size(symbol_info)
        digits = symbol_info.digits
        sl_pips = abs(signal.entry - signal.stop_loss) / pip
        pip_sl = f"  ({sl_pips:.0f} pips)"
        pip_tp = f"  ({abs(signal.take_profit - signal.entry) / pip:.0f} pips)" if has_tp else ""
    else:
        digits = 5
        pip_sl = pip_tp = ""

    fmt = f".{digits}f"
    tp_line = f"{signal.take_profit:{fmt}}{pip_tp}" if has_tp else "--  (uscita gestita dinamicamente)"
    rr_line = f"1:{signal.risk_reward:.1f}" if has_tp else "n/d (gestito dinamicamente)"

    lines = [
        "============== SEGNALE ==============",
        f" Simbolo    : {signal.symbol}  ({signal.timeframe})",
        f" Operazione : {signal.side.value}",
        f" Ingresso   : {signal.entry:{fmt}}  (a mercato)",
        f" Stop Loss  : {signal.stop_loss:{fmt}}{pip_sl}",
        f" Take Profit: {tp_line}",
        f" Lotti      : {signal.lots}",
        f" Rischio    : {signal.risk_pct * 100:.2f}%  ({signal.risk_amount:.2f})",
        f" R/R        : {rr_line}",
        f" Motivo     : {signal.reason}",
        f" Barra      : {signal.bar_time:%Y-%m-%d %H:%M} (chiusa)",
        "=====================================",
    ]
    return "\n".join(lines)
