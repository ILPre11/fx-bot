"""Configurazione centrale del progetto.

Tutti i parametri operativi stanno qui; le credenziali del conto demo
vengono lette dal file .env (vedi .env.example).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- Credenziali conto DEMO (da .env) ---------------------------------------
MT5_LOGIN: int = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD: str = os.getenv("MT5_PASSWORD", "")
MT5_SERVER: str = os.getenv("MT5_SERVER", "")
MT5_PATH: str | None = os.getenv("MT5_PATH") or None

# --- Notifiche Telegram (opzionali, da .env) --------------------------------
# Lascia vuoti per disattivarle. Vedi .env.example per come ottenerli.
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Profili di rischio ------------------------------------------------------
# Ogni profilo definisce i rischi per-modulo (in % dell'equity) e l'universo
# di simboli. Per cambiare profilo basta modificare RISK_PROFILE qui sotto.
RISK_PROFILES: dict = {
    "base": {
        "symbols": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "EURJPY"],
        "risk_trend_pct": 0.45,
        "risk_asia_pct": 0.35,
        "risk_vol_pct": 0.35,
        "risk_mean_pct": 0.25,
    },
    # Ultra Aggressive Demo 5K: SOLO conto demo / stress test, molto aggressivo
    # (vedi risk/strategy/risk_layer/ULTRA_AGGRESSIVE_DEMO_5K.md).
    "ultra_aggressive_5k": {
        "symbols": ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCHF", "EURJPY",
                    "USDCAD", "NZDUSD", "EURGBP"],
        "risk_trend_pct": 2.50,
        "risk_asia_pct": 1.80,
        "risk_vol_pct": 1.80,
        "risk_mean_pct": 1.00,
    },
}
RISK_PROFILE: str = "ultra_aggressive_5k"   # <-- profilo attivo (metti "base" per il conservativo)

_PROFILE = RISK_PROFILES[RISK_PROFILE]

# --- Coppia attiva -----------------------------------------------------------
# Il progetto lavora UNA coppia per volta: ottimizzazione, segnali e trading
# sono tutti focalizzati su questa coppia. Per cambiare coppia basta modificare
# PAIR qui sotto (deve esistere come simbolo nel broker) e rilanciare
# l'ottimizzatore su di essa. Per tornare al multi-coppia: SYMBOLS = _PROFILE["symbols"].
PAIR: str = "EURJPY"
SYMBOLS: list[str] = [PAIR]

RISK_TREND_PCT: float = _PROFILE["risk_trend_pct"]
RISK_ASIA_PCT: float = _PROFILE["risk_asia_pct"]
RISK_VOL_PCT: float = _PROFILE["risk_vol_pct"]
RISK_MEAN_PCT: float = _PROFILE["risk_mean_pct"]

# --- Mercati / dati ----------------------------------------------------------
TIMEFRAME: str = "H1"      # (legacy) usato solo dalla strategia di esempio ema_rsi_atr
BARS: int = 500            # quante candele scaricare per i calcoli

# Timeframe su cui il monitoraggio (--watch) fa scattare una nuova analisi.
# La logica dei segnali NON cambia (resta ingressi H1 + filtro H4 come l'EA):
# questo controlla solo OGNI QUANTO si ri-valuta. "H4" = 4 volte al giorno,
# "H1" = a ogni ora. Override da riga di comando con --watch-tf.
WATCH_TIMEFRAME: str = "H4"

# --- Gestione del rischio ----------------------------------------------------
RISK_PCT: float = 0.01     # 1% del saldo per operazione
SL_ATR_MULT: float = 1.5   # stop loss   = ingresso +/- ATR * questo
TP_ATR_MULT: float = 3.0   # take profit = ingresso +/- ATR * questo (R/R 1:2)

# --- Parametri della strategia di esempio (EMA + RSI + ATR) ------------------
EMA_FAST: int = 12
EMA_SLOW: int = 26
RSI_PERIOD: int = 14
ATR_PERIOD: int = 14

# --- Esecuzione --------------------------------------------------------------
# AUTO_EXECUTE=True invia ordini reali a MT5 (solo su conto demo).
# Con --live da CLI viene impostato a True automaticamente + viene attivato il
# portfolio risk layer (DD giornaliero, max posizioni, Friday cutoff).
AUTO_EXECUTE: bool = False
MAGIC: int = 555000        # identificativo degli ordini dell'app
DEVIATION: int = 20        # slippage massimo in punti

# --- Modalita' LIVE ----------------------------------------------------------
# Queste impostazioni vengono usate da main.py --live.
LIVE_OPTIMIZER_HOUR: int = 0    # ora UTC in cui scatta il re-eval notturno (mezzanotte)
LIVE_OPTIMIZER_BARS: int = 2000  # barre H1 usate dal backtest rolling (override in run_optimizer)

# --- Portfolio Risk Layer (solo in modalita' live) ----------------------------
PORTFOLIO_MAX_DAILY_DD: float = 0.10   # -10% equity giornaliero → stop tutto
PORTFOLIO_MAX_POSITIONS: int = 6       # max posizioni aperte contemporaneamente
PORTFOLIO_FRIDAY_CUTOFF_HOUR: int = 20 # venerdì UTC: chiude tutto e smette

# Offset orario del server del broker rispetto a UTC (per i moduli a sessioni,
# es. Asia/London breakout). None = autorilevamento dall'ultimo tick, che pero'
# nel weekend (mercati chiusi) puo' sbagliare. Vantage rilevato a UTC+3 in orario
# di mercato (EEST), quindi lo fisso. In inverno (EET) potrebbe diventare 2.
SERVER_UTC_OFFSET: int | None = 3
