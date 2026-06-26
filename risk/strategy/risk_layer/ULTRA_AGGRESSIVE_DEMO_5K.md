# Portfolio Risk Layer - Ultra Aggressive Demo 5K

Profilo pensato solo per conto demo da 5.000. E molto piu aggressivo del profilo precedente e non e un profilo live.

## Budget rischio

| Voce | Percentuale | Equivalente su 5.000 |
|---|---:|---:|
| Trend Pullback | 2.50% | 125 |
| Asia/London Breakout | 1.80% | 90 |
| Volatility Breakout | 1.80% | 90 |
| Mean Reversion | 1.00% | 50 |
| Rischio totale aperto massimo | 12.00% | 600 |
| Rischio massimo concentrato su USD | 8.00% | 400 |
| Perdita giornaliera massima | 10.00% | 500 |
| Perdita settimanale massima | 20.00% | 1.000 |
| Soft drawdown | 15.00% | 750 |
| Hard drawdown | 30.00% | 1.500 |
| Stop modello / emergency close | 45.00% | 2.250 |

## Cosa cambia rispetto al profilo aggressivo

- Rischio trend da 1.00% a 2.50%.
- Rischio breakout da 0.75% a 1.80%.
- Rischio mean reversion da 0.50% a 1.00%.
- Rischio totale aperto da 5.00% a 12.00%.
- Stop giornaliero da 5.00% a 10.00%.
- Stop settimanale da 10.00% a 20.00%.
- Drawdown hard da 18.00% a 30.00%.
- Universo ampliato a 9 simboli.
- Margin guard piu permissiva: 180% corrente, 150% proiettata.

## Comportamento del layer

- Fino a 15% di drawdown: rischio normale.
- Da 15% a 30% di drawdown: l'EA dimezza automaticamente il rischio.
- Da 30% di drawdown: l'EA blocca nuovi ingressi.
- Da 45% di drawdown: l'EA chiude le posizioni della strategia e ferma il modello.
- Se la perdita giornaliera supera 10%: niente nuovi ingressi fino al giorno successivo.
- Se la perdita settimanale supera 20%: niente nuovi ingressi fino alla settimana successiva.

## Uso consigliato

1. Compila `FX_MultiRegime_Ensemble_MT5_UltraAggressive5K.mq5`.
2. Carica `profiles/FXMR_Ultra_Aggressive_Demo_5K.set`.
3. Testa prima ogni modulo separato.
4. Poi testa il sistema completo con real ticks, spread variabile, commissioni e swap.

## Bocciatura rapida

Boccia questo profilo se:

- drawdown OOS supera 45%,
- il margin level scende spesso sotto 180%,
- lo stress spread +25% distrugge la curva,
- il profitto arriva quasi tutto da una sola coppia,
- la mean reversion produce perdite di coda troppo grandi.
