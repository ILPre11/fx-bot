"""Calcolo della dimensione della posizione (lotti) in base al rischio."""
from __future__ import annotations

import math


def _round_to_step(lots: float, symbol_info) -> float:
    """Arrotonda i lotti allo step del simbolo e rispetta min/max."""
    step = symbol_info.volume_step or 0.01
    # round() prima di floor() per assorbire il rumore in virgola mobile,
    # altrimenti 0.5/0.01 = 49.9999... verrebbe troncato a 0.49 invece di 0.50.
    lots = math.floor(round(lots / step, 9)) * step
    lots = max(symbol_info.volume_min, min(lots, symbol_info.volume_max))
    decimals = len(str(step).split(".")[-1]) if "." in str(step) else 0
    return round(lots, decimals)


def lots_for_risk(balance: float, risk_pct: float, loss_per_lot: float,
                  symbol_info) -> float:
    """Lotti che rischiano `risk_pct` del saldo, data la perdita per 1 lotto allo SL.

    `loss_per_lot` e' in valuta del conto (idealmente da mt5.order_calc_profit).
    """
    if loss_per_lot <= 0:
        return symbol_info.volume_min
    risk_amount = balance * risk_pct
    return _round_to_step(risk_amount / loss_per_lot, symbol_info)


def position_size(balance: float, risk_pct: float, entry: float,
                  stop_loss: float, symbol_info) -> float:
    """Fallback senza MT5: stima la perdita per lotto da tick_value/tick_size.

    Meno affidabile di order_calc_profit (il tick_value puo' non essere ancora
    sincronizzato subito dopo aver selezionato il simbolo).
    """
    sl_distance = abs(entry - stop_loss)
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size
    if sl_distance <= 0 or not tick_size or not tick_value:
        return symbol_info.volume_min
    loss_per_lot = (sl_distance / tick_size) * tick_value
    return lots_for_risk(balance, risk_pct, loss_per_lot, symbol_info)
