"""Notifiche dei segnali via Telegram Bot API (solo libreria standard).

Serve un bot (creato con @BotFather) e l'id della chat di destinazione.
Token e chat id vanno nel file .env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from html import escape

from forex_bot.models import Signal
from forex_bot.output import format_signal

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: int = 10) -> None:
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout

    def _call(self, method: str, params: dict) -> dict:
        url = _API.format(token=self.token, method=method)
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(url, data=data, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def send(self, text: str) -> bool:
        """Invia un messaggio. Non solleva: in caso di errore di rete lo segnala
        e ritorna False, senza bloccare l'analisi."""
        try:
            res = self._call("sendMessage", {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            })
            if not res.get("ok"):
                print(f"[telegram] errore: {res.get('description')}")
            return bool(res.get("ok"))
        except Exception as exc:  # rete/timeout: non deve fermare il bot
            print(f"[telegram] invio fallito: {exc}")
            return False

    def send_signal(self, signal: Signal, symbol_info=None) -> bool:
        head = f"\U0001F514 <b>{escape(signal.symbol)} {signal.side.value}</b> ({signal.timeframe})"
        body = escape(format_signal(signal, symbol_info))
        return self.send(f"{head}\n<pre>{body}</pre>")

    def test(self) -> bool:
        return self.send("✅ Test notifiche FX Multi-Regime: connessione OK.")

    def detect_chats(self) -> list:
        """Elenca le chat che hanno scritto al bot (per trovare il chat id)."""
        res = self._call("getUpdates", {})
        out = []
        for upd in res.get("result", []):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if "id" in chat:
                name = chat.get("title") or chat.get("username") or chat.get("first_name")
                out.append((chat["id"], chat.get("type"), name))
        return out
