"""Strategy configuration.

All tunables live here so the same engine can be applied to any market
(equities, futures, FX, crypto) simply by adjusting parameters — the logic
itself makes no market-specific assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import yaml


@dataclass
class StrategyConfig:
    # ----- Timeframes -----
    # Pandas offset aliases. The htf must be a strict multiple of the ltf.
    ltf: str = "5min"          # execution timeframe (entries): "1min" or "5min"
    htf: str = "1H"            # analysis timeframe (bias/structure)

    # ----- Higher-timeframe bias -----
    htf_ema_fast: int = 20
    htf_ema_slow: int = 50
    htf_adx_length: int = 14
    htf_adx_min: float = 20.0  # require a trending HTF before taking trades

    # ----- Lower-timeframe entry -----
    ltf_ema_fast: int = 9
    ltf_ema_slow: int = 21
    ltf_rsi_length: int = 14
    rsi_long_floor: float = 40.0   # avoid buying when already deeply oversold/falling
    rsi_long_ceiling: float = 70.0 # avoid chasing overbought
    rsi_short_floor: float = 30.0
    rsi_short_ceiling: float = 60.0
    pullback_lookback: int = 3     # bars to confirm a pullback before resumption
    breakout_lookback: int = 10    # micro structure breakout window
    use_vwap_filter: bool = True   # longs only above VWAP, shorts only below
    volume_ma_length: int = 20
    volume_mult: float = 1.0       # entry bar volume must exceed mult * avg volume

    # ----- Risk management -----
    atr_length: int = 14
    atr_stop_mult: float = 1.5     # stop distance = mult * ATR
    risk_reward: float = 2.0       # take-profit = risk_reward * stop distance
    risk_per_trade: float = 0.01   # fraction of equity risked per trade
    allow_long: bool = True
    allow_short: bool = True

    # ----- Session / circuit breakers -----
    session_start: str = "09:30"   # local exchange time (HH:MM), inclusive
    session_end: str = "15:55"     # flat-by time (HH:MM), inclusive
    no_entry_after: str = "15:30"  # stop opening new trades after this time
    max_trades_per_day: int = 4
    max_daily_loss: float = 0.03   # halt for the day after this equity drawdown

    # ----- Account / costs -----
    initial_equity: float = 100_000.0
    commission_per_trade: float = 0.0   # absolute cost per fill (entry & exit each)
    slippage_bps: float = 1.0           # basis points applied to every fill

    def validate(self) -> None:
        if self.htf_ema_fast >= self.htf_ema_slow:
            raise ValueError("htf_ema_fast must be < htf_ema_slow")
        if self.ltf_ema_fast >= self.ltf_ema_slow:
            raise ValueError("ltf_ema_fast must be < ltf_ema_slow")
        if not (0 < self.risk_per_trade < 1):
            raise ValueError("risk_per_trade must be in (0, 1)")
        if self.risk_reward <= 0:
            raise ValueError("risk_reward must be > 0")
        if self.atr_stop_mult <= 0:
            raise ValueError("atr_stop_mult must be > 0")
        if not (self.allow_long or self.allow_short):
            raise ValueError("at least one of allow_long / allow_short must be True")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyConfig":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        cfg = cls(**filtered)
        cfg.validate()
        return cfg

    @classmethod
    def from_yaml(cls, path: str) -> "StrategyConfig":
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return cls.from_dict(data)
