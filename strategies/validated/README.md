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

## Combinazione di portafoglio

[portfolio_NZDUSD-trend_USDJPY-vol.md](portfolio_NZDUSD-trend_USDJPY-vol.md) —
le due gambe sopra unite con la size reale (profilo `ultra_aggressive_5k`):
walk-forward di portafoglio 3/3 fette positive, correlazione giornaliera ≈ 0,
diversificazione del drawdown reale (non correlazione nascosta).

## Candidate scartate o non ancora promosse

- **NZDUSD VOL** — validata singolarmente (WF 3/3, +6.3R PF1.34) ma valutata
  come 3ª gamba di portafoglio e **scartata**: non diversifica contro NZDUSD
  Trend (stesso simbolo, arbitrato allo stesso slot), aumenta il drawdown
  combinato in 2 fette su 3 a fronte di più rendimento. Vedi
  `optimizer/walkforward_NZDUSD_vol.{log,json}` e
  `optimizer/walkforward_portfolio_NZDUSD-trend+vol_USDJPY-vol.log` per i dati.
- **EURJPY VOL, EURUSD VOL, USDCHF VOL** — edge più debole/incoerente,
  esplorate ma non promosse. Vedi `optimizer/walkforward_{EURJPY,EURUSD,USDCHF}.log`.
- **EURJPY ensemble ottimizzato** (+126R in-sample) — **scartata**: walk-forward
  negativo (l'edge decade nel tempo, fetta più recente in perdita). Esempio di
  overfitting da NON ripetere.

## Come rigenerare le prove

```
python -m optimizer.validate_one --symbol NZDUSD --module trend --years 8
python -m optimizer.walk_forward --symbol NZDUSD --modules trend --space trend --years 8 --folds 3
python -m optimizer.walk_forward_portfolio --legs NZDUSD:trend,USDJPY:vol --years 8 --folds 3
```
