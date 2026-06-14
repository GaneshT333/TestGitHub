# Pine Script — MTF Intraday (HTF bias + 1‑minute entry)

`MTF_Intraday_Strategy.pine` is a TradingView **Pine Script v5 strategy** that
implements the same approach as the Python framework in this repo:

> **Analyse trend + strength on a higher timeframe, then take precise entries on
> the 1‑minute chart, with buy/sell signals.**

## How to use

1. Open TradingView → **Pine Editor**.
2. Paste the contents of `MTF_Intraday_Strategy.pine` and click **Add to chart**.
3. **Run the chart on the 1‑minute timeframe** (the entry timeframe).
4. Set the **Higher timeframe (analysis)** input to your bias timeframe
   (default `15` — try `30` or `60`).
5. Read results in the **Strategy Tester** tab; tune the inputs per market.

## Signal logic

**Higher‑timeframe bias** (non‑repainting — uses the last *closed* HTF bar):
- `EMA fast > EMA slow` and `close > EMA slow` → up; opposite → down
- `ADX ≥ threshold` confirms a real trend (filters chop)
- → bias = **LONG / SHORT / FLAT**

**1‑minute entry** (only in the bias direction):
- Trigger: **pullback to the fast EMA then resume**, *or* **breakout** of the
  recent N‑bar range
- Confirmations: RSI inside a healthy band, price on the correct side of **VWAP**,
  and **volume above its average**

**Risk:** ATR stop + fixed reward:risk target, position sized to a % of equity,
session window, daily‑loss halt, max‑trades‑per‑day, and force‑flat at session end.

A **BUY**/**SELL** label is plotted at each entry, and matching `alertcondition`s
let you wire up TradingView alerts/webhooks.

## Mapping to `config.yaml`

The inputs mirror the Python `config.yaml` 1‑for‑1 (HTF EMAs + ADX, LTF EMAs,
RSI bands, pullback/breakout lookbacks, VWAP/volume filters, ATR stop, reward:risk,
risk‑per‑trade, session, max trades/day, daily‑loss halt), so a setup tuned in the
backtester transfers directly to the chart.

## Note on the source video

This script was built from the repo's existing multi‑timeframe spec because the
linked YouTube video could not be fetched in this environment. If the video
teaches specific rules (exact indicators, timeframes, or entry/exit conditions),
share them and the inputs/logic can be matched precisely.

> Research/education only. Not financial advice. Backtest and paper‑trade first.
