"""Monitoraggio della modalita' live: alert Telegram + riepilogo giornaliero.

Filosofia: pochi messaggi ATTESI (un riepilogo al giorno) + alert IMMEDIATI
solo sugli eventi che richiedono attenzione (Algo Trading spento, connessione
persa, DD sfondato, Friday cutoff, ordini falliti, errori inattesi). Se il
riepilogo giornaliero non arriva, il bot e' morto: e' il vero heartbeat.

Tutti i metodi sono sicuri senza notifier (stampano soltanto).
"""
from __future__ import annotations

from datetime import datetime, timezone

import MetaTrader5 as mt5

import config


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class LiveMonitor:
    def __init__(self, notifier=None) -> None:
        self.notifier = notifier
        self._algo_off = False
        self._dd_alert_date = ""
        self._cutoff_alert_date = ""
        # se l'ora del riepilogo di oggi e' gia' passata all'avvio, non
        # inviarlo subito (il messaggio di avvio copre gia' la giornata)
        now = datetime.now(timezone.utc)
        self._summary_date = _today() if now.hour >= config.DAILY_SUMMARY_HOUR_UTC else ""

    # --- invio ---------------------------------------------------------------
    def alert(self, text: str) -> None:
        try:
            print(f"[monitor] {text}")
        except UnicodeEncodeError:
            # console senza unicode (es. cp1252): le emoji non devono crashare
            print(f"[monitor] {text}".encode("ascii", "replace").decode("ascii"))
        if self.notifier:
            try:
                self.notifier.send(text)
            except Exception:
                pass  # Telegram giu' non deve fermare il bot

    # --- controlli per ciclo ---------------------------------------------------
    def check_algo_trading(self) -> bool:
        """True se il terminale puo' inviare ordini. Alert al cambio di stato:
        con Algo Trading spento gli ordini falliscono SILENZIOSAMENTE
        ('AutoTrading disabled by client'), scoperto sul campo il 2026-07-02."""
        info = mt5.terminal_info()
        allowed = bool(info and info.trade_allowed)
        if not allowed and not self._algo_off:
            self._algo_off = True
            self.alert("🚨 Algo Trading DISATTIVATO nel terminale MT5: il bot non "
                       "puo' inviare ordini. Riattiva il pulsante Algo Trading!")
        elif allowed and self._algo_off:
            self._algo_off = False
            self.alert("✅ Algo Trading di nuovo attivo: il bot puo' operare.")
        return allowed

    def daily_summary(self, acc) -> None:
        """Un messaggio al giorno all'ora config.DAILY_SUMMARY_HOUR_UTC:
        se non arriva, il bot non sta girando."""
        now = datetime.now(timezone.utc)
        if self._summary_date == _today() or now.hour < config.DAILY_SUMMARY_HOUR_UTC:
            return
        self._summary_date = _today()
        positions = [p for p in (mt5.positions_get() or []) if p.magic == config.MAGIC]
        if positions:
            pos_txt = ", ".join(
                f"{p.symbol} {'BUY' if p.type == mt5.ORDER_TYPE_BUY else 'SELL'} "
                f"{p.volume} ({p.profit:+.2f})" for p in positions)
        else:
            pos_txt = "nessuna"
        algo = "ON" if self.check_algo_trading() else "OFF (!)"
        self.alert(f"☀️ Bot vivo. Equity {acc.equity:.2f} {acc.currency} | "
                   f"posizioni: {pos_txt} | Algo Trading: {algo}")

    # --- eventi (dedup per giorno dove serve) ---------------------------------
    def dd_breached(self, equity: float) -> None:
        if self._dd_alert_date != _today():
            self._dd_alert_date = _today()
            self.alert(f"🛑 DD giornaliero -{config.PORTFOLIO_MAX_DAILY_DD:.0%} superato "
                       f"(equity {equity:.2f}): nessun nuovo trade fino a domani.")

    def friday_cutoff(self, closed: int) -> None:
        if self._cutoff_alert_date != _today():
            self._cutoff_alert_date = _today()
            self.alert(f"🌙 Friday cutoff: chiuse {closed} posizioni. "
                       "Bot in pausa fino a lunedi'.")
