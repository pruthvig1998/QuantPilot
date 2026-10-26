# Impact study: can cheap weekly options actually win?

Live capture: 2026-10-26T19:00:40.442677+00:00 UTC (US market hours), the 12-name watchlist, every expiry 1-7 days out. Universe: contracts with a two-sided quote. Every contract was run through QuantPilot's own probability guardrail. Probability of profit is the guardrail's model estimate (lognormal, from the chain's own implied volatility), not a guarantee.

**5,349 tradeable contracts evaluated.**

## Headline

- **Cheap contracts** (premium <= $1.00 per share ($100 per contract)): 1,888 of them. Median modeled probability of profit **0.4%**; **99.8%** have less than a 20% modeled chance; **99.9%** fail QuantPilot's guardrail. Median move needed just to break even: 11.1%; median time decay: 42.8% of the premium per day.
- **Contracts that pass the guardrail**: 2,928. Median modeled probability of profit **47.0%**, median breakeven move 0.2%.

## By premium

| Premium (per share) | Contracts | Median modeled PoP | PoP below 20% | Fail the guardrail | Median breakeven move | Median decay per day (% of premium) |
|---|---|---|---|---|---|---|
| up to $0.50 | 1,647 | 0.3% | 99.9% | 100.0% | 12.1% | 43.3% |
| $0.50-$1.00 | 241 | 5.0% | 99.2% | 99.2% | 6.8% | 36.6% |
| $1.00-$2.00 | 253 | 9.7% | 93.7% | 95.7% | 4.6% | 30.0% |
| $2.00-$5.00 | 395 | 19.5% | 51.6% | 63.5% | 2.7% | 20.3% |
| over $5.00 | 2,813 | 47.1% | 0.7% | 1.5% | 0.2% | 1.1% |

## Cheapest contract vs the cheapest one that can actually win

| Name | Cheapest contract (premium, modeled PoP) | Cheapest that passes the guardrail (premium, modeled PoP) |
|---|---|---|
| AAPL | AAPL261028C00362500 - $0.01, 0.1% | AAPL261028C00345000 - $1.76, 24.2% |
| AMD | AMD261030C00750000 - $0.01, 0.0% | AMD261028P00522500 - $5.38, 22.6% |
| AMZN | AMZN261028C00270000 - $0.01, 0.1% | AMZN261028P00247500 - $2.05, 29.0% |
| AVGO | AVGO261030C00400000 - $0.01, 0.1% | AVGO261028C00335000 - $3.08, 22.9% |
| GOOGL | GOOGL261030P00220000 - $0.01, 0.1% | GOOGL261102C00330000 - $5.10, 22.0% |
| META | META261030C00810000 - $0.02, 0.0% | META261028C00640000 - $5.22, 23.6% |
| MSFT | MSFT261030C00650000 - $0.01, 0.0% | MSFT261102C00550000 - $7.47, 22.9% |
| NFLX | NFLX261030C00073000 - $0.01, 0.5% | NFLX261030C00064000 - $0.59, 25.8% |
| NVDA | NVDA261028C00235000 - $0.01, 0.1% | NVDA261028C00217500 - $1.93, 26.5% |
| QQQ | QQQ261027C00737000 - $0.01, 0.0% | QQQ261027P00710000 - $1.76, 19.7% |
| SPY | SPY261027C00778000 - $0.01, 0.1% | SPY261027P00764000 - $1.44, 23.6% |
| TSLA | TSLA261028C00455000 - $0.01, 0.0% | TSLA261028C00400000 - $3.08, 21.2% |

Reproduce: `.venv/bin/python scripts/impact_study.py samples/impact-study-2026-10-26` (reads chains_raw.json in that folder).
