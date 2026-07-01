# NZDUSD — Trend Pullback

- **Modulo**: `trend` (Trend Pullback, ingressi H1 + filtro regime H4)
- **Parametri**: DEFAULT, nessuna ottimizzazione — `optimizer/fast_backtest.DEFAULT_PARAMS`
  (chiavi `trend_*`) + periodi indicatori in `DEFAULT_PERIODS`, invariati.
- **Uscita**: TP a R:R fisso + time-stop, da `config.EXIT_RR=2.0` / `config.EXIT_MAX_BARS=120`
  (applicati anche nel live: di default la strategia non mette né TP né time-stop).
- **Rischio per trade**: `risk_trend_pct` del profilo attivo — **2.50%** con `ultra_aggressive_5k`.
- **Nel live**: attiva in `config.VALIDATED_STRATEGIES["NZDUSD"] = ["trend"]`.

## Profilo di rischio (8 anni, `optimizer/validate_one.py`, 2026-07-01)

| Metrica | Valore |
|---|---|
| Trade totali | 170 (57 long / 113 short) |
| Total R | +32.7 R |
| Profit Factor | 1.32 |
| Win rate | 40% |
| Payoff (vincita media / perdita media) | 1.98 (+1.98R / -1.00R) |
| Max drawdown | 9.0 R |
| Peggior serie di perdite | 9 |
| Recupero (Total R / DD) | 3.63× |
| Long | 27/57 vinti, +22.7 R |
| Short | 41/113 vinti, +10.0 R |
| Anni positivi | 7/9 (2018-2026) |

Win rate basso (40%) ma payoff ~2:1 → tipico di un trend-follower sano
(poche vincite grandi coprono molte piccole perdite). Richiede disciplina:
serie di 9 perdite consecutive osservata storicamente.

**Sensibilità parametri**: plateau su tutti e 5 i parametri testati (Total R
resta positivo variando ±2 step attorno al default) → edge reale, non un
punto fortunato. Vedi output completo di `validate_one` per i dettagli.

## Walk-forward anchored (8 anni, 3 fette, parametri DEFAULT, 2026-07-01)

| Fetta | Periodo TEST | Trade | PF | Total R |
|---|---|---|---|---|
| 1 | 2020-10 → 2022-09 | 34 | 1.58 | +11.0 |
| 2 | 2022-09 → 2024-08 | 39 | 1.33 | +7.7 |
| 3 | 2024-08 → 2026-07 | 44 | 1.52 | +13.0 |

**3/3 fette OOS positive**, nessun declino nella fetta più recente → edge
attuale, non in via di esaurimento.

Fonte dati: `optimizer/walkforward_NZDUSD_trend.log` / `.json`
(rigenerabile con `python -m optimizer.walk_forward --symbol NZDUSD --modules trend --space trend`).
