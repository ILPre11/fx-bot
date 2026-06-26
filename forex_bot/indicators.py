"""Indicatori tecnici in pandas puro (niente TA-Lib).

Implementazioni allineate a MetaTrader 5 (smoothing di Wilder dove previsto).
Funzioni indipendenti da MetaTrader: facili da testare in isolamento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Media mobile esponenziale."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI con smoothing di Wilder."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range con smoothing di Wilder."""
    return _true_range(high, low, close).ewm(alpha=1 / period, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, deviation: float = 2.0):
    """Bande di Bollinger (media + dev. std di popolazione, come MT5).

    Ritorna (middle, upper, lower).
    """
    middle = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)  # ddof=0 = popolazione, come iBands
    upper = middle + deviation * std
    lower = middle - deviation * std
    return middle, upper, lower


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    """ADX con +DI e -DI (smoothing di Wilder), allineato a iADX di MT5.

    Ritorna un DataFrame con colonne: adx, plus_di, minus_di.
    """
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0.0), 0.0)
    minus_dm = down.where((down > up) & (down > 0.0), 0.0)

    alpha = 1 / period
    tr = _true_range(high, low, close).ewm(alpha=alpha, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False).mean() / tr
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / tr

    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = (100 * (plus_di - minus_di).abs() / denom).fillna(0.0)
    adx_line = dx.ewm(alpha=alpha, adjust=False).mean()

    return pd.DataFrame({"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di})


def donchian(high: pd.Series, low: pd.Series, period: int = 20):
    """Canale di Donchian: (massimo piu' alto, minimo piu' basso) su `period` barre.

    Ritorna (highest, lowest) come Series.
    """
    return high.rolling(period).max(), low.rolling(period).min()


def bb_width(close: pd.Series, period: int = 20, deviation: float = 2.0) -> pd.Series:
    """Ampiezza relativa delle Bollinger: (upper - lower) / |middle|."""
    middle, upper, lower = bollinger(close, period, deviation)
    return (upper - lower) / middle.abs()


def percentile_floor(values, pct: float) -> float:
    """Percentile col metodo dell'EA (PercentileFromArray): ordina e prende
    l'elemento all'indice floor((n-1)*pct/100). NON interpola come numpy.
    """
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = arr.size
    if n == 0:
        return float("nan")
    arr.sort()
    p = min(100.0, max(0.0, pct))
    idx = int(np.floor((n - 1) * p / 100.0))
    idx = min(n - 1, max(0, idx))
    return float(arr[idx])
