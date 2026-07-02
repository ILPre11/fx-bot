"""Esecutore automatico (PREDISPOSIZIONE per il futuro).

Mostra il segnale e invia realmente l'ordine a MetaTrader 5, ma SOLO su
conto demo. Oggi non e' attivo: si abilita con AUTO_EXECUTE=True in config.py.
"""
from __future__ import annotations

import MetaTrader5 as mt5

from forex_bot.executors.base import Executor
from forex_bot.models import Side, Signal
from forex_bot.output import format_signal


class Mt5Executor(Executor):
    def __init__(
        self,
        magic: int = 555000,
        deviation: int = 20,
        allow_live: bool = False,
        notifier=None,
    ) -> None:
        self.magic = magic
        self.deviation = deviation
        self.allow_live = allow_live  # protezione: di default opera solo su demo
        self.notifier = notifier      # alert Telegram su esito ordine (opzionale)

    def _alert(self, text: str) -> None:
        if self.notifier:
            try:
                self.notifier.send(text)
            except Exception:
                pass  # Telegram giu' non deve bloccare l'esecuzione

    def handle(self, signal: Signal, symbol_info=None) -> None:
        print(format_signal(signal, symbol_info))

        if signal.side is Side.FLAT or signal.lots <= 0:
            return

        account = mt5.account_info()
        if account is None:
            print("[Mt5Executor] Nessun account collegato: ordine annullato.")
            return
        is_demo = account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        if not is_demo and not self.allow_live:
            print("[Mt5Executor] Conto NON demo: esecuzione bloccata per sicurezza.")
            self._alert(f"🚨 {signal.symbol}: ordine BLOCCATO, il conto collegato "
                        "NON e' demo. Verifica il terminale MT5!")
            return

        tick = mt5.symbol_info_tick(signal.symbol)
        if tick is None:
            print(f"[Mt5Executor] Nessun prezzo per {signal.symbol}.")
            return

        if signal.side is Side.BUY:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.symbol,
            "volume": float(signal.lots),
            "type": order_type,
            "price": price,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "forex_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            detail = getattr(result, "comment", None) or mt5.last_error()
            print(f"[Mt5Executor] Ordine FALLITO: {detail}")
            self._alert(f"🚨 {signal.symbol} {signal.side.value}: ordine FALLITO "
                        f"({detail}). Controlla il terminale MT5.")
        else:
            print(f"[Mt5Executor] Ordine eseguito: ticket {result.order}, "
                  f"{signal.lots} lotti.")
            self._alert(f"✅ {signal.symbol} {signal.side.value} eseguito: "
                        f"{signal.lots} lotti, ticket {result.order}, "
                        f"SL {signal.stop_loss} / TP {signal.take_profit}.")
