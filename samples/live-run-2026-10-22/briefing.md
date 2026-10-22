# QuantPilot Morning Briefing - Thu Oct 22, 2026
As of 10:20 AM ET (live)

## Market X-Ray
- Posture: MIXED - breadth 33.3% bullish / 25.0% bearish; 75.0% of the watchlist above the 200DMA
- Breadth: 4 bullish / 5 neutral / 3 bearish of 12 (stacks 4 up / 5 down; RSI 0 overbought / 0 oversold)
- Leading sectors: Energy, Healthcare, Consumer Discretionary
- Lagging sectors: Technology, Communication Services, Industrials
- Top sector: Energy (XLE) $67.32 (live) - momentum +8.40, RS vs SPY +9.77%
- Weakest sector: Industrials (XLI) $166.28 (live) - momentum -3.84, RS vs SPY -1.54%

## Liquidity Board
| Rank | Ticker | Price | Day % | Score | Direction | OI | Opt vol | Mom | Relvol |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TSLA | $388.39 (live) | unknown | 45.9 | bullish | +0.39 | +0.31 | +0.96 | +0.13 |
| 2 | AAPL | $345.06 (live) | unknown | 23.1 | bullish | +0.23 | +0.45 | +0.20 | +0.00 |
| 3 | AMZN | $253.37 (live) | unknown | 10.2 | choppy | +0.38 | +0.19 | -0.09 | -0.18 |
| 4 | NVDA | $217.09 (live) | unknown | 5.4 | choppy | +0.37 | +0.33 | -0.56 | -0.00 |
| 5 | MSFT | $526.27 (live) | unknown | -5.0 | choppy | +0.23 | -0.05 | -0.43 | -0.00 |
| 6 | SPY | $767.17 (live) | unknown | -6.5 | choppy | -0.17 | +0.19 | -0.10 | -0.17 |
| 7 | GOOGL | $328.18 (live) | unknown | -8.2 | choppy | +0.23 | +0.35 | -0.95 | -0.00 |
| 8 | AVGO | $330.70 (live) | unknown | -14.0 | choppy | +0.17 | +0.21 | -0.90 | -0.09 |
| 9 | NFLX | $66.22 (live) | unknown | -15.1 | bearish | -0.09 | +0.47 | -0.97 | -0.00 |
| 10 | QQQ | $714.85 (live) | unknown | -20.9 | bearish | -0.18 | -0.01 | -0.57 | -0.06 |
| 11 | AMD | $529.45 (live) | unknown | -22.1 | bearish | +0.04 | +0.09 | -0.98 | -0.04 |
| 12 | META | $660.00 (live) | unknown | -57.0 | bearish | -0.36 | -0.05 | -1.00 | -1.00 |
Choppy / no read: AMZN (score 10.2), NVDA (score 5.4), MSFT (score -5.0), SPY (score -6.5), GOOGL (score -8.2), AVGO (score -14.0)

## Trade Cards
### META - SKIP (no trade)
- Nearest candidate: META261023C00665000 call, strike $665.00, exp 2026-10-23 (1 DTE), premium $4.95 (live)
- Levels: spot $660.00 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +1.5% by 2026-10-23 to break even; model probability of profit 22%; bleeds $242.94/day in theta per contract
- Sector: META: sector XLC ranks #9 of 10 (lagging), market posture mixed.
- Risk review: not applicable - the card is a no_trade (SKIP).
- Why: META: SKIP (conviction 7/10, none bias). Packet shows strongly bearish liquidity composite (-57), put OI more than double call OI, price below short-term EMA stack, and all viable options expiring tomorrow with low probability of profit; the lone bullish signal is an untested order block formed minutes ago. Bull case: META's price at 660.01 remains 4.36% above its 200-day moving average of 632.43, confirming the long-term uptrend is intact [indicators.long_filter.price_above_200dma = true, indicators.long_filter.distance_200dma_pct = 4.360331146799366]. An unmitigated bullish order block formed today at 650.25-655.00 sits just 1.5% below the current print, marking a fresh demand zone that has not yet been tested [order_blocks.belo Bear case: The liquidity composite scores -57.02 with a bearish direction, driven by a -0.9982 momentum component and put open interest (114,586) more than doubling call open interest (53,683) [liquidity.score = -57.02, liquidity.direction = "bearish", liquidity.components.momentum = -0.9982, liquidity.inputs.put_oi = 114586.0, liquidity.inputs.call_oi = 53683.0]. Price sits 7.2% below the 9-day EMA (707.55) and 7.7% below the Biggest risk: Extreme put skew (75-79% IV vs 34-37% call IV) and 1-day expiry with high theta burn make any directional trade highly vulnerable to time decay and downside continuation.
- Reason: judge verdict SKIP. Packet shows strongly bearish liquidity composite (-57), put OI more than double call OI, price below short-term EMA stack, and all viable options expiring tomorrow with low probability of profit; ...
- Checks: 12 passed / 0 failed / 3 unknown of 15
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

### TSLA - WATCH (no trade)
- Nearest candidate: TSLA261023C00390000 call, strike $390.00, exp 2026-10-23 (1 DTE), premium $2.67 (live)
- Levels: spot $388.39 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +1.1% by 2026-10-23 to break even; model probability of profit 24%; bleeds $117.96/day in theta per contract
- Sector: TSLA: sector XLY ranks #3 of 10 (leading), market posture mixed.
- Risk review: not applicable - the card is a no_trade (WATCH).
- Why: TSLA: WATCH (conviction 0/10, none bias). Bull case: TSLA sits at the 20-day high with a bullish EMA stack and price above the 200 DMA by just 0.37% [indicators.breakouts.at_20d_high = true, indicators.ema.bullish_stack = true, indicators.long_filter.price_above_200dma = true, indicators.long_filter.distance_200dma_pct = 0.3734809774829841]. Options flow shows heavy call skew with call OI more than double put OI (214k vs 94k) and call volume nearly 2x put volume [liqui Bear case: The bull case leans heavily on a momentum reading of 0.96, but that component is backward-looking while every forward-looking options metric screams caution. Put implied volatilities are triple the call IVs (77-86% vs 19-30%) on 1-DTE contracts, signaling heavy downside hedging demand [guardrails.candidates[3].evaluation.metrics.implied_volatility = 0.7739280419921876, guardrails.candidates[4].evaluation.metrics.impl
- Reason: judge verdict WATCH
- Checks: 12 passed / 0 failed / 3 unknown of 15
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

### AAPL - WATCH (no trade)
- Nearest candidate: AAPL261023C00345000 call, strike $345.00, exp 2026-10-23 (1 DTE), premium $2.54 (live)
- Levels: spot $345.06 (live) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs +0.7% by 2026-10-23 to break even; model probability of profit 29%; bleeds $91.56/day in theta per contract
- Sector: AAPL: sector XLK ranks #8 of 10 (lagging), market posture mixed.
- Risk review: not applicable - the card is a no_trade (WATCH).
- Why: AAPL: WATCH (conviction 5/10, none bias). While AAPL shows a bullish trend and call-skewed flow, the guardrails model ranks puts higher, all liquid options are 0DTE with high theta burn, and IV rank is unknown, leaving directional edge unproven. Bull case: AAPL is in a confirmed uptrend with a bullish EMA stack and price 17.5% above the 200-day moving average [indicators.regime = "uptrend", indicators.ema.bullish_stack = true, indicators.long_filter.distance_200dma_pct = 17.54494992916362]. Options flow is heavily call-skewed with 151k call OI versus 96k put OI and 72k call volume versus 27k put volume [liquidity.inputs.call_oi = 151410.0, liquidity.inputs.put_oi = 956 Bear case: The bull’s call-skewed flow ignores that every liquid contract in the guardrails window expires tomorrow (1 DTE), forcing buyers to pay extreme theta - $84.52/day on the highlighted 342.5C - for a mere 37% probability of profit [guardrails.candidates[1].evaluation.metrics.theta_burn_usd_per_day = 84.52, guardrails.candidates[1].evaluation.metrics.probability_of_profit = 0.3719]. The guardrails model itself ranks puts Biggest risk: Extreme theta decay on 0DTE options combined with unknown IV rank makes premium valuation unreliable.
- Reason: judge verdict WATCH. While AAPL shows a bullish trend and call-skewed flow, the guardrails model ranks puts higher, all liquid options are 0DTE with high theta burn, and IV rank is unknown, leaving directional edge un...
- Checks: 11 passed / 1 failed / 3 unknown of 15
-   failed: delta_band (selection) - |delta| 0.51 vs target band 0.25-0.45 around 0.35
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

## Risk Flags
- AAPL: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- META: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- TSLA: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored

## Journal
- Entries: 3 | scored: 0 | hits 0 / losses 0 | hit rate unknown (nothing scored yet)

Educational only - not financial advice.
