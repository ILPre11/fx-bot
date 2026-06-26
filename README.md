# Forex Analyzer (MT5) — FX Multi-Regime

Analisi automatica del forex con **Python + MetaTrader 5**. Per ogni mercato
configurato il programma calcola un segnale e ti dice **come aprire la posizione**:
direzione, ingresso, stop loss e dimensione in lotti (sul rischio).

La strategia e' il port Python dell'EA **FX Multi-Regime Ensemble** (4 moduli:
Trend Pullback, Asia/London Breakout, Mean Reversion, Vol Breakout), con
arbitraggio tra i moduli e sizing sul rischio identico all'EA (`order_calc_profit`).

> Pensato per **conto DEMO / uso didattico**. Non e' consulenza finanziaria.

## Stato
- ✅ **Solo segnali**: il software analizza e propone l'operazione; la apri tu.
- ✅ Tutti e 4 i moduli portati e verificati + arbitraggio.
- 🔜 **Esecuzione automatica**: gia' predisposta (`AUTO_EXECUTE=True` in `config.py`,
  solo su conto demo). Mancano, per l'auto-trading completo, lo strato di
  risk-management di portafoglio e la gestione delle posizioni aperte; l'EA `.mq5`
  in `strategy/` resta il riferimento per il backtest nello Strategy Tester.

## Requisiti
- Windows con terminale **MetaTrader 5** aperto e loggato su un conto demo.
- Python 3.10+

## Installazione
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # poi inserisci le credenziali demo dentro .env
```

## Avvio
```powershell
# Analisi singola (una passata sui simboli)
.venv\Scripts\python.exe main.py

# Monitoraggio continuo: rianalizza a ogni nuova barra H1
.venv\Scripts\python.exe main.py --watch
.venv\Scripts\python.exe main.py --watch --interval 60
```
Tieni il terminale MT5 **aperto e connesso**: la libreria Python si collega a quello.

## Configurazione (`config.py`)
- `SYMBOLS`: i mercati da analizzare (default: 6 major dell'EA).
- `SERVER_UTC_OFFSET`: `None` = autorilevato; oppure forza un intero (es. 3).
- `RISK_PCT`: rischio di fallback; i moduli usano i propri (0.25%–0.45%).
- `AUTO_EXECUTE`: `True` per inviare gli ordini (solo demo).
- Credenziali demo → file `.env`.

## Struttura
```
config.py                 parametri operativi + credenziali (.env)
main.py                   CLI: analisi singola o --watch; orchestrazione
strategy/                 l'EA MQL5 originale (per il backtest nello Strategy Tester)
forex_bot/
  mt5_client.py           connessione, dati multi-TF, offset UTC, sizing broker
  indicators.py           EMA, RSI, ATR, ADX/±DI, Bollinger, Donchian, percentili
  models.py               Side, MarketData, TradeIdea, Signal
  risk.py                 calcolo dei lotti dal rischio %
  output.py               formattazione del segnale
  strategies/
    base.py               interfaccia Strategy (MarketData multi-TF)
    fx_multi_regime.py    port dell'EA: 4 moduli + arbitraggio
    ema_rsi_atr.py        esempio minimale di riferimento
  executors/
    base.py / manual.py   mostra il segnale (modalita' attuale)
    mt5_executor.py       invia l'ordine (futuro, solo demo)
```
