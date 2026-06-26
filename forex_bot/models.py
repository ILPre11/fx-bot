"""Modelli dati condivisi: dati di mercato, idea di trade e segnale finale."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    FLAT = "FLAT"  # nessun segnale


@dataclass
class MarketData:
    """Dati di mercato per un simbolo, su uno o piu' timeframe.

    `rates` mappa il nome del timeframe ("H1", "H4", ...) al relativo DataFrame
    (colonne: time, open, high, low, close, tick_volume, ...). L'ultima riga di
    ogni DataFrame e' la candela ancora in formazione (shift 0); la -2 e'
    l'ultima chiusa (shift 1), come nell'EA.
    """

    symbol: str
    bid: float
    ask: float
    rates: dict
    symbol_info: object = None
    server_utc_offset: int = 0
    as_of: object = None  # "adesso" in UTC (tz-naive); None=usa l'orologio reale (live)

    def df(self, timeframe: str):
        return self.rates[timeframe]


@dataclass
class TradeIdea:
    """Idea grezza prodotta da una strategia (senza dimensione della posizione)."""

    side: Side
    entry: float
    stop_loss: float
    take_profit: float = 0.0          # 0 = nessun TP fisso (uscita gestita altrove)
    reason: str = ""
    risk_pct: float | None = None     # override rischio per-segnale (frazione, es. 0.0045)


@dataclass
class Signal:
    """Segnale completo pronto da mostrare (o, in futuro, da eseguire)."""

    symbol: str
    timeframe: str
    side: Side
    entry: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_amount: float
    risk_pct: float
    reason: str
    bar_time: datetime

    @property
    def risk_reward(self) -> float:
        if self.take_profit <= 0:
            return 0.0
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit - self.entry)
        return reward / risk if risk else 0.0
