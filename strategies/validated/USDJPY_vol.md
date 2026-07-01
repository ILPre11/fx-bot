# USDJPY — Volatility Breakout

- **Modulo**: `vol` (Vol Breakout: compressione bande di Bollinger + rottura Donchian)
- **Parametri**: DEFAULT, nessuna ottimizzazione — `optimizer/fast_backtest.DEFAULT_PARAMS`
  (chiavi `vol_*`, `compression_percentile`) + periodi indicatori in `DEFAULT_PERIODS`, invariati.
- **Uscita**: TP a R:R fisso + time-stop, da `config.EXIT_RR=2.0` / `config.EXIT_MAX_BARS=120`.
- **Rischio per trade**: `risk_vol_pct` del profilo attivo — **1.80%** con `ultra_aggressive_5k`.
- **Nel live**: attiva in `config.VALIDATED_STRATEGIES["USDJPY"] = ["vol"]`.

## Profilo di rischio (8 anni, `optimizer/validate_one.py`, 2026-07-01)

| Metrica | Valore |
|---|---|
| Trade totali | 164 (112 long / 52 short) |
| Total R | +28.0 R |
| Profit Factor | 1.28 |
| Win rate | 39% |
| Payoff (vincita media / perdita media) | 2.00 (+2.00R / -1.00R) |
| Max drawdown | 11.0 R |
| Peggior serie di perdite | 6 |
| Recupero (Total R / DD) | 2.55× |
| Long | 45/112 vinti, +23.0 R |
| Short | 19/52 vinti, +5.0 R |
| Anni positivi | 6/9 (2018-2026) |

Bias direzionale long (112 long vs 52 short) — complementare a NZDUSD Trend
(bilanciata) e NZDUSD VOL (bias short), utile per la diversificazione di
portafoglio. Nota: 2026 (parziale) a -3R, coerente con l'annata mista vista
anche nella validazione storica.

**Sensibilità parametri**: plateau su tutti e 5 i parametri testati (Total R
resta positivo variando ±2 step attorno al default) → edge reale, non un
punto fortunato.

## Walk-forward anchored (8 anni, 3 fette, parametri DEFAULT, 2026-07-01)

| Fetta | Periodo TEST | Trade | PF | Total R |
|---|---|---|---|---|
| 1 | 2020-10 → 2022-09 | 40 | 1.64 | +14.0 |
| 2 | 2022-09 → 2024-08 | 42 | 1.36 | +9.0 |
| 3 | 2024-08 → 2026-07 | 43 | 1.44 | +11.0 |

**3/3 fette OOS positive**, nessun declino nella fetta più recente.

Fonte dati: `optimizer/walkforward_USDJPY_vol.log` / `.json`
(rigenerabile con `python -m optimizer.walk_forward --symbol USDJPY --modules vol --space vol`).
