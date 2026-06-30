# Low-Lag Trend Predictor (Pine Script)

A TradingView indicator (`trend_predictor.pine`, Pine v6) that labels the current
market regime as **Uptrend**, **Downtrend**, or **Sideways**, designed to react
with as little lag as practical.

## How to use

1. Open [TradingView](https://www.tradingview.com) → any chart → **Pine Editor**.
2. Paste the contents of `trend_predictor.pine`.
3. Click **Add to chart**.

You get:
- A colored **HMA line** (teal = up, red = down, gray = sideways) + an orange ZLEMA.
- A **background tint** for the current regime.
- A **status label** showing the state plus live ADX, Choppiness, and HMA slope.
- **Alerts** that fire on each regime change.

## How it minimizes lag

| Job | Tool | Why it's low-lag |
|-----|------|------------------|
| Direction | **Hull MA (HMA)** | Weighted construction that tracks price far faster than EMA/SMA of the same length. |
| Early confirmation | **Zero-Lag EMA** | Pre-adds recent momentum to de-lag the input before smoothing. |
| Trend vs chop | **ADX + Choppiness Index** | Reports a flat tape as *Sideways* instead of forcing a fake trend. |
| Threshold scaling | **ATR-normalized HMA slope** | The "is it really moving?" test adapts to each instrument's volatility. |

### Classification logic

- **Trending?** `ADX ≥ threshold` **and** `Choppiness ≤ threshold`.
- **Uptrend:** trending **and** HMA rising ≥ `slopeAtrMin` ATR/bar **and** `close > HMA` **and** `DI+ ≥ DI−`.
- **Downtrend:** trending **and** HMA falling **and** `close < HMA` **and** `DI− > DI+`.
- **Sideways:** anything else.

## Lag vs. repainting (read this)

No indicator on **closed** bars can be truly zero-lag — any smoothing carries
*some* delay; this design minimizes it, it doesn't abolish it. The honest
trade-off is exposed as an input:

- `React intrabar (repaints)` **OFF** (default) — decisions commit on bar close.
  Stable, no repaint, slightly later.
- `React intrabar (repaints)` **ON** — decides on the live bar. Earlier, but the
  current bar's state can change until it closes.

This mirrors the parent repo's stance on **avoiding look-ahead bias**: the
default never uses information from an unfinished bar.

## Tuning

| Input | Effect |
|-------|--------|
| `Hull MA length` | Lower = faster & noisier, higher = smoother & slower. |
| `Zero-Lag EMA length` | Fast early-warning line length. |
| `ADX trend threshold` | Raise to demand stronger trends before leaving Sideways. |
| `Choppiness sideways threshold` | Raise to call Sideways more readily. |
| `Min HMA slope (in ATR)` | Minimum per-bar move (in ATRs) to count as trending. |

Starting points: scalping `HMA 21–34`, intraday `HMA 55` (default), swing `HMA 100+`.

## Disclaimer

For research and educational use only. Not financial advice. Backtested or
indicated signals do not predict future performance.
