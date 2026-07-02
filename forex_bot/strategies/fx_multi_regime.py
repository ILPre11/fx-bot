"""Port in Python dell'EA 'FX Multi-Regime Ensemble' (solo segnali d'ingresso).

Port incrementale. Moduli implementati: TREND, MEAN_REVERSION.
Restano: ASIA_BREAKOUT, VOL_BREAKOUT. Arbitraggio (ChooseSignal) gia' attivo.

Indicizzazione come nell'EA: 'shift k' = k barre indietro, dove shift 0 e' la
candela in formazione e shift 1 l'ultima chiusa.
"""
from __future__ import annotations

import math
from datetime import datetime

import pandas as pd

from forex_bot import indicators as ind
from forex_bot.models import MarketData, Side, TradeIdea
from forex_bot.strategies.base import Strategy

# Id moduli (come nell'enum dell'EA) e ordine di priorita' dell'arbitraggio.
MODULE_TREND = 1
MODULE_ASIA = 2
MODULE_MEANREV = 3
MODULE_VOL = 4
PRIORITY = (MODULE_ASIA, MODULE_VOL, MODULE_TREND, MODULE_MEANREV)


def _at(series, shift: int) -> float:
    """Valore della serie 'shift' barre indietro (shift 1 = ultima chiusa)."""
    return float(series.iloc[-1 - shift])


def _ok(*vals: float) -> bool:
    return all(not math.isnan(v) for v in vals)


class FxMultiRegimeStrategy(Strategy):
    name = "fx_multi_regime"
    required_timeframes = ["H1", "H4"]

    def __init__(self, risk_trend_pct: float = 0.45, risk_asia_pct: float = 0.35,
                 risk_vol_pct: float = 0.35, risk_mean_pct: float = 0.25) -> None:
        # Periodi indicatori (default dell'EA)
        self.fast_ema = 20
        self.medium_ema = 50
        self.slow_ema = 100
        self.long_ema = 200
        self.adx_period = 14
        self.atr_period = 14
        self.atr_long_period = 100
        self.bb_period = 20
        self.bb_dev = 2.0
        self.rsi_period = 2
        self.donchian_period = 20

        # Modulo Trend
        self.use_trend = True
        self.trend_adx_h1_min = 22.0
        self.trend_adx_h4_min = 20.0
        self.trend_atr_stop_mult = 2.0
        self.risk_trend = risk_trend_pct / 100.0

        # Modulo Mean Reversion
        self.use_mean_rev = True
        self.range_adx_h1_max = 18.0
        self.range_adx_h4_max = 20.0
        self.range_near_ema_atr = 1.0
        self.range_atr_max_ratio = 1.10
        self.mean_rsi_long_max = 8.0
        self.mean_rsi_short_min = 92.0
        self.mean_atr_stop_mult = 1.40
        self.risk_mean_rev = risk_mean_pct / 100.0

        # Modulo Vol Breakout
        self.use_vol = True
        self.bb_width_pct_bars = 120
        self.compression_percentile = 25.0
        self.vol_adx_max = 20.0
        self.vol_atr_stop_mult = 1.80
        self.risk_vol = risk_vol_pct / 100.0

        # Modulo Asia/London Breakout
        self.use_asia = True
        self.asia_start_hour = 0
        self.asia_end_hour = 6
        self.breakout_start_hour = 7
        self.breakout_end_hour = 11
        self.asia_min_range_atr = 0.40
        self.asia_max_range_atr = 1.20
        self.asia_breakout_buffer_atr = 0.10
        self.asia_max_stop_atr = 2.20
        self.asia_width_percentile = 45.0
        self.risk_asia = risk_asia_pct / 100.0

        # Parametri di USCITA (impostati dall'ottimizzatore; None = comportamento
        # storico: nessun TP fisso, uscita gestita altrove).
        self.rr = None            # take profit = ingresso +/- rr * (distanza SL)
        self.max_bars_open = None  # time-stop in barre H1 (gestito nel loop live)

    # Mappa nome-parametro-ottimizzatore -> attributo della strategia (dove differisce)
    _OPT_ALIASES = {
        "atr_long": "atr_long_period",
        "donchian": "donchian_period",
        "bbw_pct_bars": "bb_width_pct_bars",
    }

    def apply_optimized(self, opt: dict) -> None:
        """Applica i parametri trovati dall'ottimizzatore (soglie + periodi + uscita).

        Accetta un dict piatto con le chiavi usate da optimizer/fast_backtest
        (DEFAULT_PARAMS + DEFAULT_PERIODS) piu' rr e max_bars_open.
        """
        for key, value in opt.items():
            attr = self._OPT_ALIASES.get(key, key)
            if hasattr(self, attr):
                # i periodi sono interi
                cur = getattr(self, attr)
                setattr(self, attr, int(value) if isinstance(cur, int) else value)

    def generate(self, data: MarketData) -> TradeIdea | None:
        candidates: dict[int, TradeIdea] = {}
        trend = self._trend(data)
        if trend:
            candidates[MODULE_TREND] = trend
        mean = self._mean_reversion(data)
        if mean:
            candidates[MODULE_MEANREV] = mean
        vol = self._vol_breakout(data)
        if vol:
            candidates[MODULE_VOL] = vol
        asia = self._asia_breakout(data)
        if asia:
            candidates[MODULE_ASIA] = asia
        idea = self._choose(candidates)
        # Take profit dal R:R ottimizzato (se impostato): TP = ingresso +/- rr*rischio
        if idea is not None and self.rr and idea.take_profit == 0.0:
            risk = abs(idea.entry - idea.stop_loss)
            if risk > 0:
                idea.take_profit = (idea.entry + self.rr * risk if idea.side is Side.BUY
                                    else idea.entry - self.rr * risk)
        return idea

    # --------------------------- Arbitraggio --------------------------------
    def _choose(self, candidates: dict[int, TradeIdea]) -> TradeIdea | None:
        """Replica ChooseSignal dell'EA: niente conflitti, priorita', rischio minimo."""
        if not candidates:
            return None
        sides = {idea.side for idea in candidates.values()}
        if Side.BUY in sides and Side.SELL in sides:
            return None  # moduli in conflitto: si salta
        min_risk = min(idea.risk_pct for idea in candidates.values()
                       if idea.risk_pct is not None)
        for mod in PRIORITY:
            if mod in candidates:
                chosen = candidates[mod]
                chosen.risk_pct = min_risk  # rischio piu' prudente tra i validi
                return chosen
        return None

    # ----------------------------- Modulo Trend -----------------------------
    def _trend(self, data: MarketData) -> TradeIdea | None:
        if not self.use_trend:
            return None
        h1 = data.df("H1")
        h4 = data.df("H4")
        if len(h1) < self.atr_long_period + 10 or len(h4) < self.long_ema + 10:
            return None

        c1 = h1["close"]
        ema20 = ind.ema(c1, self.fast_ema)
        ema100_h1 = ind.ema(c1, self.slow_ema)
        adx_h1 = ind.adx(h1["high"], h1["low"], c1, self.adx_period)
        atr_h1 = ind.atr(h1["high"], h1["low"], c1, self.atr_period)
        atr_long_h1 = ind.atr(h1["high"], h1["low"], c1, self.atr_long_period)

        c4 = h4["close"]
        ema50_h4 = ind.ema(c4, self.medium_ema)
        ema100_h4 = ind.ema(c4, self.slow_ema)
        ema200_h4 = ind.ema(c4, self.long_ema)
        adx_h4 = ind.adx(h4["high"], h4["low"], c4, self.adx_period)

        v_close4 = _at(c4, 1)
        v_e50_4, v_e100_4, v_e200_4 = _at(ema50_h4, 1), _at(ema100_h4, 1), _at(ema200_h4, 1)
        v_e100_4_6 = _at(ema100_h4, 6)
        v_adx4 = _at(adx_h4["adx"], 1)

        v_e20_1, v_e100_1 = _at(ema20, 1), _at(ema100_h1, 1)
        v_c1_1, v_c1_2 = _at(c1, 1), _at(c1, 2)
        v_e20_2 = _at(ema20, 2)
        v_adx1 = _at(adx_h1["adx"], 1)
        v_pdi, v_mdi = _at(adx_h1["plus_di"], 1), _at(adx_h1["minus_di"], 1)
        v_atr1, v_atrL1 = _at(atr_h1, 1), _at(atr_long_h1, 1)

        if not _ok(v_close4, v_e50_4, v_e100_4, v_e200_4, v_e100_4_6, v_adx4,
                   v_e20_1, v_e100_1, v_c1_1, v_c1_2, v_e20_2, v_adx1, v_pdi, v_mdi,
                   v_atr1, v_atrL1):
            return None
        if v_atr1 <= 0:
            return None

        long_regime = (v_close4 > v_e100_4 and v_e50_4 > v_e100_4 and
                       v_e100_4 > v_e200_4 and v_e100_4 > v_e100_4_6 and
                       v_adx4 >= self.trend_adx_h4_min)
        short_regime = (v_close4 < v_e100_4 and v_e50_4 < v_e100_4 and
                        v_e100_4 < v_e200_4 and v_e100_4 < v_e100_4_6 and
                        v_adx4 >= self.trend_adx_h4_min)

        atr_filter = v_atr1 > 0.75 * v_atrL1
        long_ok = (long_regime and v_e20_1 > v_e100_1 and v_c1_1 > v_e20_1 and
                   v_c1_2 <= v_e20_2 and v_adx1 > self.trend_adx_h1_min and
                   v_pdi > v_mdi and atr_filter)
        short_ok = (short_regime and v_e20_1 < v_e100_1 and v_c1_1 < v_e20_1 and
                    v_c1_2 >= v_e20_2 and v_adx1 > self.trend_adx_h1_min and
                    v_mdi > v_pdi and atr_filter)

        if not long_ok and not short_ok:
            return None
        if long_ok:
            entry = data.ask
            sl = entry - self.trend_atr_stop_mult * v_atr1
            side = Side.BUY
        else:
            entry = data.bid
            sl = entry + self.trend_atr_stop_mult * v_atr1
            side = Side.SELL
        return TradeIdea(side=side, entry=entry, stop_loss=sl, take_profit=0.0,
                         reason=f"TREND (ADX H1 {v_adx1:.0f} / H4 {v_adx4:.0f})",
                         risk_pct=self.risk_trend)

    # ------------------------- Modulo Mean Reversion ------------------------
    def _mean_reversion(self, data: MarketData) -> TradeIdea | None:
        if not self.use_mean_rev:
            return None
        h1 = data.df("H1")
        h4 = data.df("H4")
        need = max(self.atr_long_period, self.bb_period, self.donchian_period + 2) + 10
        if len(h1) < need or len(h4) < self.adx_period + 10:
            return None

        c1 = h1["close"]
        mid, up, lo = ind.bollinger(c1, self.bb_period, self.bb_dev)
        rsi2 = ind.rsi(c1, self.rsi_period)
        atr14 = ind.atr(h1["high"], h1["low"], c1, self.atr_period)
        atr100 = ind.atr(h1["high"], h1["low"], c1, self.atr_long_period)
        ema100_h1 = ind.ema(c1, self.slow_ema)
        adx_h1 = ind.adx(h1["high"], h1["low"], c1, self.adx_period)
        adx_h4 = ind.adx(h4["high"], h4["low"], h4["close"], self.adx_period)
        dh_s, dl_s = ind.donchian(h1["high"], h1["low"], self.donchian_period)

        def width(k: int) -> float:
            m = _at(mid, k)
            if math.isnan(m) or m == 0:
                return float("nan")
            return (_at(up, k) - _at(lo, k)) / abs(m)

        v_adx1, v_adx4 = _at(adx_h1["adx"], 1), _at(adx_h4["adx"], 1)
        v_atr, v_atrL = _at(atr14, 1), _at(atr100, 1)
        v_ema100, v_close = _at(ema100_h1, 1), _at(c1, 1)
        w1, w3 = width(1), width(3)
        if not _ok(v_adx1, v_adx4, v_atr, v_atrL, v_ema100, v_close, w1, w3):
            return None
        if v_atrL <= 0:
            return None

        range_regime = (v_adx1 < self.range_adx_h1_max and
                        v_adx4 < self.range_adx_h4_max and
                        abs(v_close - v_ema100) <= self.range_near_ema_atr * v_atr and
                        v_atr <= self.range_atr_max_ratio * v_atrL and
                        w1 <= w3 * 1.25)
        if not range_regime:
            return None

        v_up1, v_lo1 = _at(up, 1), _at(lo, 1)
        v_rsi = _at(rsi2, 1)
        v_atr3 = _at(atr14, 3)
        v_dh, v_dl = _at(dh_s, 2), _at(dl_s, 2)
        if not _ok(v_up1, v_lo1, v_rsi, v_atr3, v_dh, v_dl):
            return None

        atr_expanding = v_atr > v_atr3
        broke_down = v_close < v_dl and atr_expanding
        broke_up = v_close > v_dh and atr_expanding
        long_ok = v_close < v_lo1 and v_rsi < self.mean_rsi_long_max and not broke_down
        short_ok = v_close > v_up1 and v_rsi > self.mean_rsi_short_min and not broke_up
        if not long_ok and not short_ok:
            return None

        if long_ok:
            entry = data.ask
            sl = entry - self.mean_atr_stop_mult * v_atr
            side = Side.BUY
        else:
            entry = data.bid
            sl = entry + self.mean_atr_stop_mult * v_atr
            side = Side.SELL
        return TradeIdea(side=side, entry=entry, stop_loss=sl, take_profit=0.0,
                         reason=f"MEAN_REV (RSI2 {v_rsi:.0f}, ADX {v_adx1:.0f})",
                         risk_pct=self.risk_mean_rev)

    # ------------------------- Modulo Vol Breakout --------------------------
    def _vol_breakout(self, data: MarketData) -> TradeIdea | None:
        if not self.use_vol:
            return None
        h1 = data.df("H1")
        h4 = data.df("H4")
        need = max(self.bb_width_pct_bars + self.bb_period, self.atr_long_period,
                   self.donchian_period + 2) + 10
        if len(h1) < need or len(h4) < self.slow_ema + 10:
            return None

        c1 = h1["close"]
        bbw = ind.bb_width(c1, self.bb_period, self.bb_dev)
        atr14 = ind.atr(h1["high"], h1["low"], c1, self.atr_period)
        atr100 = ind.atr(h1["high"], h1["low"], c1, self.atr_long_period)
        adx_h1 = ind.adx(h1["high"], h1["low"], c1, self.adx_period)
        ema50_h1 = ind.ema(c1, self.medium_ema)
        dh_s, dl_s = ind.donchian(h1["high"], h1["low"], self.donchian_period)
        c4 = h4["close"]
        ema100_h4 = ind.ema(c4, self.slow_ema)

        # Regime di compressione (squeeze): width <= 25 percentile su 120 barre.
        v_w1 = _at(bbw, 1)
        window = bbw.iloc[-1 - self.bb_width_pct_bars:-1].values  # shift 1..120
        threshold = ind.percentile_floor(window, self.compression_percentile)
        v_atr1, v_atrL = _at(atr14, 1), _at(atr100, 1)
        v_adx1 = _at(adx_h1["adx"], 1)
        if not _ok(v_w1, threshold, v_atr1, v_atrL, v_adx1):
            return None
        compression = (v_w1 <= threshold and v_atr1 < v_atrL and v_adx1 < self.vol_adx_max)
        if not compression:
            return None

        v_dh, v_dl = _at(dh_s, 2), _at(dl_s, 2)
        v_atr3 = _at(atr14, 3)
        v_ema50 = _at(ema50_h1, 1)
        v_c1 = _at(c1, 1)
        v_c4 = _at(c4, 1)
        v_e100_4, v_e100_4_6 = _at(ema100_h4, 1), _at(ema100_h4, 6)
        if not _ok(v_dh, v_dl, v_atr3, v_ema50, v_c1, v_c4, v_e100_4, v_e100_4_6):
            return None

        atr_expands = v_atr1 > v_atr3
        h4_flat = abs(v_e100_4 - v_e100_4_6) <= 0.25 * v_atr1
        long_ok = (v_c1 > v_dh and atr_expands and v_c1 > v_ema50 and
                   (v_c4 > v_e100_4 or h4_flat))
        short_ok = (v_c1 < v_dl and atr_expands and v_c1 < v_ema50 and
                    (v_c4 < v_e100_4 or h4_flat))
        if not long_ok and not short_ok:
            return None

        if long_ok:
            entry = data.ask
            sl = entry - self.vol_atr_stop_mult * v_atr1
            side = Side.BUY
        else:
            entry = data.bid
            sl = entry + self.vol_atr_stop_mult * v_atr1
            side = Side.SELL
        return TradeIdea(side=side, entry=entry, stop_loss=sl, take_profit=0.0,
                         reason=f"VOL_BREAKOUT (BBw {v_w1:.4f}<=p25 {threshold:.4f}, ADX {v_adx1:.0f})",
                         risk_pct=self.risk_vol)

    # ------------------------ Modulo Asia Breakout --------------------------
    def _now_utc(self, data: MarketData) -> "pd.Timestamp":
        """'Adesso' in UTC tz-naive. In live usa l'orologio reale; nel backtest
        usa l'ora della barra corrente (data.as_of) per non leggere il futuro."""
        if getattr(data, "as_of", None) is not None:
            return pd.Timestamp(data.as_of)
        return pd.Timestamp.now(tz="UTC").tz_localize(None)

    def _asia_range(self, data: MarketData):
        """Massimo/minimo delle barre H1 nella sessione asiatica (00-06 UTC) di oggi.

        Ritorna (high, low) o None se la sessione non e' ancora chiusa oppure non
        ci sono barre nella finestra (offset server errato?).
        """
        h1 = data.df("H1")
        utc_times = h1["time"] - pd.Timedelta(hours=data.server_utc_offset)
        utc_now = self._now_utc(data)
        midnight = utc_now.normalize()
        start = midnight + pd.Timedelta(hours=self.asia_start_hour)
        end = midnight + pd.Timedelta(hours=self.asia_end_hour)
        if utc_now < end:
            return None
        sel = h1[(utc_times >= start) & (utc_times < end)]
        if sel.empty:
            return None
        return float(sel["high"].max()), float(sel["low"].min())

    def _asia_breakout(self, data: MarketData) -> TradeIdea | None:
        if not self.use_asia:
            return None
        # finestra di trading 07-11 UTC (ora reale in live, ora della barra nel backtest)
        if not (self.breakout_start_hour <= self._now_utc(data).hour < self.breakout_end_hour):
            return None
        h1 = data.df("H1")
        h4 = data.df("H4")
        if len(h1) < self.bb_width_pct_bars + self.bb_period + 10:
            return None

        c1 = h1["close"]
        atr14 = ind.atr(h1["high"], h1["low"], c1, self.atr_period)
        v_atr1 = _at(atr14, 1)
        if math.isnan(v_atr1) or v_atr1 <= 0:
            return None

        rng = self._asia_range(data)
        if rng is None:
            return None
        asia_high, asia_low = rng
        width_rng = asia_high - asia_low
        if not (self.asia_min_range_atr * v_atr1 <= width_rng <= self.asia_max_range_atr * v_atr1):
            return None

        bbw = ind.bb_width(c1, self.bb_period, self.bb_dev)
        v_w1 = _at(bbw, 1)
        thr = ind.percentile_floor(
            bbw.iloc[-1 - self.bb_width_pct_bars:-1].values, self.asia_width_percentile)
        if math.isnan(v_w1) or math.isnan(thr) or v_w1 > thr:
            return None

        adx_h1 = ind.adx(h1["high"], h1["low"], c1, self.adx_period)
        v_adx1, v_adx3 = _at(adx_h1["adx"], 1), _at(adx_h1["adx"], 3)
        v_atr3 = _at(atr14, 3)
        v_close1 = _at(c1, 1)
        c4 = h4["close"]
        ema100_h4 = ind.ema(c4, self.slow_ema)
        v_close4, v_e100_4 = _at(c4, 1), _at(ema100_h4, 1)
        if not _ok(v_adx1, v_adx3, v_atr3, v_close1, v_close4, v_e100_4):
            return None

        adx_rising = v_adx1 > v_adx3
        atr_rising = v_atr1 > v_atr3
        buffer = self.asia_breakout_buffer_atr * v_atr1
        long_ok = (v_close1 > asia_high + buffer and adx_rising and atr_rising and
                   v_close4 > v_e100_4)
        short_ok = (v_close1 < asia_low - buffer and adx_rising and atr_rising and
                    v_close4 < v_e100_4)
        if not long_ok and not short_ok:
            return None

        if long_ok:
            entry = data.ask
            sl = asia_low - buffer
            side = Side.BUY
        else:
            entry = data.bid
            sl = asia_high + buffer
            side = Side.SELL
        if abs(entry - sl) > self.asia_max_stop_atr * v_atr1:
            return None

        return TradeIdea(side=side, entry=entry, stop_loss=sl, take_profit=0.0,
                         reason=f"ASIA_BREAKOUT (range {asia_low:.5f}-{asia_high:.5f})",
                         risk_pct=self.risk_asia)
