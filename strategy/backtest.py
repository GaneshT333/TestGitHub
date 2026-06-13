"""Event-driven backtester for the multi-timeframe intraday strategy.

Design goals
------------
* No look-ahead: a signal on bar *t* is filled at the open of bar *t+1*.
* Realistic intraday rules: ATR stop, fixed R:R target, force-flat at session
  end, max trades/day, and a daily-loss circuit breaker.
* Honest accounting: commission + slippage applied to every fill, position
  sized from the configured risk-per-trade.

Only one position is held at a time, which matches how a single intraday
strategy is typically run on one instrument.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

import numpy as np
import pandas as pd

from .config import StrategyConfig
from .strategy import IntradayMTFStrategy, LONG, SHORT, FLAT


@dataclass
class Trade:
    direction: int                 # LONG / SHORT
    entry_time: pd.Timestamp
    entry_price: float
    size: float
    stop: float
    target: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    pnl: float = 0.0
    reason: str = ""               # stop / target / session_close / eod

    @property
    def r_multiple(self) -> float:
        risk = abs(self.entry_price - self.stop) * self.size
        return self.pnl / risk if risk else 0.0


@dataclass
class BacktestResult:
    trades: list[Trade]
    equity_curve: pd.Series
    config: StrategyConfig
    stats: dict = field(default_factory=dict)

    def summary(self) -> str:
        s = self.stats
        lines = [
            "================ Backtest Summary ================",
            f"Trades:            {s['n_trades']}",
            f"Win rate:          {s['win_rate']:.1%}",
            f"Avg R / trade:     {s['avg_r']:.2f}R",
            f"Expectancy:        {s['expectancy']:.2f}R",
            f"Profit factor:     {s['profit_factor']:.2f}",
            f"Net P&L:           {s['net_pnl']:,.2f}",
            f"Return:            {s['return_pct']:.2%}",
            f"Max drawdown:      {s['max_drawdown_pct']:.2%}",
            f"Sharpe (per-trade):{s['sharpe']:.2f}",
            f"Final equity:      {s['final_equity']:,.2f}",
            "==================================================",
        ]
        return "\n".join(lines)


def _parse_time(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


class Backtester:
    def __init__(self, config: StrategyConfig | None = None):
        self.cfg = config or StrategyConfig()
        self.cfg.validate()
        self.strategy = IntradayMTFStrategy(self.cfg)

    # ------------------------------------------------------------------ #
    def run(self, ltf_df: pd.DataFrame) -> BacktestResult:
        cfg = self.cfg
        df = self.strategy.compute_signals(ltf_df)

        sess_start = _parse_time(cfg.session_start)
        sess_end = _parse_time(cfg.session_end)
        no_entry_after = _parse_time(cfg.no_entry_after)

        equity = cfg.initial_equity
        trades: list[Trade] = []
        equity_times: list[pd.Timestamp] = []
        equity_vals: list[float] = []

        open_trade: Trade | None = None
        current_day = None
        trades_today = 0
        day_start_equity = equity
        halted_today = False

        # Pre-extract numpy arrays for speed and clarity.
        idx = df.index
        op = df["open"].to_numpy()
        hi = df["high"].to_numpy()
        lo = df["low"].to_numpy()
        atr_arr = df["atr"].to_numpy()
        sig = df["signal"].to_numpy()

        n = len(df)
        for i in range(n):
            ts = idx[i]
            t = ts.time()
            day = ts.date()

            if day != current_day:
                current_day = day
                trades_today = 0
                day_start_equity = equity
                halted_today = False

            in_session = sess_start <= t <= sess_end

            # ---- Manage an open position first (exits take priority) ----
            if open_trade is not None:
                exit_price, reason = self._check_exit(open_trade, hi[i], lo[i])
                # Force flat at/after the session-end time if not already stopped.
                if exit_price is None and t >= sess_end:
                    exit_price, reason = df["close"].iat[i], "session_close"
                if exit_price is not None:
                    equity = self._close_trade(open_trade, exit_price, ts, reason, equity)
                    trades.append(open_trade)
                    open_trade = None
                    # Daily-loss circuit breaker.
                    if (day_start_equity - equity) >= cfg.max_daily_loss * day_start_equity:
                        halted_today = True

            equity_times.append(ts)
            equity_vals.append(equity + self._open_pnl(open_trade, df["close"].iat[i]))

            # ---- Look for a new entry (filled next bar's open) ----
            if open_trade is not None or halted_today or not in_session:
                continue
            if t > no_entry_after or trades_today >= cfg.max_trades_per_day:
                continue
            if sig[i] == FLAT or i + 1 >= n:
                continue
            if np.isnan(atr_arr[i]) or atr_arr[i] <= 0:
                continue

            direction = int(sig[i])
            fill_price = self._apply_slippage(op[i + 1], direction, entering=True)
            open_trade = self._open_trade(direction, idx[i + 1], fill_price, atr_arr[i], equity)
            trades_today += 1

        # Close anything still open at the final bar.
        if open_trade is not None:
            last_close = df["close"].iat[-1]
            equity = self._close_trade(open_trade, last_close, idx[-1], "eod", equity)
            trades.append(open_trade)
            equity_vals[-1] = equity

        equity_curve = pd.Series(equity_vals, index=pd.DatetimeIndex(equity_times))
        stats = self._compute_stats(trades, equity_curve)
        return BacktestResult(trades, equity_curve, cfg, stats)

    # ------------------------------------------------------------------ #
    # Trade lifecycle helpers
    # ------------------------------------------------------------------ #
    def _open_trade(self, direction, ts, price, atr_val, equity) -> Trade:
        cfg = self.cfg
        stop_dist = cfg.atr_stop_mult * atr_val
        if direction == LONG:
            stop = price - stop_dist
            target = price + cfg.risk_reward * stop_dist
        else:
            stop = price + stop_dist
            target = price - cfg.risk_reward * stop_dist

        risk_cash = cfg.risk_per_trade * equity
        size = risk_cash / stop_dist if stop_dist > 0 else 0.0
        return Trade(direction, ts, price, size, stop, target)

    def _check_exit(self, trade: Trade, high, low):
        """Return (exit_price, reason), or (None, "") if neither stop nor target hit.

        Within a bar we cannot know whether the stop or the target was touched
        first, so we conservatively assume the *stop* fills first — this avoids
        flattering the results.
        """
        if trade.direction == LONG:
            if low <= trade.stop:
                return trade.stop, "stop"
            if high >= trade.target:
                return trade.target, "target"
        else:
            if high >= trade.stop:
                return trade.stop, "stop"
            if low <= trade.target:
                return trade.target, "target"
        return None, ""

    def _close_trade(self, trade: Trade, raw_price, ts, reason, equity) -> float:
        cfg = self.cfg
        # Exit slippage works against us (opposite sign to entry).
        price = self._apply_slippage(raw_price, trade.direction, entering=False)
        gross = (price - trade.entry_price) * trade.size * trade.direction
        costs = 2 * cfg.commission_per_trade  # entry + exit
        trade.exit_time = ts
        trade.exit_price = price
        trade.reason = reason
        trade.pnl = gross - costs
        return equity + trade.pnl

    def _open_pnl(self, trade: Trade | None, mark_price: float) -> float:
        if trade is None:
            return 0.0
        return (mark_price - trade.entry_price) * trade.size * trade.direction

    def _apply_slippage(self, price, direction, entering: bool) -> float:
        bps = self.cfg.slippage_bps / 10_000.0
        # Buys (entering long / exiting short) pay up; sells receive less.
        sign = direction if entering else -direction
        return price * (1 + sign * bps)

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #
    def _compute_stats(self, trades: list[Trade], equity_curve: pd.Series) -> dict:
        cfg = self.cfg
        n = len(trades)
        if n == 0:
            return {
                "n_trades": 0, "win_rate": 0.0, "avg_r": 0.0, "expectancy": 0.0,
                "profit_factor": 0.0, "net_pnl": 0.0, "return_pct": 0.0,
                "max_drawdown_pct": 0.0, "sharpe": 0.0,
                "final_equity": cfg.initial_equity,
            }

        pnls = np.array([t.pnl for t in trades])
        r_mult = np.array([t.r_multiple for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        gross_win = wins.sum()
        gross_loss = -losses.sum()
        net_pnl = pnls.sum()

        roll_max = equity_curve.cummax()
        drawdown = (equity_curve - roll_max) / roll_max
        max_dd = drawdown.min() if len(drawdown) else 0.0

        sharpe = (r_mult.mean() / r_mult.std(ddof=1) * np.sqrt(n)) if (n > 1 and r_mult.std(ddof=1) > 0) else 0.0

        return {
            "n_trades": n,
            "win_rate": len(wins) / n,
            "avg_r": float(r_mult.mean()),
            "expectancy": float(r_mult.mean()),
            "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            "net_pnl": float(net_pnl),
            "return_pct": float(net_pnl / cfg.initial_equity),
            "max_drawdown_pct": float(max_dd),
            "sharpe": float(sharpe),
            "final_equity": float(cfg.initial_equity + net_pnl),
        }
