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
    # (vedi strategy/risk_layer/ULTRA_AGGRESSIVE_DEMO_5K.md).
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

# --- Strategie VALIDATE da operare sul demo ---------------------------------
# Mappa coppia -> moduli attivi. Una strategia = coppia + modulo/i + parametri
# DEFAULT (validati walk-forward). NIENTE ottimizzazione: è stato verificato che
# ottimizzare peggiora l'out-of-sample. Moduli validi: "trend","vol","meanrev","asia".
#
# 2026-08-01: portato da 2 a 5 gambe per aumentare il FLUSSO DI ORDINI. Ogni
# gamba produce solo ~1,5-1,9 trade/mese e lo slot per simbolo risulta occupato
# appena il 4-8% del tempo -> il tappo non era il vincolo "1 posizione per
# simbolo", era la rarità del segnale, e le gambe si sommano quasi linearmente.
# Walk-forward di portafoglio (8 anni, 3 fette, fetta più recente 2024-01 -> 2026-07):
#   2 gambe: 117 trade (3,8/mese) PF 1.35 tot +52,3% DD 16,4%   VALIDA 3/3
#   3 gambe: 153 trade (5,0/mese) PF 1.40 tot +73,9% DD 18,2%   VALIDA 3/3
#   4 gambe: 203 trade (6,6/mese) PF 1.41 tot +97,3% DD 25,4%   VALIDA 3/3
#   5 gambe: 268 trade (8,8/mese) PF 1.31 tot +97,8% DD 20,9%   VALIDA 3/3  <-- attiva
# Prezzo da pagare: nella fetta 1 (2018-12 -> 2021-06, la peggiore) il DD passa
# da 24,0% a 35,5%. Per tornare indietro basta togliere gambe da questa mappa:
# senza "EURJPY" = 4 gambe, senza EURJPY e CADJPY = 3 gambe, ecc.
# Fonte: optimizer/walkforward_portfolio_*.log, strategies/validated/.
VALIDATED_STRATEGIES: dict[str, list[str]] = {
    "NZDUSD": ["trend", "vol"],  # Trend (WF 3/3, 7/9 anni) + VOL (WF 3/3, 6/9 anni)
    "USDJPY": ["vol"],           # USDJPY VOL   (WF 3/3, plateau parametri, 6/9 anni)
    "EURJPY": ["vol"],           # EURJPY VOL   (miglior Total R storico, 7/9 anni)
    "CADJPY": ["vol"],           # CADJPY VOL   (PF 1.40 storico, 6/9 anni)
}
SYMBOLS: list[str] = list(VALIDATED_STRATEGIES)
PAIR: str = SYMBOLS[0]   # default per gli script di ottimizzazione (--symbol)

# Modello di USCITA validato nel backtest: TP a R:R fisso + time-stop (barre H1).
# Va applicato anche al live, altrimenti la strategia non replica ciò che è stato
# validato (di default non mette nè TP nè time-stop).
EXIT_RR: float = 2.0
EXIT_MAX_BARS: int = 120

# Re-ottimizzazione notturna dei moduli: DISATTIVATA. Operiamo strategie validate
# fisse, non la selezione automatica dei moduli (approccio superato).
LIVE_NIGHTLY_REOPTIMIZE: bool = False

RISK_TREND_PCT: float = _PROFILE["risk_trend_pct"]
RISK_ASIA_PCT: float = _PROFILE["risk_asia_pct"]
RISK_VOL_PCT: float = _PROFILE["risk_vol_pct"]
RISK_MEAN_PCT: float = _PROFILE["risk_mean_pct"]

# --- Mercati / dati ----------------------------------------------------------
TIMEFRAME: str = "H1"      # (legacy) usato solo dalla strategia di esempio ema_rsi_atr
BARS: int = 500            # quante candele scaricare per i calcoli

# Timeframe su cui il monitoraggio (--watch) fa scattare una nuova analisi.
# DEVE restare "H1": gli ingressi sono su barra H1 (filtro regime su H4) e i
# trigger sono EVENTI di una singola barra (trend: close incrocia la EMA20
# proprio su quella barra; vol: rottura Donchian su quella barra). Con "H4" il
# bot rivaluta solo 1 barra H1 su 4 e i segnali nati sulle altre 3 vengono
# persi per sempre: misurato su 8 anni di storico (2026-08-01), 168 -> 61
# trade su NZDUSD trend e 165 -> 52 su USDJPY vol, con l'edge di USDJPY che
# crolla da +30.0 R a +2.0 R. Non e' solo "meno trade": e' un'altra strategia,
# non quella validata. Override da riga di comando con --watch-tf.
WATCH_TIMEFRAME: str = "H1"

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

# --- Monitoraggio / resilienza (modalita' --watch e --live) -------------------
# Riepilogo Telegram giornaliero: e' l'heartbeat del bot (un messaggio atteso
# al giorno: se non arriva, il bot non sta girando). 06 UTC = 8:00 italiane (estate).
DAILY_SUMMARY_HOUR_UTC: int = 6
# Log rotante dell'output (console + file, per il post-mortem di crash/riavvii).
LOG_FILE: str = "logs/bot.log"
LOG_MAX_BYTES: int = 5_000_000
LOG_BACKUPS: int = 3

# --- Portfolio Risk Layer (solo in modalita' live) ----------------------------
PORTFOLIO_MAX_DAILY_DD: float = 0.10   # -10% equity giornaliero → stop tutto
PORTFOLIO_MAX_POSITIONS: int = 6       # max posizioni aperte contemporaneamente
PORTFOLIO_FRIDAY_CUTOFF_HOUR: int = 20 # venerdì UTC: chiude tutto e smette

# Offset orario del server del broker rispetto a UTC (per i moduli a sessioni,
# es. Asia/London breakout). None = autorilevamento dall'ultimo tick, che pero'
# nel weekend (mercati chiusi) puo' sbagliare. Vantage rilevato a UTC+3 in orario
# di mercato (EEST), quindi lo fisso. In inverno (EET) potrebbe diventare 2.
SERVER_UTC_OFFSET: int | None = 3
