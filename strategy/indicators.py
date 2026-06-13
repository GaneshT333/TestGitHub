"""Vectorised technical indicators built on pandas Series.

Every function is pure: it takes Series/DataFrame input and returns a new
Series, leaving the caller's data untouched. This keeps the strategy and
backtester easy to reason about and test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    # When there is no loss at all RSI is defined as 100.
    out = out.where(avg_loss != 0.0, 100.0)
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    """True range from OHLC."""
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Average True Range (Wilder's smoothing)."""
    tr = true_range(df)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Average Directional Index — trend-strength filter.

    Returns a Series of ADX values (0-100). Values above ~20-25 indicate a
    trending market; lower values indicate chop where pullback entries fail.
    """
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()

    plus_di = 100 * (
        plus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_
    )
    minus_di = 100 * (
        minus_dm.ewm(alpha=1 / length, adjust=False, min_periods=length).mean() / atr_
    )

    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)) * 100
    return dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def vwap(df: pd.DataFrame, group_key: pd.Series | None = None) -> pd.Series:
    """Volume-Weighted Average Price.

    When ``group_key`` is provided (typically the calendar date) VWAP resets at
    the start of each group, matching how intraday traders use the session VWAP.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"]

    if group_key is None:
        cum_pv = pv.cumsum()
        cum_vol = df["volume"].cumsum()
    else:
        cum_pv = pv.groupby(group_key).cumsum()
        cum_vol = df["volume"].groupby(group_key).cumsum()

    return cum_pv / cum_vol.replace(0.0, np.nan)


def rolling_extreme(series: pd.Series, length: int, kind: str) -> pd.Series:
    """Rolling max ("high") or min ("low") excluding the current bar.

    Used for breakout / swing-level detection. Shifting by one avoids look-ahead
    on the bar being evaluated.
    """
    if kind == "high":
        return series.shift(1).rolling(length).max()
    if kind == "low":
        return series.shift(1).rolling(length).min()
    raise ValueError("kind must be 'high' or 'low'")
