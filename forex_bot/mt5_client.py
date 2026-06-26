"""Wrapper attorno al pacchetto MetaTrader5: connessione e download dati."""
from __future__ import annotations

import datetime as _dt

import MetaTrader5 as mt5
import pandas as pd

from forex_bot.models import Side

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
}


class Mt5Error(RuntimeError):
    """Errore generico nella comunicazione con MetaTrader 5."""


class Mt5Client:
    """Connessione al terminale MT5 e accesso a conto, simboli e candele."""

    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        path: str | None = None,
    ) -> None:
        self.login = login
        self.password = password
        self.server = server
        self.path = path

    # --- ciclo di vita ------------------------------------------------------
    def connect(self) -> None:
        # 1. Attacca/avvia il terminale MT5 SENZA credenziali: cosi' si collega
        #    al terminale gia' aperto e loggato, evitando un nuovo login.
        ok = mt5.initialize(path=self.path) if self.path else mt5.initialize()
        if not ok:
            raise Mt5Error(
                "initialize() fallita: apri il terminale MetaTrader 5 e riprova. "
                f"Dettaglio: {mt5.last_error()}"
            )

        # 2. Se il terminale e' gia' loggato sul conto giusto, non serve altro.
        info = mt5.account_info()
        if info is not None and (not self.login or info.login == self.login):
            return

        # 3. Altrimenti prova il login esplicito con le credenziali del .env.
        if self.login and self.password and self.server:
            if mt5.login(self.login, password=self.password, server=self.server):
                return
            err = mt5.last_error()
            info = mt5.account_info()
            if info is not None:
                print(
                    f"[avviso] Login con le credenziali .env fallito ({err}); "
                    f"uso il conto gia' connesso nel terminale: {info.login}."
                )
                return
            mt5.shutdown()
            raise Mt5Error(
                f"login() fallito: {err}. Controlla LOGIN, PASSWORD e soprattutto "
                "SERVER nel file .env (dev'essere identico al nome in MT5), oppure "
                "fai prima il login manuale del conto demo nel terminale."
            )

        # 4. Nessuna credenziale e nessun conto connesso.
        mt5.shutdown()
        raise Mt5Error(
            "Nessun conto connesso e credenziali mancanti nel .env. "
            "Fai il login del conto demo in MT5 oppure compila il file .env."
        )

    def disconnect(self) -> None:
        mt5.shutdown()

    def __enter__(self) -> "Mt5Client":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()

    # --- info conto / simbolo ----------------------------------------------
    def account(self):
        info = mt5.account_info()
        if info is None:
            raise Mt5Error(f"account_info() fallita: {mt5.last_error()}")
        return info

    def is_demo(self) -> bool:
        return self.account().trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO

    def symbol(self, name: str):
        if not mt5.symbol_select(name, True):
            raise Mt5Error(f"Impossibile selezionare {name}: {mt5.last_error()}")
        mt5.symbol_info_tick(name)  # "sveglia" il simbolo appena selezionato
        info = mt5.symbol_info(name)
        if info is None:
            raise Mt5Error(f"symbol_info({name}) fallita: {mt5.last_error()}")
        return info

    def loss_per_lot(self, symbol: str, side: Side, entry: float,
                     stop_loss: float) -> float | None:
        """Perdita (valore assoluto, valuta del conto) per 1 lotto da entry a SL.

        La calcola il broker via order_calc_profit (gestisce le conversioni di
        valuta). Restituisce None se il dato non e' disponibile.
        """
        order_type = mt5.ORDER_TYPE_BUY if side is Side.BUY else mt5.ORDER_TYPE_SELL
        profit = mt5.order_calc_profit(order_type, symbol, 1.0, entry, stop_loss)
        return abs(profit) if profit is not None else None

    def tick(self, symbol: str):
        t = mt5.symbol_info_tick(symbol)
        if t is None:
            raise Mt5Error(f"symbol_info_tick({symbol}) fallita: {mt5.last_error()}")
        return t

    def server_utc_offset(self, reference_symbol: str) -> int | None:
        """Stima l'offset (in ore) del server rispetto a UTC dall'ultimo tick.

        Ritorna None se non determinabile in modo affidabile (es. tick vecchio
        nel weekend): in tal caso conviene impostare SERVER_UTC_OFFSET a mano.
        """
        tick = mt5.symbol_info_tick(reference_symbol)
        if tick is None or not tick.time:
            return None
        delta_h = (
            _dt.datetime.utcfromtimestamp(tick.time) - _dt.datetime.utcnow()
        ).total_seconds() / 3600.0
        offset = int(round(delta_h))
        return offset if -12 <= offset <= 14 else None

    # --- dati di mercato ----------------------------------------------------
    def rates(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        tf = TIMEFRAMES.get(timeframe.upper())
        if tf is None:
            raise Mt5Error(f"Timeframe non valido: {timeframe}")
        data = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if data is None or len(data) == 0:
            raise Mt5Error(f"Nessun dato per {symbol} {timeframe}: {mt5.last_error()}")
        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df
