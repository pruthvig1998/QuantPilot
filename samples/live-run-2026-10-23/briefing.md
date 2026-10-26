# QuantPilot Morning Briefing - Fri Oct 23, 2026
As of 10:21 AM ET (live)

## Market X-Ray
- Posture: MIXED - breadth 25.0% bullish / 25.0% bearish; 66.7% of the watchlist above the 200DMA
- Breadth: 3 bullish / 6 neutral / 3 bearish of 12 (stacks 4 up / 6 down; RSI 0 overbought / 0 oversold)
- Leading sectors: Energy, Healthcare, Consumer Discretionary
- Lagging sectors: Technology, Communication Services, Industrials
- Top sector: Energy (XLE) $68.77 (live) - momentum +10.43, RS vs SPY +10.70%
- Weakest sector: Industrials (XLI) $163.47 (live) - momentum -5.33, RS vs SPY -2.33%

## Liquidity Board
| Rank | Ticker | Price | Day % | Score | Direction | OI | Opt vol | Mom | Relvol |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | MSFT | $520.73 (live) | -0.07% | 20.5 | bullish | +0.46 | +0.57 | -0.31 | -0.00 |
| 2 | TSLA | $367.73 (live) | -1.83% | 19.7 | bullish | -0.01 | +0.35 | +0.45 | +0.00 |
| 3 | AAPL | $347.55 (live) | -0.19% | 19.1 | bullish | +0.27 | -0.02 | +0.22 | +0.31 |
| 4 | AMZN | $249.21 (live) | -0.47% | 11.1 | choppy | +0.06 | +0.50 | -0.13 | -0.00 |
| 5 | NVDA | $212.96 (live) | +0.35% | 5.2 | choppy | +0.31 | -0.10 | -0.06 | -0.00 |
| 6 | AMD | $517.72 (live) | +1.93% | 2.8 | choppy | -0.18 | +0.49 | -0.16 | -0.00 |
| 7 | QQQ | $705.25 (live) | +0.11% | 2.3 | choppy | -0.06 | +0.28 | -0.11 | -0.00 |
| 8 | AVGO | $325.69 (live) | +0.76% | -1.8 | choppy | -0.24 | +0.30 | -0.08 | -0.00 |
| 9 | NFLX | $67.24 (live) | +0.28% | -3.4 | choppy | +0.08 | +0.48 | -0.71 | -0.00 |
| 10 | GOOGL | $323.74 (live) | -0.15% | -4.7 | choppy | +0.09 | +0.46 | -0.77 | -0.00 |
| 11 | SPY | $760.54 (live) | -0.45% | -17.6 | bearish | -0.28 | -0.24 | -0.13 | -0.00 |
| 12 | META | $646.65 (live) | -0.34% | -36.9 | bearish | -0.31 | -0.15 | -0.95 | -0.00 |
Choppy / no read: AMZN (score 11.1), NVDA (score 5.2), AMD (score 2.8), QQQ (score 2.3), AVGO (score -1.8), NFLX (score -3.4), GOOGL (score -4.7)

## Trade Cards
### META - SKIP (no trade)
- Nearest candidate: META261028C00625000 call, strike $625.00, exp 2026-10-28 (5 DTE), premium $24.48 (live)
- Levels: spot $646.65 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +0.4% by 2026-10-28 to break even; model probability of profit 45%; bleeds $76.65/day in theta per contract
- Sector: META: sector XLC ranks #9 of 10 (lagging), market posture mixed.
- Risk review: not applicable - the card is a no_trade (SKIP).
- Why: META: SKIP (conviction 7/10, none bias). Packet shows deeply bearish liquidity (-36.92), price below EMA stack, and three unmitigated bearish order blocks starting at current price; the sole ranked call's breakeven sits inside the first block, and FOMC event risk on expiry day adds unquantifiable uncertainty. Bull case: META trades 2.2% above its 200‑day moving average [indicators.long_filter.price_above_200dma = true, indicators.long_filter.distance_200dma_pct = 2.229456875245407] with daily RSI at 36.4, signaling a potential oversold bounce [indicators.rsi_daily = 36.43292041644055]. Earnings risk has passed (two days ago) [events.earnings.days_away = -2], leaving only the FOMC decision in five days as a known catalyst [events.mar Bear case: The liquidity composite is deeply bearish at -36.92 with every component negative [liquidity.score = -36.92, liquidity.direction = "bearish", liquidity.components.momentum = -0.9481, liquidity.components.options_oi = -0.3126, liquidity.components.options_volume = -0.1534]. Price sits below the entire EMA stack [indicators.ema.price_below_stack = true] and has fallen 8.84% over the last five sessions [liquidity.inputs Biggest risk: FOMC decision on expiration day (2026-10-28) could trigger gap move that overwhelms the 5-day holding window.
- Reason: judge verdict SKIP. Packet shows deeply bearish liquidity (-36.92), price below EMA stack, and three unmitigated bearish order blocks starting at current price; the sole ranked call's breakeven sits inside the first b...
- Checks: 8 passed / 4 failed / 3 unknown of 15
-   failed: market_event_in_window (events) - market event(s) inside the 5-day window: FOMC 2026-10-28 (5d)
-   failed: delta_band (selection) - |delta| 0.81 vs target band 0.25-0.45 around 0.35
-   failed: option_volume (selection) - contract volume 2 vs 50 minimum
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

### MSFT - WATCH (no trade)
- Nearest candidate: MSFT261030C00537500 call, strike $537.50, exp 2026-10-30 (7 DTE), premium $6.30 (live)
- Levels: spot $520.73 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +4.4% by 2026-10-30 to break even; model probability of profit 23%; bleeds $79.25/day in theta per contract
- Sector: MSFT: sector XLK ranks #8 of 10 (lagging), market posture mixed.
- Risk review: not applicable - the card is a no_trade (WATCH).
- Why: MSFT: WATCH (conviction 4/10, none bias). Mixed evidence: long-term uptrend but short-term weakness and major event risk with unknown IV rank; options have low probability of profit and high theta. Watch for post-event setup. Bull case: MSFT sits in a confirmed uptrend regime with price 19.3% above the 200 DMA [indicators.regime = "uptrend", indicators.long_filter.distance_200dma_pct = 19.297821733239147], and the 7-day options window captures two major catalysts - earnings and an FOMC decision - both in 5 days [events.earnings.days_away = 5, events.market_events_in_window[0].days_away = 5]. The three ranked calls (532.5/535/537.5 strikes) offer del Bear case: The bull case leans on a long‑term uptrend (19.3% above the 200 DMA) but ignores that price currently sits below the short‑term EMA stack [indicators.ema.price_below_stack = true], volume is only 12% of its 20‑day average [liquidity.inputs.relative_volume = 0.1207388534761133], and the 5‑day return is negative [liquidity.inputs.ret_5d_pct = -1.57]. More critically, both earnings and the FOMC decision land inside the Biggest risk: Unknown IV rank with earnings and FOMC in the 5-day window makes IV crush risk unquantifiable, while low probability of profit and high theta decay require a sharp directional move to overcome.
- Reason: judge verdict WATCH. Mixed evidence: long-term uptrend but short-term weakness and major event risk with unknown IV rank; options have low probability of profit and high theta. Watch for post-event setup.
- Checks: 9 passed / 3 failed / 3 unknown of 15
-   failed: earnings_in_window (events) - earnings on 2026-10-28, 5 day(s) away, inside the 5-day holding window
-   failed: market_event_in_window (events) - market event(s) inside the 5-day window: FOMC 2026-10-28 (5d)
-   failed: option_volume (selection) - contract volume 14 vs 50 minimum
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

### TSLA - WATCH (no trade)
- Nearest candidate: TSLA261028C00377500 call, strike $377.50, exp 2026-10-28 (5 DTE), premium $4.50 (live)
- Levels: spot $367.73 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +3.9% by 2026-10-28 to break even; model probability of profit 23%; bleeds $70.64/day in theta per contract
- Sector: TSLA: sector XLY ranks #3 of 10 (leading), market posture mixed.
- Risk review: not applicable - the card is a no_trade (WATCH).
- Why: TSLA: WATCH (conviction 4/10, none bias). Bullish options flow conflicts with price below 200 DMA, bearish overhead order blocks, and low volume; FOMC event risk and unavailable IV rank leave directional edge unproven. Bull case: The liquidity profile shows bullish direction with a score of 19.72, driven by call volume of 5,078 versus put volume of 2,456 and a 3.67% five-day return [liquidity.direction = "bullish", liquidity.inputs.call_volume = 5078, liquidity.inputs.put_volume = 2456, liquidity.inputs.ret_5d_pct = 3.67]. The EMA stack is bullishly aligned [indicators.ema.bullish_stack = true], and price sits directly on a 7-touch equal-lows Bear case: Price sits 4.8% below the 200 DMA [indicators.long_filter.distance_200dma_pct = -4.814578842035979, indicators.long_filter.price_above_200dma = false] and remains under the bullish EMA stack [indicators.ema.price_below_stack = true], confirming the primary downtrend is intact. Daily volume is a mere 24% of the 20-day average [indicators.volume.relative_volume = 0.2407895206094735], signaling no institutional convicti Biggest risk: FOMC decision in 5 days with unknown IV rank could trigger vol expansion or crush while theta burns >$70/day on all 5-day options.
- Reason: judge verdict WATCH. Bullish options flow conflicts with price below 200 DMA, bearish overhead order blocks, and low volume; FOMC event risk and unavailable IV rank leave directional edge unproven.
- Checks: 11 passed / 1 failed / 3 unknown of 15
-   failed: market_event_in_window (events) - market event(s) inside the 5-day window: FOMC 2026-10-28 (5d)
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

## Risk Flags
- META: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- MSFT: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- TSLA: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- Market events inside the holding window: FOMC 2026-10-28 (in 5d)

## Journal
- Entries: 6 | scored: 0 | hits 0 / losses 0 | hit rate unknown (nothing scored yet)

Educational only - not financial advice.
