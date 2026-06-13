"""Tests for the multi-timeframe intraday strategy.

Runnable with pytest (`pytest -q`) or directly (`python tests/test_strategy.py`).
The most important tests guard against look-ahead bias, which is the single
biggest cause of intraday backtests that look great and lose money live.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import Backtester, StrategyConfig, IntradayMTFStrategy
from strategy import data as data_mod
from strategy import indicators as ind
from strategy.data import normalize_freq


def _sample(days=15, freq="5min"):
    return data_mod.generate_synthetic(days=days, freq=freq, seed=3)


def test_normalize_freq():
    assert normalize_freq("1H") == "1h"
    assert normalize_freq("15T") == "15min"
    assert normalize_freq("5min") == "5min"
    assert normalize_freq("1h") == "1h"


def test_rsi_bounds():
    df = _sample()
    r = ind.rsi(df["close"], 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_atr_positive():
    df = _sample()
    a = ind.atr(df, 14).dropna()
    assert (a > 0).all()


def test_rolling_extreme_no_lookahead():
    # rolling high must exclude the current bar (shifted by one).
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    hh = ind.rolling_extreme(s, 2, "high")
    # At index 2 the lookback covers indices 0-1 -> max(1,2)=2, not 3.
    assert hh.iloc[2] == 2.0


def test_htf_bias_values():
    cfg = StrategyConfig()
    strat = IntradayMTFStrategy(cfg)
    df = _sample()
    htf = strat.compute_htf_bias(df)
    assert set(htf["bias"].unique()).issubset({-1, 0, 1})


def test_htf_bias_no_lookahead():
    """Every LTF bar must only see an HTF bias whose bar already closed."""
    cfg = StrategyConfig()
    strat = IntradayMTFStrategy(cfg)
    df = _sample()
    sig = strat.compute_signals(df)
    htf = strat.compute_htf_bias(df)

    # For a sample of LTF timestamps, the attached bias must equal the bias of
    # the latest HTF bar with close-time <= the LTF timestamp.
    htf_nonan = htf.dropna(subset=["bias"])
    for ts in sig.index[::257]:
        prior = htf_nonan.loc[htf_nonan.index <= ts]
        expected = prior["bias"].iloc[-1] if len(prior) else 0
        assert sig.loc[ts, "htf_bias"] == expected


def test_signals_only_in_bias_direction():
    cfg = StrategyConfig()
    strat = IntradayMTFStrategy(cfg)
    df = _sample()
    sig = strat.compute_signals(df)
    longs = sig[sig["signal"] == 1]
    shorts = sig[sig["signal"] == -1]
    assert (longs["htf_bias"] == 1).all()
    assert (shorts["htf_bias"] == -1).all()


def test_backtest_runs_and_accounts():
    cfg = StrategyConfig()
    res = Backtester(cfg).run(_sample(days=20))
    assert res.stats["n_trades"] >= 0
    # Final equity must equal initial + sum of trade PnL (accounting identity).
    pnl = sum(t.pnl for t in res.trades)
    assert abs(res.stats["final_equity"] - (cfg.initial_equity + pnl)) < 1e-6


def test_max_trades_per_day_respected():
    cfg = StrategyConfig(max_trades_per_day=2)
    res = Backtester(cfg).run(_sample(days=20))
    per_day = {}
    for t in res.trades:
        d = t.entry_time.date()
        per_day[d] = per_day.get(d, 0) + 1
    assert all(v <= 2 for v in per_day.values())


def test_trades_respect_session_window():
    cfg = StrategyConfig()
    res = Backtester(cfg).run(_sample(days=20))
    from datetime import time
    start = time(9, 30)
    no_entry = time(15, 30)
    for t in res.trades:
        assert start <= t.entry_time.time() <= time(15, 55)
        # Entries fill on the bar after the signal, so allow up to no_entry+1 bar.
        assert t.entry_time.time() <= time(15, 35)


def test_long_only_config():
    cfg = StrategyConfig(allow_short=False)
    res = Backtester(cfg).run(_sample(days=20))
    assert all(t.direction == 1 for t in res.trades)


def test_stop_and_target_distances():
    cfg = StrategyConfig(risk_reward=2.0, atr_stop_mult=1.5)
    res = Backtester(cfg).run(_sample(days=20))
    for t in res.trades:
        stop_dist = abs(t.entry_price - t.stop)
        target_dist = abs(t.target - t.entry_price)
        # Target distance is risk_reward times the stop distance.
        assert abs(target_dist - cfg.risk_reward * stop_dist) < 1e-6 * t.entry_price


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} tests passed")


if __name__ == "__main__":
    _run_all()
