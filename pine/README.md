# Pine Script — Inside Candle Strategy (HTF detection + 1‑minute entry)

`Inside_Candle_Strategy.pine` is a TradingView **Pine Script v5 strategy** that
implements the **Inside Candle (Inside Bar) strategy** from the source video,
detecting the pattern on a **higher timeframe** and taking entries on the
**1‑minute** chart with BUY/SELL signals.

## The strategy

An **inside candle** forms entirely within the previous ("mother") candle's
high–low range:

```
mother high ─────────┐
                     │   ┌── inside high   ← break UP  = BUY
   mother candle     │   │  inside candle
                     │   └── inside low    ← break DOWN = SELL
mother low  ─────────┘
```

- **Entry:** break of the inside candle's **high → BUY**, break of its **low → SELL**
- **Stop loss:** inside candle's low (long) / high (short) — optionally the wider
  mother‑candle extreme
- **Target:** minimum **1:2 / 1:3** reward:risk; optional trailing stop to ride
  big moves

## "Edge" rules from the video (built in as filters)

1. **Opening counter‑trend filter** — near the open, only trade in the session's
   initial (gap / first‑candle) direction. Reversals are allowed later in the day.
2. **New inside candle supersedes the old** — levels refresh when a newer
   qualifying inside candle appears.
3. **Smaller inside candle is stronger** — `Max inside/mother range ratio`
   rejects inside candles that are too large relative to the mother.
4. **Avoid a large inside body** — `Reject large inside body` skips inside
   candles whose body is big vs the mother candle.
5. **False‑breakout (trap) protection** — the `Close beyond level` trigger
   requires a *close* past the high/low instead of a bare wick, filtering many
   fake breakouts. Switch to `Wick beyond level` for the raw break.

## How to use

1. TradingView → **Pine Editor** → paste `Inside_Candle_Strategy.pine` → **Add to chart**.
2. **Run the chart on the 1‑minute timeframe** (the entry timeframe).
3. Set **Inside‑candle detection timeframe** to your structure timeframe
   (default `15`; the video demonstrated `5`).
4. Tune filters and risk in the settings; review results in the **Strategy Tester**.
5. Create alerts from the **BUY signal / SELL signal** `alertcondition`s for
   notifications or webhooks.

## Key inputs

| Group | Input | Meaning |
|-------|-------|---------|
| Timeframe | `detection timeframe` | where inside candles are detected (chart stays 1m) |
| Entry | `Breakout trigger` | close‑confirmed vs raw wick break |
| Filters | `range ratio`, `body ratio`, `expiry` | pattern‑quality gates |
| Risk | `SL level`, `Reward:Risk`, `trailing`, `risk per trade` | stops, targets, sizing |
| Session | `session`, `opening filter`, `no‑entry window`, `max trades`, `daily loss` | intraday guard‑rails |

## Non‑repainting note

Inside candles are read from **closed** higher‑timeframe bars
(`request.security` on `high[1]/high[2]` etc.), so signals do **not** repaint
after the fact.

> Research/education only. Not financial advice. Backtest and paper‑trade before
> risking real capital. Inside‑bar breakouts are prone to false breakouts —
> mind the trap rules from the video.
