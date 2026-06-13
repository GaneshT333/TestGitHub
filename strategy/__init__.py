"""Multi-timeframe intraday trading strategy.

Bias and structure are analysed on a higher timeframe (e.g. 15m / 1h / daily)
and entries are executed on a lower timeframe (1m / 5m).
"""

from .strategy import IntradayMTFStrategy
from .config import StrategyConfig
from .backtest import Backtester, BacktestResult

__all__ = [
    "IntradayMTFStrategy",
    "StrategyConfig",
    "Backtester",
    "BacktestResult",
]

__version__ = "0.1.0"
