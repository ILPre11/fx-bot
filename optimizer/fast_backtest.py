"""
Valutatore veloce dell'ensemble FX Multi-Regime per l'ottimizzazione parametrica.

Idea: i PERIODI degli indicatori restano fissi, quindi gli indicatori si
calcolano UNA SOLA VOLTA su tutta la storia (precompute). L'hill-climbing tocca
solo le SOGLIE (adx min, rsi, moltiplicatori ATR, R:R, time-stop), che sono
semplici confronti -> ogni valutazione costa secondi invece di minuti.

La logica dei moduli è un port fedele di forex_bot/strategies/fx_multi_regime.py.
Va validato (validate.py) contro il motore originale prima di fidarsi.

Convenzione shift come nell'EA: per la barra H1 corrente i, 'shift k' = i-k
(shift 1 = ultima H1 chiusa). Per l'H4, m = ultima barra H4 con time <= time[i],
e 'shift k' su H4 = m-k.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forex_bot import indicators as ind

MODULE_TREND = 1
MODULE_ASIA = 2
MODULE_MEANREV = 3
MODULE_VOL = 4
PRIORITY = (MODULE_ASIA, MODULE_VOL, MODULE_TREND, MODULE_MEANREV)

BB_DEV = 2.0
SERVER_OFFSET = 3  # Vantage UTC+3

# Periodi degli indicatori (default dell'EA). Ora OTTIMIZZABILI: passati a
# precompute() che ricalcola gli indicatori (costa ~0,1s, trascurabile).
DEFAULT_PERIODS: dict[str, int] = {
    "fast_ema": 20,
    "medium_ema": 50,
    "slow_ema": 100,
    "long_ema": 200,
    "adx_period": 14,
    "atr_period": 14,
    "atr_long": 100,
    "bb_period": 20,
    "rsi_period": 2,
    "donchian": 20,
    "bbw_pct_bars": 120,
}

# Parametri ottimizzabili (default = strategia attuale)
DEFAULT_PARAMS: dict[str, float] = {
    # Trend
    "trend_adx_h1_min": 22.0,
    "trend_adx_h4_min": 20.0,
    "trend_atr_stop_mult": 2.0,
    # Mean reversion
    "range_adx_h1_max": 18.0,
    "range_adx_h4_max": 20.0,
    "range_near_ema_atr": 1.0,
    "range_atr_max_ratio": 1.10,
    "mean_rsi_long_max": 8.0,
    "mean_rsi_short_min": 92.0,
    "mean_atr_stop_mult": 1.40,
    # Vol breakout
    "compression_percentile": 25.0,
    "vol_adx_max": 20.0,
    "vol_atr_stop_mult": 1.80,
    # Asia breakout
    "asia_min_range_atr": 0.40,
    "asia_max_range_atr": 1.20,
    "asia_breakout_buffer_atr": 0.10,
    "asia_max_stop_atr": 2.20,
    "asia_width_percentile": 45.0,
    # Uscita (comuni a tutti i moduli)
    "rr": 2.0,            # target take profit in multipli di R
    "max_bars_open": 120,  # time-stop in barre H1
}

BUY, SELL = 1, -1


@dataclass
class Precomputed:
    """Indicatori e serie precalcolati una sola volta per il simbolo."""
    n: int
    h1_time: np.ndarray
    close: np.ndarray
    high: np.ndarray
    low: np.ndarray
    ema20: np.ndarray
    ema50: np.ndarray
    ema100: np.ndarray
    adx1: np.ndarray
    pdi1: np.ndarray
    mdi1: np.ndarray
    atr14: np.ndarray
    atr100: np.ndarray
    bb_up: np.ndarray
    bb_lo: np.ndarray
    bbw: np.ndarray
    rsi2: np.ndarray
    donch_h: np.ndarray
    donch_l: np.ndarray
    # H4
    h4_idx: np.ndarray      # per ogni i: indice ultima barra H4 con time<=time[i]
    h4_close: np.ndarray
    h4_ema50: np.ndarray
    h4_ema100: np.ndarray
    h4_ema200: np.ndarray
    h4_adx: np.ndarray
    # Asia: range sessione asiatica (00-06 UTC) per data
    asia_high: dict
    asia_low: dict
    as_of_utc: np.ndarray   # time[i] convertito in UTC (datetime64)
    start: int              # primo indice valutabile
    bbw_pct_bars: int = 120  # finestra percentile bb_width


def precompute(h1: pd.DataFrame, h4: pd.DataFrame, periods: dict | None = None) -> Precomputed:
    pr = {**DEFAULT_PERIODS, **(periods or {})}
    fast_ema = int(pr["fast_ema"]); medium_ema = int(pr["medium_ema"])
    slow_ema = int(pr["slow_ema"]); long_ema = int(pr["long_ema"])
    adx_p = int(pr["adx_period"]); atr_p = int(pr["atr_period"]); atr_long = int(pr["atr_long"])
    bb_p = int(pr["bb_period"]); rsi_p = int(pr["rsi_period"]); donch = int(pr["donchian"])
    bbw_bars = int(pr["bbw_pct_bars"])

    c1 = h1["close"]
    adx_h1 = ind.adx(h1["high"], h1["low"], c1, adx_p)
    mid, up, lo = ind.bollinger(c1, bb_p, BB_DEV)
    dh, dl = ind.donchian(h1["high"], h1["low"], donch)

    c4 = h4["close"]
    adx_h4 = ind.adx(h4["high"], h4["low"], c4, adx_p)

    h1_time = h1["time"].to_numpy()
    h4_time = h4["time"].to_numpy()
    # m[i] = numero barre H4 con time <= time[i], -1 = ultimo indice valido
    h4_idx = np.searchsorted(h4_time, h1_time, side="right") - 1

    as_of_utc = h1_time - np.timedelta64(SERVER_OFFSET, "h")

    # Range sessione asiatica (00:00-06:00 UTC) per ciascuna data UTC
    utc_ts = pd.DatetimeIndex(as_of_utc)
    asia_mask = (utc_ts.hour >= 0) & (utc_ts.hour < 6)
    asia_high: dict = {}
    asia_low: dict = {}
    if asia_mask.any():
        dfa = pd.DataFrame({
            "date": utc_ts[asia_mask].normalize(),
            "high": h1["high"].to_numpy()[asia_mask],
            "low": h1["low"].to_numpy()[asia_mask],
        })
        g = dfa.groupby("date")
        asia_high = g["high"].max().to_dict()
        asia_low = g["low"].min().to_dict()

    pc = Precomputed(
        n=len(h1),
        h1_time=h1_time,
        close=c1.to_numpy(),
        high=h1["high"].to_numpy(),
        low=h1["low"].to_numpy(),
        ema20=ind.ema(c1, fast_ema).to_numpy(),
        ema50=ind.ema(c1, medium_ema).to_numpy(),
        ema100=ind.ema(c1, slow_ema).to_numpy(),
        adx1=adx_h1["adx"].to_numpy(),
        pdi1=adx_h1["plus_di"].to_numpy(),
        mdi1=adx_h1["minus_di"].to_numpy(),
        atr14=ind.atr(h1["high"], h1["low"], c1, atr_p).to_numpy(),
        atr100=ind.atr(h1["high"], h1["low"], c1, atr_long).to_numpy(),
        bb_up=up.to_numpy(),
        bb_lo=lo.to_numpy(),
        bbw=ind.bb_width(c1, bb_p, BB_DEV).to_numpy(),
        rsi2=ind.rsi(c1, rsi_p).to_numpy(),
        donch_h=dh.to_numpy(),
        donch_l=dl.to_numpy(),
        h4_idx=h4_idx,
        h4_close=c4.to_numpy(),
        h4_ema50=ind.ema(c4, medium_ema).to_numpy(),
        h4_ema100=ind.ema(c4, slow_ema).to_numpy(),
        h4_ema200=ind.ema(c4, long_ema).to_numpy(),
        h4_adx=adx_h4["adx"].to_numpy(),
        asia_high=asia_high,
        asia_low=asia_low,
        as_of_utc=as_of_utc,
        start=0,
        bbw_pct_bars=bbw_bars,
    )
    # primo indice valutabile: H4 EMA-lunga "scaldata" e warmup H1 sufficiente
    warm_h4 = long_ema + 10
    warm_h1 = max(atr_long, slow_ema, bbw_bars + bb_p, donch) + 12
    valid = np.where(h4_idx >= warm_h4)[0]
    pc.start = max(int(valid[0]) if len(valid) else warm_h1, warm_h1)
    return pc


def _ok(*vals) -> bool:
    for v in vals:
        if v != v:  # NaN
            return False
    return True


# --------------------------- Moduli (port fedele) ---------------------------
def _trend(pc: Precomputed, i: int, m: int, p: dict):
    close4 = pc.h4_close[m - 1]
    e50_4, e100_4, e200_4 = pc.h4_ema50[m - 1], pc.h4_ema100[m - 1], pc.h4_ema200[m - 1]
    e100_4_6 = pc.h4_ema100[m - 6]
    adx4 = pc.h4_adx[m - 1]
    e20_1, e100_1 = pc.ema20[i - 1], pc.ema100[i - 1]
    c1_1, c1_2 = pc.close[i - 1], pc.close[i - 2]
    e20_2 = pc.ema20[i - 2]
    adx1 = pc.adx1[i - 1]
    pdi, mdi = pc.pdi1[i - 1], pc.mdi1[i - 1]
    atr1, atrL1 = pc.atr14[i - 1], pc.atr100[i - 1]

    if not _ok(close4, e50_4, e100_4, e200_4, e100_4_6, adx4, e20_1, e100_1,
               c1_1, c1_2, e20_2, adx1, pdi, mdi, atr1, atrL1):
        return None
    if atr1 <= 0:
        return None

    long_regime = (close4 > e100_4 and e50_4 > e100_4 and e100_4 > e200_4 and
                   e100_4 > e100_4_6 and adx4 >= p["trend_adx_h4_min"])
    short_regime = (close4 < e100_4 and e50_4 < e100_4 and e100_4 < e200_4 and
                    e100_4 < e100_4_6 and adx4 >= p["trend_adx_h4_min"])
    atr_filter = atr1 > 0.75 * atrL1
    long_ok = (long_regime and e20_1 > e100_1 and c1_1 > e20_1 and c1_2 <= e20_2 and
               adx1 > p["trend_adx_h1_min"] and pdi > mdi and atr_filter)
    short_ok = (short_regime and e20_1 < e100_1 and c1_1 < e20_1 and c1_2 >= e20_2 and
                adx1 > p["trend_adx_h1_min"] and mdi > pdi and atr_filter)
    if not long_ok and not short_ok:
        return None
    entry = pc.close[i]
    if long_ok:
        return (BUY, entry, entry - p["trend_atr_stop_mult"] * atr1)
    return (SELL, entry, entry + p["trend_atr_stop_mult"] * atr1)


def _mean_rev(pc: Precomputed, i: int, m: int, p: dict):
    adx1, adx4 = pc.adx1[i - 1], pc.h4_adx[m - 1]
    atr, atrL = pc.atr14[i - 1], pc.atr100[i - 1]
    ema100, close = pc.ema100[i - 1], pc.close[i - 1]

    def width(k):
        mid_k = (pc.bb_up[i - k] + pc.bb_lo[i - k]) / 2.0
        if mid_k != mid_k or mid_k == 0:
            return float("nan")
        return (pc.bb_up[i - k] - pc.bb_lo[i - k]) / abs(mid_k)

    w1, w3 = width(1), width(3)
    if not _ok(adx1, adx4, atr, atrL, ema100, close, w1, w3):
        return None
    if atrL <= 0:
        return None
    range_regime = (adx1 < p["range_adx_h1_max"] and adx4 < p["range_adx_h4_max"] and
                    abs(close - ema100) <= p["range_near_ema_atr"] * atr and
                    atr <= p["range_atr_max_ratio"] * atrL and w1 <= w3 * 1.25)
    if not range_regime:
        return None

    up1, lo1 = pc.bb_up[i - 1], pc.bb_lo[i - 1]
    rsi = pc.rsi2[i - 1]
    atr3 = pc.atr14[i - 3]
    dh, dl = pc.donch_h[i - 2], pc.donch_l[i - 2]
    if not _ok(up1, lo1, rsi, atr3, dh, dl):
        return None
    atr_expanding = atr > atr3
    broke_down = close < dl and atr_expanding
    broke_up = close > dh and atr_expanding
    long_ok = close < lo1 and rsi < p["mean_rsi_long_max"] and not broke_down
    short_ok = close > up1 and rsi > p["mean_rsi_short_min"] and not broke_up
    if not long_ok and not short_ok:
        return None
    entry = pc.close[i]
    if long_ok:
        return (BUY, entry, entry - p["mean_atr_stop_mult"] * atr)
    return (SELL, entry, entry + p["mean_atr_stop_mult"] * atr)


def _vol(pc: Precomputed, i: int, m: int, p: dict):
    w1 = pc.bbw[i - 1]
    window = pc.bbw[i - pc.bbw_pct_bars: i]  # shift 1..N = indici i-N..i-1
    threshold = ind.percentile_floor(window, p["compression_percentile"])
    atr1, atrL = pc.atr14[i - 1], pc.atr100[i - 1]
    adx1 = pc.adx1[i - 1]
    if not _ok(w1, threshold, atr1, atrL, adx1):
        return None
    if not (w1 <= threshold and atr1 < atrL and adx1 < p["vol_adx_max"]):
        return None

    dh, dl = pc.donch_h[i - 2], pc.donch_l[i - 2]
    atr3 = pc.atr14[i - 3]
    ema50 = pc.ema50[i - 1]
    c1 = pc.close[i - 1]
    c4 = pc.h4_close[m - 1]
    e100_4, e100_4_6 = pc.h4_ema100[m - 1], pc.h4_ema100[m - 6]
    if not _ok(dh, dl, atr3, ema50, c1, c4, e100_4, e100_4_6):
        return None
    atr_expands = atr1 > atr3
    h4_flat = abs(e100_4 - e100_4_6) <= 0.25 * atr1
    long_ok = c1 > dh and atr_expands and c1 > ema50 and (c4 > e100_4 or h4_flat)
    short_ok = c1 < dl and atr_expands and c1 < ema50 and (c4 < e100_4 or h4_flat)
    if not long_ok and not short_ok:
        return None
    entry = pc.close[i]
    if long_ok:
        return (BUY, entry, entry - p["vol_atr_stop_mult"] * atr1)
    return (SELL, entry, entry + p["vol_atr_stop_mult"] * atr1)


def _asia(pc: Precomputed, i: int, m: int, p: dict):
    as_of = pd.Timestamp(pc.as_of_utc[i])
    if not (7 <= as_of.hour < 11):
        return None
    atr1 = pc.atr14[i - 1]
    if atr1 != atr1 or atr1 <= 0:
        return None
    day = as_of.normalize()
    if day not in pc.asia_high:
        return None
    asia_high = pc.asia_high[day]
    asia_low = pc.asia_low[day]
    width_rng = asia_high - asia_low
    if not (p["asia_min_range_atr"] * atr1 <= width_rng <= p["asia_max_range_atr"] * atr1):
        return None

    w1 = pc.bbw[i - 1]
    window = pc.bbw[i - pc.bbw_pct_bars: i]  # shift 1..N = indici i-N..i-1
    thr = ind.percentile_floor(window, p["asia_width_percentile"])
    if w1 != w1 or thr != thr or w1 > thr:
        return None

    adx1, adx3 = pc.adx1[i - 1], pc.adx1[i - 3]
    atr3 = pc.atr14[i - 3]
    close1 = pc.close[i - 1]
    close4, e100_4 = pc.h4_close[m - 1], pc.h4_ema100[m - 1]
    if not _ok(adx1, adx3, atr3, close1, close4, e100_4):
        return None
    adx_rising = adx1 > adx3
    atr_rising = atr1 > atr3
    buf = p["asia_breakout_buffer_atr"] * atr1
    long_ok = close1 > asia_high + buf and adx_rising and atr_rising and close4 > e100_4
    short_ok = close1 < asia_low - buf and adx_rising and atr_rising and close4 < e100_4
    if not long_ok and not short_ok:
        return None
    entry = pc.close[i]
    if long_ok:
        sl = asia_low - buf
        if abs(entry - sl) > p["asia_max_stop_atr"] * atr1:
            return None
        return (BUY, entry, sl)
    sl = asia_high + buf
    if abs(entry - sl) > p["asia_max_stop_atr"] * atr1:
        return None
    return (SELL, entry, sl)


_MODULE_FN = {
    MODULE_TREND: _trend,
    MODULE_MEANREV: _mean_rev,
    MODULE_VOL: _vol,
    MODULE_ASIA: _asia,
}


def _choose(candidates: dict):
    """Replica ChooseSignal: niente conflitti, priorità. (Il rischio non conta in R.)"""
    if not candidates:
        return None
    sides = {c[0] for c in candidates.values()}
    if BUY in sides and SELL in sides:
        return None
    for mod in PRIORITY:
        if mod in candidates:
            return candidates[mod]
    return None


def _simulate_exit(pc, entry_idx, side, entry, sl, rr, max_bars):
    risk = abs(entry - sl)
    if risk <= 0:
        return 0.0, 0
    tp = entry + rr * risk if side == BUY else entry - rr * risk
    end = min(entry_idx + max_bars + 1, pc.n)
    for j in range(entry_idx + 1, end):
        lo, hi = pc.low[j], pc.high[j]
        if side == BUY:
            if lo <= sl:
                return -1.0, j - entry_idx
            if hi >= tp:
                return rr, j - entry_idx
        else:
            if hi >= sl:
                return -1.0, j - entry_idx
            if lo <= tp:
                return rr, j - entry_idx
    last = min(entry_idx + max_bars, pc.n - 1)
    lc = pc.close[last]
    pnl = (lc - entry) / risk if side == BUY else (entry - lc) / risk
    return float(pnl), max_bars


def evaluate(pc: Precomputed, params: dict, modules=(1, 2, 3, 4)) -> dict:
    """Esegue il backtest veloce e ritorna le statistiche."""
    p = {**DEFAULT_PARAMS, **params}
    max_bars = int(p["max_bars_open"])
    rr = p["rr"]
    pnls: list[float] = []
    open_until = -1

    for i in range(pc.start, pc.n - 2):
        if i <= open_until:
            continue
        m = pc.h4_idx[i]
        if m < 7:
            continue
        candidates = {}
        for mod in modules:
            sig = _MODULE_FN[mod](pc, i, m, p)
            if sig is not None:
                candidates[mod] = sig
        chosen = _choose(candidates)
        if chosen is None:
            continue
        side, entry, sl = chosen
        pnl, bars = _simulate_exit(pc, i, side, entry, sl, rr, max_bars)
        pnls.append(pnl)
        open_until = i + bars

    return _stats(pnls)


def _stats(pnls: list[float]) -> dict:
    if not pnls:
        return {"num_trades": 0, "pf": 0.0, "win_rate": 0.0, "total_r": 0.0,
                "sharpe": 0.0, "max_dd_r": 0.0}
    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    gp, gl = wins.sum(), -losses.sum()
    pf = gp / gl if gl > 0 else float("inf")
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    std = arr.std()
    sharpe = float(arr.mean() / std * np.sqrt(252 * 16)) if std > 0 else 0.0
    return {
        "num_trades": len(pnls),
        "pf": round(pf, 3) if pf != float("inf") else 999.0,
        "win_rate": round(len(wins) / len(pnls), 3),
        "total_r": round(float(arr.sum()), 2),
        "sharpe": round(sharpe, 2),
        "max_dd_r": round(max_dd, 2),
    }
