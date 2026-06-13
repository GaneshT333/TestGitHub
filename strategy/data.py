"""Data loading and resampling utilities.

The strategy operates on a tidy OHLCV DataFrame indexed by a timezone-aware (or
naive) DatetimeIndex with columns: open, high, low, close, volume.

Three sources are supported:
  * load_csv      — your own historical data
  * load_yfinance — optional convenience wrapper (requires `yfinance` + network)
  * generate_synthetic — deterministic fake data so the demo/backtest runs
                          anywhere, with no dependencies on a data feed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV = ["open", "high", "low", "close", "volume"]


def normalize_freq(timeframe: str) -> str:
    """Normalise pandas offset aliases across pandas 1.x and 2.x.

    pandas 2.2 deprecated the uppercase ``H``/``T`` aliases in favour of
    ``h``/``min``. We accept either so the same config runs on both.
    """
    tf = timeframe.strip()
    # Split optional leading multiplier from the unit, e.g. "15" + "min".
    i = 0
    while i < len(tf) and (tf[i].isdigit()):
        i += 1
    num, unit = tf[:i], tf[i:]
    replacements = {"H": "h", "T": "min", "MIN": "min", "Min": "min"}
    unit = replacements.get(unit, unit)
    return f"{num}{unit}"


def _validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in OHLCV if c not in df.columns]
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must be indexed by a DatetimeIndex")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df[OHLCV].astype(float)


def load_csv(path: str, datetime_col: str = "datetime") -> pd.DataFrame:
    """Load OHLCV data from a CSV file.

    The CSV must contain a datetime column plus open/high/low/close/volume
    (case-insensitive). Column names are normalised to lowercase.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    dt_col = datetime_col.lower()
    if dt_col not in df.columns:
        raise ValueError(f"CSV must contain a '{datetime_col}' column")
    df[dt_col] = pd.to_datetime(df[dt_col])
    df = df.set_index(dt_col)
    df.index.name = "datetime"
    return _validate_ohlcv(df)


def load_yfinance(symbol: str, period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Download intraday data via yfinance (optional dependency, needs network)."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - optional path
        raise ImportError(
            "yfinance is not installed. Install it with `pip install yfinance` "
            "or use load_csv / generate_synthetic instead."
        ) from exc

    raw = yf.download(symbol, period=period, interval=interval, progress=False)
    if raw.empty:
        raise ValueError(f"No data returned for {symbol!r} ({interval}, {period})")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.lower)
    raw.index.name = "datetime"
    return _validate_ohlcv(raw)


def resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample OHLCV to a higher timeframe using standard aggregation."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(normalize_freq(timeframe), label="right", closed="right").agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"])


def generate_synthetic(
    days: int = 20,
    start: str = "2024-01-02 09:30",
    freq: str = "1min",
    session_minutes: int = 390,
    seed: int = 7,
    start_price: float = 100.0,
) -> pd.DataFrame:
    """Generate deterministic intraday OHLCV data with intraday trends.

    The generator deliberately injects persistent intraday drift (a random-walk
    of the per-session drift term) so that a trend-following multi-timeframe
    strategy has something real to find — useful for smoke-testing and demos.
    """
    freq = normalize_freq(freq)
    # Number of bars per session depends on the bar length, so a 5min session
    # spans the same wall-clock window as a 1min session (just fewer bars).
    bar_minutes = max(1, int(pd.Timedelta(freq).total_seconds() // 60))
    n_bars = max(1, session_minutes // bar_minutes)

    rng = np.random.default_rng(seed)
    sessions = []
    day = pd.Timestamp(start)
    price = start_price

    for _ in range(days):
        # Each session gets its own drift (trend) and volatility regime.
        drift = rng.normal(0, 0.00012)
        vol = abs(rng.normal(0.0009, 0.0003)) + 1e-4
        idx = pd.date_range(day, periods=n_bars, freq=freq)

        # Intraday drift wanders so trends build and fade within the day.
        steps = rng.normal(drift, vol, n_bars)
        steps += np.cumsum(rng.normal(0, vol * 0.15, n_bars)) / n_bars
        log_path = np.cumsum(steps)
        closes = price * np.exp(log_path)

        opens = np.empty_like(closes)
        opens[0] = price
        opens[1:] = closes[:-1]

        bar_range = np.abs(rng.normal(0, vol, n_bars)) * closes
        highs = np.maximum(opens, closes) + bar_range * 0.5
        lows = np.minimum(opens, closes) - bar_range * 0.5
        volume = rng.integers(500, 5000, n_bars).astype(float)

        sessions.append(
            pd.DataFrame(
                {
                    "open": opens,
                    "high": highs,
                    "low": lows,
                    "close": closes,
                    "volume": volume,
                },
                index=idx,
            )
        )
        price = closes[-1]
        day = (day + pd.Timedelta(days=1)).normalize() + pd.Timedelta(
            hours=day.hour, minutes=day.minute
        )

    df = pd.concat(sessions)
    df.index.name = "datetime"
    return _validate_ohlcv(df)
