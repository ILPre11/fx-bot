# Portafoglio a 5 gambe — NZDUSD Trend+VOL, USDJPY VOL, EURJPY VOL, CADJPY VOL

Configurazione live attiva dal **2026-08-01** (`config.VALIDATED_STRATEGIES`).
Sostituisce il portafoglio a 2 gambe ([portfolio_NZDUSD-trend_USDJPY-vol.md](portfolio_NZDUSD-trend_USDJPY-vol.md)).

**Motivo del cambio: flusso di ordini.** In 3 settimane di demo il bot non aveva
aperto nessuna posizione. Con 2 gambe il ritmo atteso è ~3,8 trade/mese, quindi
i 20-30 trade necessari a decidere demo→reale richiedevano 6-8 mesi di uptime
continuo. Con 5 gambe si passa a ~8,8/mese → ~3 mesi.

## Perché aggiungere gambe (e non allargare i filtri)

Misurato su 8 anni, per ogni gamba (`slot%` = quota di tempo con la posizione aperta):

| Gamba | segnali | trade | persi per slot occupato | durata media | slot% | trade/mese |
|---|---|---|---|---|---|---|
| NZDUSD TREND | 266 | 168 | 98 | 23 h | 8% | 1,8 |
| USDJPY VOL | 208 | 165 | 43 | 15 h | 5% | 1,8 |
| NZDUSD VOL | 160 | 125 | 35 | 14 h | 4% | 1,3 |
| EURJPY VOL | 223 | 176 | 47 | 17 h | 6% | 1,9 |
| CADJPY VOL | 201 | 148 | 53 | 17 h | 5% | 1,1 |

Lo slot per simbolo (`risk/portfolio_layer.py`, `MAX_PER_SYMBOL=1`) è occupato
solo il **4-8% del tempo**: il vincolo "1 posizione per simbolo" NON è il collo
di bottiglia. Il tappo è la **rarità del segnale** — ogni gamba spara ~1,5
volte al mese e basta. Di conseguenza le gambe si sommano quasi linearmente e
il modo corretto di aumentare gli ordini è aggiungerne, non allentare le soglie
d'ingresso (che invaliderebbe la validazione walk-forward di ogni gamba).

## Walk-forward di portafoglio (8 anni, 3 fette, DEFAULT, 2026-08-01)

Confronto a parità di dati e di confini delle fette. Fetta più recente:
2024-01-13 → 2026-07-31 (30,6 mesi).

| Config | trade (fetta 3) | trade/mese | PF | Totale | DD fetta 3 | DD fetta 1 | Verdetto |
|---|---|---|---|---|---|---|---|
| 2 gambe (precedente) | 117 | 3,8 | 1,35 | +52,3% | 16,4% | 24,0% | VALIDA 3/3 |
| 3 gambe (+NZDUSD vol) | 153 | 5,0 | 1,40 | +73,9% | 18,2% | 21,5% | VALIDA 3/3 |
| 4 gambe (+CADJPY vol) | 203 | 6,6 | 1,41 | +97,3% | 25,4% | 23,6% | VALIDA 3/3 |
| **5 gambe (+EURJPY vol)** | **268** | **8,8** | **1,31** | **+97,8%** | **20,9%** | **35,5%** | **VALIDA 3/3** |

Dettaglio della configurazione attiva a 5 gambe:

| Fetta | Periodo | Trade | PF | Totale | DD combinato | DD somma gambe |
|---|---|---|---|---|---|---|
| 1 | 2018-12 → 2021-06 | 218 | 1,14 | +38,4% | 35,5% | 64,3% |
| 2 | 2021-06 → 2024-01 | 250 | 1,65 | +171,3% | 18,7% | 41,0% |
| 3 | 2024-01 → 2026-07 | 268 | 1,31 | +97,8% | 20,9% | 61,4% |

- **3/3 fette positive** → VALIDA.
- **Correlazioni tra gambe: da -0,011 a +0,116** (tutte praticamente indipendenti).
- **Diversificazione reale**: DD combinato sempre molto sotto la somma dei DD
  delle gambe (+28,8% / +22,3% / +40,5% di beneficio per fetta).
- **Concorrenza**: max 4 posizioni aperte insieme in 8 anni (limite live
  `PORTFOLIO_MAX_POSITIONS=6`), 2+ posizioni solo il 3,26% del tempo.

## Prezzo da pagare e limiti noti

- **Drawdown più alto nella fetta peggiore**: fetta 1 passa da 24,0% (2 gambe)
  a 35,5%. Sul profilo `ultra_aggressive_5k` (2,50%/1,80% per trade) è un
  drawdown severo. Se è troppo, la variante a 3 gambe ha DD fetta 1 di 21,5%
  (più basso dell'attuale a 2 gambe) e comunque 5,0 trade/mese.
- **EURJPY VOL è piatta di recente**: nella fetta 3 fa PF 1,01, +0,48%. Aggiunge
  ~1,9 trade/mese a valore atteso ≈ 0 sull'ultimo periodo. Va bene per
  accumulare campioni nel test demo, non è un contributo di edge. È la prima
  gamba da togliere se si vuole ridurre il rischio.
- **CADJPY VOL è piatta nella fetta 1** (PF 1,00 su 18 trade), buona nelle
  fette 2 e 3.
- **CADJPY non è nell'elenco `symbols` del profilo di rischio**: non è un
  problema (`config.SYMBOLS` deriva da `VALIDATED_STRATEGIES`, la chiave
  `symbols` del profilo non è letta da nessuna parte), ma è un'incoerenza da
  tenere presente se un giorno quella chiave tornasse in uso.

## Come tornare indietro

Togliere gambe da `config.VALIDATED_STRATEGIES`:
senza `EURJPY` → 4 gambe; senza `EURJPY` e `CADJPY` → 3 gambe;
rimettendo `"NZDUSD": ["trend"]` → configurazione originale a 2 gambe.

Fonte dati: `optimizer/walkforward_portfolio_NZDUSD-trend+vol_USDJPY-vol_EURJPY-vol_CADJPY-vol.{log,json}`
e le varianti a 2/3/4 gambe negli altri `walkforward_portfolio_*.log`.
Rigenerabile con:

```
python -m optimizer.walk_forward_portfolio --legs NZDUSD:trend,USDJPY:vol,NZDUSD:vol,EURJPY:vol,CADJPY:vol --years 8 --folds 3
```
