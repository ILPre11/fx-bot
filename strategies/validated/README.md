# Registro strategie validate

Ogni file qui dentro è **una strategia validata**: coppia + modulo + parametri
DEFAULT (nessuna ottimizzazione — verificato più volte che ottimizzare peggiora
l'out-of-sample, vedi `optimizer/walk_forward.py`). I parametri DEFAULT vivono
nel codice, non qui: `optimizer/fast_backtest.DEFAULT_PARAMS` /
`DEFAULT_PERIODS`, più il modello di uscita in `config.EXIT_RR` /
`config.EXIT_MAX_BARS`. Questo registro raccoglie solo le **prove di
validazione** (risultati, non il codice) così da non doverle andare a
recuperare sparse tra `optimizer/walkforward_*.json` e i log.

Criteri per essere "validata":
1. **Walk-forward anchored, parametri DEFAULT, 3 fette OOS positive** (nessun
   fitting sul periodo di test).
2. **Sensibilità ai parametri**: il Total R resta positivo variando ogni
   parametro di ±2 step attorno al default (plateau, non punto fortunato).
3. **Profilo di rischio** accettabile: drawdown, serie di perdite, PF, anni
   positivi coerenti con lo stile trend/breakout.

## Strategie attive nel live (`config.VALIDATED_STRATEGIES`)

| File | Coppia | Modulo | Rischio/trade | Verdetto |
|---|---|---|---|---|
| [NZDUSD_trend.md](NZDUSD_trend.md) | NZDUSD | trend | 2.50% (`risk_trend_pct`) | Validata, 7/9 anni positivi, WF 3/3 |
| [USDJPY_vol.md](USDJPY_vol.md) | USDJPY | vol | 1.80% (`risk_vol_pct`) | Validata, 6/9 anni positivi, WF 3/3 |
| (vedi portafoglio) | NZDUSD | vol | 1.80% (`risk_vol_pct`) | Validata, 6/9 anni positivi, WF 3/3 |
| (vedi portafoglio) | EURJPY | vol | 1.80% (`risk_vol_pct`) | Attiva per flusso ordini — piatta nell'ultima fetta |
| (vedi portafoglio) | CADJPY | vol | 1.80% (`risk_vol_pct`) | Attiva, PF 1.40 storico, 6/9 anni |

## Combinazione di portafoglio

**Attiva dal 2026-08-01**: [portfolio_5_gambe.md](portfolio_5_gambe.md) — 5 gambe
(NZDUSD trend+vol, USDJPY vol, EURJPY vol, CADJPY vol), walk-forward 3/3 fette
positive, ~8,8 trade/mese contro i 3,8 della configurazione precedente.
Motivo del cambio: **flusso di ordini** (con 2 gambe servivano 6-8 mesi per
accumulare i 20-30 trade del test demo).

Configurazione precedente, ancora valida ma più lenta:
[portfolio_NZDUSD-trend_USDJPY-vol.md](portfolio_NZDUSD-trend_USDJPY-vol.md).

## Candidate scartate o non ancora promosse

- **NZDUSD VOL** — era stata scartata come 3ª gamba (drawdown combinato più alto
  in 2 fette su 3). **Decisione ribaltata il 2026-08-01**: rimisurata sui dati
  aggiornati a fine luglio e con gli stessi confini di fetta, la configurazione
  a 3 gambe ha DD nella fetta peggiore **più basso** di quella a 2 gambe
  (21,5% contro 24,0%), PF più alto e +1,2 trade/mese. Ora è attiva.
- **EURJPY VOL** — promossa il 2026-08-01 **per il flusso di ordini, non per
  l'edge**: miglior Total R storico (+48,3R, PF 1,48, 7/9 anni) ma nell'ultima
  fetta è piatta (PF 1,01). È la prima gamba da togliere per ridurre il rischio.
- **EURUSD VOL, USDCHF VOL** — edge più debole/incoerente (USDCHF VOL: +3,0R su
  8 anni, PF 1,03), esplorate ma non promosse. Vedi
  `optimizer/walkforward_{EURUSD,USDCHF}.log`.
- **EURJPY ensemble ottimizzato** (+126R in-sample) — **scartata**: walk-forward
  negativo (l'edge decade nel tempo, fetta più recente in perdita). Esempio di
  overfitting da NON ripetere.

## Come rigenerare le prove

```
python -m optimizer.validate_one --symbol NZDUSD --module trend --years 8
python -m optimizer.walk_forward --symbol NZDUSD --modules trend --space trend --years 8 --folds 3
python -m optimizer.walk_forward_portfolio --legs NZDUSD:trend,USDJPY:vol,NZDUSD:vol,EURJPY:vol,CADJPY:vol --years 8 --folds 3
```
