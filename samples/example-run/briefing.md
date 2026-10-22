# QuantPilot Morning Briefing - Fri Oct 23, 2026
As of 8:30 AM ET (premarket)

## Market X-Ray
- Posture: MIXED - breadth 58.3% bullish / 41.7% bearish; 58.3% of the watchlist above the 200DMA
- Breadth: 7 bullish / 0 neutral / 5 bearish of 12 (stacks 7 up / 5 down; RSI 7 overbought / 5 oversold)
- Leading sectors: Technology, Healthcare, Energy
- Lagging sectors: Utilities, Real Estate, Communication Services
- Top sector: Technology (XLK) $139.00 (premarket) - momentum +1.98, RS vs SPY +2.80%
- Weakest sector: Communication Services (XLC) $131.00 (premarket) - momentum -2.08, RS vs SPY +0.00%

## Liquidity Board
| Rank | Ticker | Price | Day % | Score | Direction | OI | Opt vol | Mom | Relvol |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | TSLA | $248.30 (premarket) | +2.31% | 49.1 | bullish | +0.57 | +0.57 | +0.36 | +0.45 |
| 2 | SPY | $102.00 (premarket) | -1.19% | -5.3 | choppy | +0.01 | +0.01 | -0.24 | -0.00 |
| 3 | AMD | $110.00 (premarket) | -1.19% | -5.9 | choppy | +0.00 | +0.00 | -0.24 | -0.00 |
| 4 | NVDA | $187.45 (premarket) | -1.39% | -40.7 | bearish | -0.54 | -0.54 | -0.27 | -0.23 |
Choppy / no read: SPY (score -5.3), AMD (score -5.9)
No data: NFLX (options tables not registered for NFLX (fixture))

## Trade Cards
### TSLA - TRADE call | conviction 7/10
- Contract: TSLA261027C00252500 call, strike $252.50, exp 2026-10-27 (4 DTE), premium $2.81 (premarket)
- Levels: spot $248.30 (premarket) | entry $243.56 | stop $242.83 | target $255.10 (liquidity_pool)
- Size: 1 contract | premium outlay $281.00 | risk budget $100.00 (1% of $10,000.00)
- Greeks: needs +2.8% by 2026-10-27 to break even; model probability of profit 26%; bleeds $52.26/day in theta per contract
- Sector: TSLA: sector XLY ranks #5 of 10 (neutral), market posture mixed.
- Risk review: cleared - no failed crush/earnings check, sized at 1 contract(s), reward:risk 15.83.
- Why: TSLA: TRADE (conviction 7/10, call bias). Uptrend, top board score and a surviving in-band call outweigh the event flag, which the card surfaces as a failed check. Bull case: TSLA is in an uptrend [indicators.regime = uptrend] with price above the 200DMA [indicators.long_filter.price_above_200dma = true]. The liquidity board ranks it top of this run [liquidity.score = 49.12], and the nearest bullish order block below spot gives a defined entry zone. Bear case: The bull case ignores the calendar: the FOMC decision lands inside the holding window [events.market_events_in_window = FOMC 2026-10-28], and the packet carries no IV rank [events.iv.rank_pct = null], so premium crush into the print cannot be scored. STRONGEST BEAR EVIDENCE: events.market_events_in_window includes FOMC 2026-10-28 Biggest risk: FOMC decision on 2026-10-28 lands inside the holding window; event volatility can crush the premium even if direction is right.
- Checks: 10 passed / 1 failed / 4 unknown of 15
-   failed: market_event_in_window (events) - market event(s) inside the 5-day window: FOMC 2026-10-28 (5d)
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

### NVDA - WATCH (no trade)
- Nearest candidate: NVDA261027P00185000 put, strike $185.00, exp 2026-10-27 (4 DTE), premium $1.96 (premarket)
- Levels: spot $187.45 (premarket) | entry unknown | stop unknown | target unknown (no target in packet)
- Greeks: needs -2.4% by 2026-10-27 to break even; model probability of profit 28%; bleeds $34.01/day in theta per contract
- Sector: NVDA: sector XLK ranks #1 of 10 (leading), market posture mixed.
- Risk review: not applicable - the card is a no_trade (WATCH).
- Why: Round 1 came back INSUFFICIENT_EVIDENCE (gap: events.iv.rank_pct is null in the packet - the crush-risk check cannot be scored without an IV rank). After the follow-up pass, WATCH (conviction 4/10, put bias). Direction leans put on trend and board score, but the IV rank gap persisted through round 2, so this stays a WATCH, not a trade. Bull case: CONCEDED: this gap cannot be resolved from the packet. The downtrend evidence stands [indicators.regime = downtrend] and the board score is -40.74 [liquidity.score = -40.74], but IV rank stays unknown in packet. Bear case: The concession settles it: direction leans put, yet with IV rank unknown in packet the premium side is unscoreable, so a trade cannot be sized honestly. STRONGEST BEAR EVIDENCE: events.iv.rank_pct = null Biggest risk: Paying unscored IV into the Oct 28 FOMC window.
- Reason: judge verdict WATCH. Direction leans put on trend and board score, but the IV rank gap persisted through round 2, so this stays a WATCH, not a trade.
- Checks: 10 passed / 1 failed / 4 unknown of 15
-   failed: market_event_in_window (events) - market event(s) inside the 5-day window: FOMC 2026-10-28 (5d)
-   unknown: iv_rank_known (events) - unknown - 52-week IV range unavailable, so no IV rank can be computed
-   unknown: iv_elevated (events) - unknown - no IV rank, so elevation cannot be judged

## Risk Flags
- NVDA: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- TSLA: IV rank unknown - 52-week IV history unavailable; event risk cannot be scored
- Market events inside the holding window: FOMC 2026-10-28 (in 5d)

## Journal
- Entries: 5 | scored: 2 | hits 1 / losses 1 | hit rate 50.0%
- TRADE: 2 scored, 1 hits, hit rate 50.0%

Educational only - not financial advice.
