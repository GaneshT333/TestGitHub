# Multi-Timeframe Intraday Trading Strategy

A complete, market-agnostic intraday strategy framework that does what serious
intraday traders actually do:

> **Analyse the trend and structure on a higher timeframe, then execute precise
> entries on a 1-minute or 5-minute chart.**

It works on any market — equities, futures, FX, crypto — because the logic makes
no instrument-specific assumptions. You adapt it to a market by changing
parameters, not code.

---

## The strategy in one picture

```
Higher timeframe (e.g. 1H / 15m / Daily)      Lower timeframe (1m / 5m)
─────────────────────────────────────         ───────────────────────────────
  EMA20 vs EMA50  ──► trend direction          Trade ONLY with the HTF bias
  ADX ≥ threshold ──► trend is strong   ──►    Entry trigger:
                                                 • pullback to EMA9 then resume, OR
  Output: bias = LONG / SHORT / FLAT             • micro-structure breakout
                                               Confirmations:
                                                 • RSI in a healthy band
                                                 • price on correct side of VWAP
                                                 • volume above its average
                                               Risk: ATR stop + fixed R:R target
```

Why this works: the higher timeframe keeps you on the right side of the market
and filters out choppy regimes (via ADX), while the lower timeframe gives you a
tight, well-defined risk entry. You never take counter-trend trades.

### How signals are combined without cheating

The single most common reason an intraday backtest looks amazing and then loses
money live is **look-ahead bias** — using information that wasn't available yet.
This framework is careful about it:

- The HTF bias is carried onto the LTF with `pandas.merge_asof(direction="backward")`,
  so a 5-minute bar at 10:05 only ever sees the **last fully-closed** hourly bar.
- A signal on bar *t* is **filled at the open of bar *t+1***, never at the close
  of the bar that produced it.
- Inside a bar, when both stop and target are touched, the **stop is assumed to
  fill first** (conservative).

These rules are enforced and covered by tests (`test_htf_bias_no_lookahead`,
`test_signals_only_in_bias_direction`).

---

## Quick start

```bash
pip install -r requirements.txt

# Run on built-in synthetic data — no network or data files required:
python run_backtest.py --source synthetic --days 40 --ltf 5min --htf 1H

# Same engine, 1-minute entries with a 15-minute bias:
python run_backtest.py --source synthetic --days 20 --ltf 1min --htf 15min
```

Example output:

```
Loaded 3,120 5min bars (2024-01-02 09:30:00 -> 2024-02-10 15:55:00)
Analysis timeframe: 1H | Execution timeframe: 5min

================ Backtest Summary ================
Trades:            62
Win rate:          41.9%
Avg R / trade:     0.15R
Profit factor:     1.24
Net P&L:           8,945.44
Return:            8.95%
Max drawdown:      -9.41%
Sharpe (per-trade):0.81
Final equity:      108,945.44
==================================================
```

> The synthetic generator produces **random** intraday data for smoke-testing
> the engine; its numbers are not a performance claim. Run it on real data
> (below) before drawing any conclusion.

---

## Running on real data

### Your own CSV

Provide a CSV with a `datetime` column plus `open, high, low, close, volume`:

```bash
python run_backtest.py --source csv --csv data/aapl_1min.csv --ltf 1min --htf 30min \
    --save-trades trades.csv --save-equity equity.csv
```

### Yahoo Finance (optional)

```bash
pip install yfinance
python run_backtest.py --source yfinance --symbol AAPL --interval 5m --period 1mo
```

> Intraday history from free feeds is limited (Yahoo: ~60 days of 5m, ~7 days of
> 1m). For serious research use a paid intraday feed and the CSV path.

---

## Configuration

Every tunable lives in `config.yaml` (or a `StrategyConfig` object). Pass a file
with `--config`, or override the timeframes inline with `--ltf` / `--htf`.

```bash
python run_backtest.py --source synthetic --config config.yaml
```

Key parameters:

| Group | Parameter | Meaning |
|-------|-----------|---------|
| Timeframes | `ltf`, `htf` | execution vs. analysis timeframe |
| HTF bias | `htf_ema_fast/slow`, `htf_adx_min` | trend direction & strength filter |
| LTF entry | `ltf_ema_fast/slow`, `rsi_*`, `use_vwap_filter`, `volume_mult` | entry triggers & confirmations |
| Risk | `atr_stop_mult`, `risk_reward`, `risk_per_trade` | stop, target, position size |
| Session | `session_start/end`, `no_entry_after`, `max_trades_per_day`, `max_daily_loss` | intraday guard-rails |
| Costs | `commission_per_trade`, `slippage_bps` | realistic fills |

### Tuning per market (starting points)

| Market | `ltf` | `htf` | Notes |
|--------|-------|-------|-------|
| US equities / index ETFs | `5min` | `1H` | session 09:30–16:00 |
| Index futures (ES/NQ) | `1min`/`5min` | `15min`/`1H` | nearly 24h — widen session window |
| FX majors | `5min` | `1H`/`4H` | set session to your trading window |
| Crypto | `5min` | `1H`/`4H` | 24/7 — set session to `00:00`/`23:59` |

---

## Project layout

```
strategy/
  config.py        StrategyConfig dataclass + YAML loading and validation
  data.py          CSV / yfinance / synthetic loaders, resampling, freq aliases
  indicators.py    EMA, SMA, RSI, ATR, ADX, VWAP, rolling extremes (vectorised)
  strategy.py      HTF bias + LTF entry signal generation (the core logic)
  backtest.py      event-driven backtester, risk management, statistics
run_backtest.py    command-line runner
config.yaml        default configuration
tests/             test suite incl. look-ahead-bias guards
```

## Risk management built in

- **ATR-based stop** sized to current volatility, with a **fixed reward:risk
  target** (default 2R).
- **Position sizing** from a fixed fraction of equity risked per trade
  (default 1%).
- **Circuit breakers**: max trades per day, force-flat at session end, and a
  daily-loss halt that stops trading after a configurable drawdown.
- **Costs**: commission and basis-point slippage applied to every fill.

## Tests

```bash
python tests/test_strategy.py      # standalone
# or
pytest -q                          # if pytest is installed
```

---

## ⚠️ Disclaimer

This software is for **research and educational purposes only**. It is not
financial advice and comes with no guarantee of profitability. Backtested
results do not predict future performance. Trading leveraged intraday products
carries substantial risk of loss. Test thoroughly on out-of-sample data and
paper-trade before risking real capital.
