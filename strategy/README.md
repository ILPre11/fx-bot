# FX Multi-Regime Ensemble MT5 - Ultra Aggressive Demo 5K

Questa cartella contiene la strategia MT5 multi-regime e un profilo di rischio ultra aggressivo per conto demo da 5.000.

## File

- `FX_MultiRegime_Ensemble_MT5.mq5`: versione base della strategia.
- `FX_MultiRegime_Ensemble_MT5_UltraAggressive5K.mq5`: versione con default ultra aggressivi.
- `profiles/FXMR_Ultra_Aggressive_Demo_5K.set`: preset MT5 da caricare nello Strategy Tester o sull'EA.
- `risk_layer/ULTRA_AGGRESSIVE_DEMO_5K.md`: spiegazione del layer di rischio.

## Installazione

Copia la cartella `strategy` in:

```text
<MQL5>/Experts/strategy/
```

Poi compila:

```text
FX_MultiRegime_Ensemble_MT5_UltraAggressive5K.mq5
```

## Primo test consigliato

```text
Chart: EURUSD H1
Model: Every tick based on real ticks
Deposit: 5.000
Preset: profiles/FXMR_Ultra_Aggressive_Demo_5K.set
```

Testa prima i moduli separati, poi il sistema completo.

## Avvertenza

Questo profilo e intenzionalmente molto aggressivo. E pensato per demo e stress test, non per live trading.
