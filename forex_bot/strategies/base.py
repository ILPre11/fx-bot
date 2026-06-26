"""Interfaccia comune a tutte le strategie."""
from __future__ import annotations

from abc import ABC, abstractmethod

from forex_bot.models import MarketData, TradeIdea


class Strategy(ABC):
    """Una strategia trasforma i dati di mercato in un'idea di trade (o None)."""

    name: str = "base"
    # Timeframe di cui la strategia ha bisogno; il main li scarica e li passa.
    required_timeframes: list[str] = ["H1"]

    @abstractmethod
    def generate(self, data: MarketData) -> TradeIdea | None:
        """Restituisce una TradeIdea oppure None se non c'e' alcun segnale."""
        raise NotImplementedError
