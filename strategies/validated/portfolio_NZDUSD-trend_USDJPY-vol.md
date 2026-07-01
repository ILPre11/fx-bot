# Portafoglio — NZDUSD Trend + USDJPY VOL

Combinazione delle due strategie validate singolarmente ([NZDUSD_trend.md](NZDUSD_trend.md),
[USDJPY_vol.md](USDJPY_vol.md)), operata insieme con la size reale del profilo
di rischio attivo (`ultra_aggressive_5k`: 2.50%/trade su NZDUSD Trend, 1.80%/trade
su USDJPY VOL). Configurazione live: `config.VALIDATED_STRATEGIES` invariata.

## Walk-forward di portafoglio (8 anni, 3 fette calendariali, DEFAULT, 2026-07-01)

| Fetta | Periodo | Trade combinati | PF | Total (% equity) | DD combinato | DD somma gambe |
|---|---|---|---|---|---|---|
| 1 | 2018-11 → 2021-05 | 115 | 1.10 | +16.0% | 26.5% | 40.5% |
| 2 | 2021-05 → 2023-12 | 103 | 1.55 | +67.3% | 12.9% | 19.0% |
| 3 | 2023-12 → 2026-06 | 116 | 1.32 | +48.7% | 16.4% | 29.0% |

- **3/3 fette positive** → **VALIDA**.
- **Correlazione giornaliera tra le gambe: +0.02** (praticamente indipendenti).
- **Diversificazione reale**: il drawdown combinato è sempre nettamente più
  basso della somma dei drawdown delle gambe singole (beneficio +14%/+6%/+13%
  di equity in ogni fetta) — non è correlazione nascosta, è vera diversificazione.
- **Concorrenza posizioni**: max 2 posizioni aperte insieme in tutta la storia
  (limite live `config.PORTFOLIO_MAX_POSITIONS=6`), quindi nessun rischio di
  esposizione/margine oltre quanto già previsto dalle gambe singole.

## Candidata scartata: aggiungere NZDUSD VOL (3ª gamba)

Testata (2026-07-01) con `--legs NZDUSD:trend,USDJPY:vol,NZDUSD:vol`. Quando
più moduli condividono lo stesso simbolo vengono arbitrati come nel live
(`ChooseSignal`, 1 posizione alla volta per simbolo) — non sommati come gambe
indipendenti.

| Fetta | Total (% equity) | DD combinato |
|---|---|---|
| 1 | +15.3% | 24.0% |
| 2 | +81.7% | 15.8% |
| 3 | +64.9% | 20.8% |

Ancora 3/3 positiva, rendimento più alto, ma drawdown più alto in 2 fette su
3 (NZDUSD VOL non diversifica contro NZDUSD Trend, stesso simbolo/slot —
correlazione con USDJPY VOL comunque ~0.04, invariata). Il numero massimo di
posizioni aperte insieme resta 2 in entrambi gli scenari (non è un rischio di
esposizione, solo di drawdown/rendimento). **Decisione: scartata**, si
preferisce il drawdown più basso della combinazione a 2 gambe.

Fonte dati: `optimizer/walkforward_portfolio_NZDUSD-trend_USDJPY-vol.{log,json}`
e `optimizer/walkforward_portfolio_NZDUSD-trend+vol_USDJPY-vol.{log,json}`
(rigenerabile con `python -m optimizer.walk_forward_portfolio`).
