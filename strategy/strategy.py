"""Multi-timeframe intraday strategy.

Workflow
--------
1. Higher timeframe (HTF) analysis  -> directional *bias* (long / short / flat)
   - EMA stack defines trend direction.
   - ADX confirms the trend is strong enough to trade (filters chop).

2. Lower timeframe (LTF) execution   -> precise *entry* in the bias direction
   - Trade only with the HTF bias (no counter-trend trades).
   - Enter on a pullback-and-resume OR a micro-structure breakout.
   - Confirm with RSI band, optional VWAP side filter, and volume.

The HTF bias is merged onto the LTF using `merge_asof` so that at every LTF bar
we only use HTF information that was already *closed* — this prevents
look-ahead bias, which is the most common way intraday backtests lie.
"""

from __future__ import annotations

import pandas as pd

from . import indicators as ind
from .config import StrategyConfig
from .data import resample

# Signal encoding used throughout the package.
LONG, SHORT, FLAT = 1, -1, 0


class IntradayMTFStrategy:
    def __init__(self, config: StrategyConfig | None = None):
        self.cfg = config or StrategyConfig()
        self.cfg.validate()

    # ------------------------------------------------------------------ #
    # Higher-timeframe bias
    # ------------------------------------------------------------------ #
    def compute_htf_bias(self, ltf_df: pd.DataFrame) -> pd.DataFrame:
        """Resample to the HTF and derive a per-bar directional bias."""
        cfg = self.cfg
        htf = resample(ltf_df, cfg.htf)

        htf["ema_fast"] = ind.ema(htf["close"], cfg.htf_ema_fast)
        htf["ema_slow"] = ind.ema(htf["close"], cfg.htf_ema_slow)
        htf["adx"] = ind.adx(htf, cfg.htf_adx_length)

        trending = htf["adx"] >= cfg.htf_adx_min
        up = (htf["ema_fast"] > htf["ema_slow"]) & (htf["close"] > htf["ema_slow"])
        down = (htf["ema_fast"] < htf["ema_slow"]) & (htf["close"] < htf["ema_slow"])

        bias = pd.Series(FLAT, index=htf.index, dtype=int)
        bias[trending & up] = LONG
        bias[trending & down] = SHORT
        htf["bias"] = bias
        return htf

    # ------------------------------------------------------------------ #
    # Lower-timeframe features + entry signals
    # ------------------------------------------------------------------ #
    def compute_signals(self, ltf_df: pd.DataFrame) -> pd.DataFrame:
        """Return the LTF frame enriched with indicators, HTF bias and signals.

        The output adds (among others):
          htf_bias  : -1/0/1 bias carried from the last *closed* HTF bar
          signal    : -1/0/1 entry signal on this LTF bar
          atr       : ATR for stop sizing
        """
        cfg = self.cfg
        df = ltf_df.copy()

        # --- LTF indicators ---
        df["ema_fast"] = ind.ema(df["close"], cfg.ltf_ema_fast)
        df["ema_slow"] = ind.ema(df["close"], cfg.ltf_ema_slow)
        df["rsi"] = ind.rsi(df["close"], cfg.ltf_rsi_length)
        df["atr"] = ind.atr(df, cfg.atr_length)
        df["vwap"] = ind.vwap(df, group_key=df.index.normalize())
        df["vol_ma"] = ind.sma(df["volume"], cfg.volume_ma_length)
        df["hh"] = ind.rolling_extreme(df["high"], cfg.breakout_lookback, "high")
        df["ll"] = ind.rolling_extreme(df["low"], cfg.breakout_lookback, "low")

        # --- Carry HTF bias forward without look-ahead ---
        df = self._merge_htf_bias(df, self.compute_htf_bias(ltf_df))

        # --- Entry conditions ---
        df["signal"] = self._entry_signals(df)
        return df

    def _merge_htf_bias(self, ltf: pd.DataFrame, htf: pd.DataFrame) -> pd.DataFrame:
        """Attach the most recent *closed* HTF bias to every LTF bar.

        HTF bars are timestamped at their close (label="right"). Using
        merge_asof with direction="backward" means an LTF bar at time t only
        ever sees an HTF bar whose close timestamp <= t.
        """
        htf_bias = htf[["bias"]].rename(columns={"bias": "htf_bias"})
        merged = pd.merge_asof(
            ltf.sort_index(),
            htf_bias.sort_index(),
            left_index=True,
            right_index=True,
            direction="backward",
        )
        merged["htf_bias"] = merged["htf_bias"].fillna(FLAT).astype(int)
        return merged

    def _entry_signals(self, df: pd.DataFrame) -> pd.Series:
        cfg = self.cfg
        sig = pd.Series(FLAT, index=df.index, dtype=int)

        rising = df["ema_fast"] > df["ema_slow"]
        falling = df["ema_fast"] < df["ema_slow"]

        vol_ok = df["volume"] >= cfg.volume_mult * df["vol_ma"]

        # Pullback-and-resume: price dipped toward/below the fast EMA over the
        # lookback and the current bar closes back above it with momentum.
        pulled_back_long = (
            df["low"].rolling(cfg.pullback_lookback).min() <= df["ema_fast"]
        )
        resume_long = (df["close"] > df["ema_fast"]) & (df["close"] > df["open"])

        pulled_back_short = (
            df["high"].rolling(cfg.pullback_lookback).max() >= df["ema_fast"]
        )
        resume_short = (df["close"] < df["ema_fast"]) & (df["close"] < df["open"])

        # Micro-structure breakout of the recent range.
        breakout_long = df["close"] > df["hh"]
        breakout_short = df["close"] < df["ll"]

        rsi_long_ok = df["rsi"].between(cfg.rsi_long_floor, cfg.rsi_long_ceiling)
        rsi_short_ok = df["rsi"].between(cfg.rsi_short_floor, cfg.rsi_short_ceiling)

        vwap_long_ok = (df["close"] > df["vwap"]) if cfg.use_vwap_filter else True
        vwap_short_ok = (df["close"] < df["vwap"]) if cfg.use_vwap_filter else True

        long_trigger = (pulled_back_long & resume_long) | breakout_long
        short_trigger = (pulled_back_short & resume_short) | breakout_short

        long_ok = (
            (df["htf_bias"] == LONG)
            & rising
            & long_trigger
            & rsi_long_ok
            & vwap_long_ok
            & vol_ok
        )
        short_ok = (
            (df["htf_bias"] == SHORT)
            & falling
            & short_trigger
            & rsi_short_ok
            & vwap_short_ok
            & vol_ok
        )

        if cfg.allow_long:
            sig[long_ok] = LONG
        if cfg.allow_short:
            sig[short_ok] = SHORT
        return sig
