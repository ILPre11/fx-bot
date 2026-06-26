"""Esecutore 'manuale': non invia ordini, mostra solo come aprire la posizione.

E' la modalita' attuale del progetto (solo segnali).
"""
from __future__ import annotations

from forex_bot.executors.base import Executor
from forex_bot.models import Signal
from forex_bot.output import format_signal


class ManualExecutor(Executor):
    def handle(self, signal: Signal, symbol_info=None) -> None:
        print(format_signal(signal, symbol_info))
