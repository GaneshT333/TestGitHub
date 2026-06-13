#!/usr/bin/env python3
"""Command-line runner for the multi-timeframe intraday strategy.

Examples
--------
# Run on built-in synthetic data (no network, no data files needed):
python run_backtest.py --source synthetic --days 30

# Run on your own intraday CSV (datetime, open, high, low, close, volume):
python run_backtest.py --source csv --csv data/aapl_1min.csv --ltf 1min --htf 30min

# Run on Yahoo Finance intraday data (requires `pip install yfinance` + network):
python run_backtest.py --source yfinance --symbol AAPL --interval 5m --period 1mo
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from strategy import Backtester, StrategyConfig
from strategy import data as data_mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-timeframe intraday strategy backtest")
    p.add_argument("--source", choices=["synthetic", "csv", "yfinance"], default="synthetic")
    p.add_argument("--csv", help="path to an OHLCV CSV (for --source csv)")
    p.add_argument("--symbol", default="AAPL", help="ticker (for --source yfinance)")
    p.add_argument("--interval", default="5m", help="yfinance interval, e.g. 1m/5m")
    p.add_argument("--period", default="1mo", help="yfinance period, e.g. 5d/1mo")
    p.add_argument("--days", type=int, default=30, help="days of synthetic data")
    p.add_argument("--config", help="path to a YAML config overriding defaults")
    p.add_argument("--ltf", help="execution timeframe override, e.g. 1min/5min")
    p.add_argument("--htf", help="analysis timeframe override, e.g. 15min/1H")
    p.add_argument("--save-trades", help="write the trade log to this CSV path")
    p.add_argument("--save-equity", help="write the equity curve to this CSV path")
    return p


def load_config(args) -> StrategyConfig:
    cfg = StrategyConfig.from_yaml(args.config) if args.config else StrategyConfig()
    if args.ltf:
        cfg.ltf = args.ltf
    if args.htf:
        cfg.htf = args.htf
    cfg.validate()
    return cfg


def load_data(args, cfg: StrategyConfig) -> pd.DataFrame:
    if args.source == "synthetic":
        freq = cfg.ltf.replace("min", "min")
        return data_mod.generate_synthetic(days=args.days, freq=freq)
    if args.source == "csv":
        if not args.csv:
            sys.exit("error: --csv is required when --source csv")
        return data_mod.load_csv(args.csv)
    if args.source == "yfinance":
        return data_mod.load_yfinance(args.symbol, period=args.period, interval=args.interval)
    raise ValueError(args.source)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args)
    df = load_data(args, cfg)

    print(f"Loaded {len(df):,} {cfg.ltf} bars "
          f"({df.index[0]} -> {df.index[-1]})")
    print(f"Analysis timeframe: {cfg.htf} | Execution timeframe: {cfg.ltf}\n")

    result = Backtester(cfg).run(df)
    print(result.summary())

    if result.trades:
        last = result.trades[-5:]
        print("\nLast trades:")
        for t in last:
            print(f"  {t.entry_time} {('LONG' if t.direction == 1 else 'SHORT'):5} "
                  f"@ {t.entry_price:.2f} -> {t.exit_price:.2f} "
                  f"[{t.reason}] {t.r_multiple:+.2f}R")

    if args.save_trades and result.trades:
        rows = [vars(t) for t in result.trades]
        pd.DataFrame(rows).to_csv(args.save_trades, index=False)
        print(f"\nTrade log written to {args.save_trades}")
    if args.save_equity:
        result.equity_curve.to_csv(args.save_equity, header=["equity"])
        print(f"Equity curve written to {args.save_equity}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
