"""Strategia di esempio: EMA crossover + filtro RSI + stop/target su ATR.

Storico segnaposto, conforme alla nuova interfaccia multi-timeframe. Non piu'
usata di default (la strategia attiva e' FxMultiRegimeStrategy), ma utile come
riferimento minimale di una Strategy.
"""
from __future__ import annotations

import pandas as pd

from forex_bot import indicators as ind
from forex_bot.models import MarketData, Side, TradeIdea
from forex_bot.strategies.base import Strategy


class EmaRsiAtrStrategy(Strategy):
    name = "ema_rsi_atr"

    def __init__(
        self,
        timeframe: str = "H1",
        ema_fast: int = 12,
        ema_slow: int = 26,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0,
    ) -> None:
        self.timeframe = timeframe
        self.required_timeframes = [timeframe]
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate(self, data: MarketData) -> TradeIdea | None:
        df = data.df(self.timeframe)
        min_bars = max(self.ema_slow, self.rsi_period, self.atr_period) + 5
        if len(df) < min_bars:
            return None

        close = df["close"]
        ema_fast = ind.ema(close, self.ema_fast)
        ema_slow = ind.ema(close, self.ema_slow)
        rsi = ind.rsi(close, self.rsi_period)
        atr = ind.atr(df["high"], df["low"], close, self.atr_period)

        i = -2  # ultima barra chiusa
        price = float(close.iloc[i])
        a = float(atr.iloc[i])
        r = float(rsi.iloc[i])
        if pd.isna(a) or pd.isna(r) or a <= 0:
            return None

        trend_up = ema_fast.iloc[i] > ema_slow.iloc[i]
        trend_dn = ema_fast.iloc[i] < ema_slow.iloc[i]

        if trend_up and 50 <= r < 70:
            return TradeIdea(Side.BUY, price, price - a * self.sl_atr_mult,
                             price + a * self.tp_atr_mult,
                             f"EMA{self.ema_fast}>EMA{self.ema_slow}, RSI {r:.1f}")
        if trend_dn and 30 < r <= 50:
            return TradeIdea(Side.SELL, price, price + a * self.sl_atr_mult,
                             price - a * self.tp_atr_mult,
                             f"EMA{self.ema_fast}<EMA{self.ema_slow}, RSI {r:.1f}")
        return None
