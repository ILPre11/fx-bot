"""Interfaccia comune agli esecutori di segnali."""
from __future__ import annotations

from abc import ABC, abstractmethod

from forex_bot.models import Signal


class Executor(ABC):
    """Consuma un Signal: lo mostra e/o, in futuro, invia l'ordine."""

    @abstractmethod
    def handle(self, signal: Signal, symbol_info=None) -> None:
        raise NotImplementedError
