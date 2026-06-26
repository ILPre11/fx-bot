"""
Backtest engine per-modulo per-simbolo.

Scarica dati storici H1/H4 da MT5 e simula le combo (module, symbol) riciclando
la logica di segnale gia' portata in Python (FxMultiRegimeStrategy).

Approssimazioni intenzionali:
  - Prezzo d'ingresso = close della barra del segnale (in live e' il tick del broker)
  - TP derivato da SL con R:R fisso (la strategia non fissa TP numerici)
  - Spread ignorato
  - Un trade alla volta per combo (no piramidazione)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from forex_bot.models import MarketData, Side
from forex_bot.strategies.fx_multi_regime import (
    FxMultiRegimeStrategy,
    MODULE_TREND, MODULE_ASIA, MODULE_MEANREV, MODULE_VOL,
)

WARMUP = 230       # barre H1 di warmup (periodo max 200 + margine)
BACKTEST_RR = 2.0  # R:R usato per il TP fisso nel backtest
MAX_BARS_OPEN = 120  # time-stop: chiude dopo N barre se niente SL/TP

# Finestre scorrevoli: la strategia guarda al massimo ~210 barre H1 e ~210 H4
# indietro. Passare solo l'ultima finestra (invece dell'intera storia ad ogni
# barra) rende il loop O(n) invece di O(n^2) -> backtest su anni in minuti.
H1_WINDOW = 360
H4_WINDOW = 280
SERVER_OFFSET = 3  # Vantage UTC+3; usato per convertire l'ora barra in UTC (modulo Asia)


@dataclass
class TradeResult:
    module: int
    symbol: str
    side: str
    pnl_r: float   # P&L in R (1 R = distanza entry-SL)
    won: bool
    bars_held: int


def _make_strategy(module_id: int) -> FxMultiRegimeStrategy:
    s = FxMultiRegimeStrategy()
    s.use_trend = module_id == MODULE_TREND
    s.use_mean_rev = module_id == MODULE_MEANREV
    s.use_vol = module_id == MODULE_VOL
    s.use_asia = module_id == MODULE_ASIA
    return s


def _simulate_exit(
    h1: pd.DataFrame, entry_idx: int, entry: float, sl: float, tp: float, side: Side
) -> tuple[float, int]:
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0, 0
    end_idx = min(entry_idx + MAX_BARS_OPEN + 1, len(h1))
    for i in range(entry_idx + 1, end_idx):
        lo = float(h1.iloc[i]["low"])
        hi = float(h1.iloc[i]["high"])
        if side == Side.BUY:
            if lo <= sl:
                return -1.0, i - entry_idx
            if hi >= tp:
                return BACKTEST_RR, i - entry_idx
        else:
            if hi >= sl:
                return -1.0, i - entry_idx
            if lo <= tp:
                return BACKTEST_RR, i - entry_idx
    # time-stop
    last = min(entry_idx + MAX_BARS_OPEN, len(h1) - 1)
    last_close = float(h1.iloc[last]["close"])
    pnl_r = (last_close - entry) / risk if side == Side.BUY else (entry - last_close) / risk
    return round(pnl_r, 4), MAX_BARS_OPEN


def run(symbol: str, h1: pd.DataFrame, h4: pd.DataFrame, module_id: int) -> list[TradeResult]:
    """Testa una combo (module, symbol) su dati storici. Ritorna lista di trade."""
    strategy = _make_strategy(module_id)
    results: list[TradeResult] = []
    open_until = -1  # non aprire nuovi trade mentre siamo in posizione

    h4_times = h4["time"].values  # per ricerca veloce dell'indice H4

    for i in range(WARMUP, len(h1) - 2):
        if i <= open_until:
            continue

        current_time = h1["time"].iloc[i]
        # finestra H1: ultime H1_WINDOW barre fino a i (inclusa)
        h1_slice = h1.iloc[max(0, i + 1 - H1_WINDOW): i + 1]

        # finestra H4: barre con time <= current_time, ultime H4_WINDOW
        h4_count = int((h4_times <= current_time.to_datetime64()).sum())
        if h4_count < 30:
            continue
        h4_slice = h4.iloc[max(0, h4_count - H4_WINDOW): h4_count]

        close = float(h1_slice["close"].iloc[-1])
        as_of_utc = current_time - pd.Timedelta(hours=SERVER_OFFSET)
        data = MarketData(
            symbol=symbol,
            bid=close,
            ask=close,
            rates={"H1": h1_slice, "H4": h4_slice},
            server_utc_offset=SERVER_OFFSET,
            as_of=as_of_utc,
        )

        try:
            idea = strategy.generate(data)
        except Exception:
            continue

        if idea is None or idea.side == Side.FLAT:
            continue

        entry = close
        sl = idea.stop_loss
        risk = abs(entry - sl)
        if risk <= 0:
            continue

        tp = (entry + BACKTEST_RR * risk if idea.side == Side.BUY
              else entry - BACKTEST_RR * risk)
        pnl_r, bars = _simulate_exit(h1, i, entry, sl, tp, idea.side)

        results.append(TradeResult(
            module=module_id,
            symbol=symbol,
            side=idea.side.value,
            pnl_r=pnl_r,
            won=pnl_r > 0,
            bars_held=bars,
        ))
        open_until = i + bars

    return results


def compute_stats(results: list[TradeResult]) -> dict:
    if not results:
        return {
            "num_trades": 0, "pf": 0.0, "win_rate": 0.0,
            "sharpe": 0.0, "total_r": 0.0,
        }

    pnls = [r.pnl_r for r in results]
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]

    gross_profit = sum(wins)
    gross_loss = sum(losses)
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    total = sum(pnls)
    mean = total / len(pnls)
    std = float(np.std(pnls)) if len(pnls) > 1 else 0.0
    # Sharpe annualizzato (dati hourly: 252 giorni * ~16h trading)
    sharpe = mean / std * math.sqrt(252 * 16) if std > 0 else 0.0

    return {
        "num_trades": len(results),
        "pf": round(pf, 3),
        "win_rate": round(len(wins) / len(pnls), 3),
        "sharpe": round(sharpe, 2),
        "total_r": round(total, 2),
    }
