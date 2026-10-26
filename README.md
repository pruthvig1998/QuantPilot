# QuantPilot

**An autonomous pre-market options research agent for US markets that has to
show its work.** Built solo for the Open Agent Hackathon 2026 (GenAI.works),
Track 02 - "The Agent That Can Explain Why":

> "Build agents that investigate complex questions across multiple data
> sources, connect findings, and produce evidence-backed answers or
> recommendations."

QuantPilot investigates a 12-name liquid-options watchlist (SPY, QQQ, AAPL,
MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD, NFLX, AVGO) across fragmented
sources - options flow, price structure, sector breadth, event calendars,
SEC insider filings - and produces trade cards where every number is
traceable to the evidence packet it came from. Its motto, enforced in code:

**Not the cheapest contract - the cheapest contract that can actually win.**

## What it does

One morning run (`scripts/run_morning.py`) executes the full pipeline:

1. **Market X-Ray** reads breadth (bullish / neutral / bearish counts from the
   watchlist's own technical regime rule) and sector rotation (10 US sector
   ETFs ranked on a 5/21/63-day momentum blend plus relative strength vs SPY),
   and calls the posture: risk_on / risk_off at 60% breadth.
2. **Liquidity Board** scores every watchlist name from options open
   interest (weight 0.30), options volume (0.25), price momentum (0.25) and
   relative volume (0.20) - strikes within +/-15% of spot - and ranks
   bullish top, bearish bottom, choppy in the middle.
3. **Data packets** are assembled for the top names: quote, the full
   indicator snapshot (9/20/21 EMA stack, 200DMA, ATR supply/demand zones,
   daily + weekly RSI, relative volume, 20-day and 52-week breakout levels),
   the board row with its component breakdown, order-block zones and
   equal-high/low liquidity pools, guardrail verdicts on candidate
   contracts, the IV/event assessment, and insider-pattern context. Anything
   missing is null and *named* in the packet's data-quality list.
4. **A debate, not a summary.** A bull argues the packet, a bear argues
   against it, and a judge verdicts TRADE / WATCH / SKIP with a conviction
   score. The judge can also return INSUFFICIENT_EVIDENCE with a named gap -
   bull and bear then re-argue once with the gap in front of them, and the
   second verdict must land. Every claim in every argument must cite a
   packet value; a TRADE with no direction is downgraded to WATCH by code,
   not by politeness.
5. **Trade cards** turn a TRADE verdict into levels (entry at the
   order-block zone midpoint, stop beyond the zone, target at the nearest
   liquidity pool), a contract chosen by explicit filter checks (delta band
   0.35 +/- 0.10 with a hard ranking floor at 0.30, spread <= 20%, options
   volume >= 50, open interest >= 100, 1-7 DTE), sizing at 1% account risk,
   and the plain-English Greeks: breakeven move required, model probability
   of profit, theta burn per day. Every check on the card is listed as
   passed / failed / unknown. If no contract on the verdict's side passes
   every check, the card downgrades itself and names the failed checks.
6. **Probability and IV/event guardrails** gate everything: breakeven, PoP
   and theta come from Black-Scholes over the chain's own IV (verified
   against textbook values), and the IV/event guard red-flags only the real
   crush setup - IV rank above the 70th percentile with earnings or an
   FOMC / CPI / NFP release inside the holding window.
7. **A self-scoring journal** (SQLite, append-only) records every entry
   with its card, its full debate (both rounds) and its packet fingerprint;
   outcomes are appended later, never rewritten. Hit rate is computed over
   TRADE entries only, and a 2-loss circuit breaker prints its stand-down
   line in the briefing when it trips.
8. **Outputs**: a morning briefing (plain text + Markdown, session-tagged
   prices, one educational-only footer), a self-contained judges dashboard
   (HTML, no external assets), and an **Ask-QuantPilot** layer that answers
   questions about the run ("why is TSLA ranked first?", "what could make
   the NVDA card fail?", "what is our hit rate?") grounded only in the
   run's artifacts - with a deterministic scope gate that refuses
   personal-advice and off-watchlist questions before any model is called.

## A sample run, in numbers

`samples/morning_run.json` is a frozen run of these exact modules over a
synthetic provider, and `samples/example-run/` holds the outputs it
generates (briefing, dashboard, artifacts). Two cards tell the story:

- **TSLA - TRADE call, conviction 7/10.** Board score 49.12 (#1 of 4),
  contract TSLA261027C00252500 (strike 252.5, premium $2.81, 4 DTE), entry
  243.56, stop 242.83, target 255.10, sized 1 contract against a $100 risk
  budget (1% of $10,000). Greeks line: needs +2.8% by expiry to break even,
  model PoP 26%, theta bleed $52.26/day. Checks: 10 passed / 1 failed /
  4 unknown of 15 - the failed check (an FOMC decision inside the holding
  window) is printed on the card, not hidden.
- **NVDA - WATCH, no trade.** Round 1 of the debate came back
  INSUFFICIENT_EVIDENCE: the packet's IV rank was null, so the crush-risk
  check could not be scored. Bull and bear re-argued with that gap named;
  the gap persisted, so the judge held NVDA at WATCH (conviction 4/10)
  instead of forcing a trade on unscored IV.

Journal after the sample run: 5 entries, 2 scored, hit rate 50.0%.

## Architecture

```
                 fragmented sources
   Yahoo options chains    Yahoo bars     event calendars   SEC EDGAR
   (OI, volume, IV)       (1d/1wk/5m)    (FOMC/CPI/NFP)     Form 4 scan
          \__________________|________________|________________/
                             v
              Zetaris AI Data Harness (local)
              46 REST tables, one SQL interface
                             v
   +-------------------------------------------------------------+
   |  Analysis (pure functions, JSON in / JSON out)              |
   |  indicators - liquidity board - order blocks - X-Ray        |
   |  probability guardrail - IV/event guard                     |
   +------------------------------+------------------------------+
                                  v
                        data packet per symbol
                  (missing data is null AND named)
                                  v
   +-------------------------------------------------------------+
   |  Agent core (Nemotron via the provider layer)               |
   |  bull -> bear -> judge (TRADE / WATCH / SKIP)               |
   |  judge may return INSUFFICIENT_EVIDENCE: one loop-back      |
   +------------------------------+------------------------------+
                                  v
        trade cards (levels + contract + checks + sizing)
                                  v
   journal (SQLite, append-only) -> briefing -> dashboard -> ask layer
                                  ^
              Meterless H-Mem engine (agent memory) -+
              Meterless Runtime provider connection -+
```

| Layer | Code |
| --- | --- |
| Data providers | `src/data/provider.py`, `src/data/yahoo.py`, `src/integrations/zetaris.py` |
| Indicator engine | `src/indicators/engine.py` |
| Liquidity board | `src/liquidity/board.py` |
| Order blocks | `src/orderblocks/detector.py` |
| Market X-Ray | `src/xray/xray.py` |
| Guardrails | `src/guardrail/probability.py`, `src/guardrail/events.py` |
| Agent core | `src/agent/packet.py`, `debate.py`, `cards.py`, `journal.py` |
| Outputs | `src/agent/briefing.py`, `ask.py`, `dashboard.py`, `scripts/run_morning.py` |
| LLM providers | `src/integrations/llm.py` (NVIDIA direct + Meterless Runtime) |
| Agent memory | `src/integrations/meterless_engine.py` (H-Mem, Mac build) |

Design rules that hold across every layer: pure functions over provider
data; unknown is a first-class value (checks report passed / failed /
unknown, never a silent zero); the agent proposes and a human approves -
QuantPilot places no orders.

## Sponsor stack

- **Zetaris (data harness).** All market data reaches the agent through a
  local Zetaris platform: Yahoo's chart API is registered as 46 REST tables
  (1d/2y bars for the 12 watchlist names + 10 sector ETFs, 1wk/5y and
  5m/5d for the watchlist), flattened into SQL views. The agent queries one
  interface (`ZetarisProvider`) instead of hand-rolling per-source ETL;
  flipping one config value swaps in the direct Yahoo provider with zero
  downstream changes. Option chains and earnings dates are not Zetaris
  tables yet: the factory routes those two calls from `ZetarisProvider`
  to the direct Yahoo provider (see Limitations).
- **Meterless (engines + runtime).** Two integrations, following the
  Meterless team's official ruling for this hackathon (Sam Cummings,
  HackOS, Oct 19): the Build rule is satisfied by a **Meterless Engine** -
  the official H-Mem reference implementation, vendored unmodified
  (Apache-2.0) and driven through a Node bridge, giving the agent
  superseding long-term memory (remember / recall / count). The Power rule
  is satisfied by a **Meterless Runtime provider connection** implemented
  in the product per the published Runtime 1.4 provider contract
  (`src/integrations/llm.py`): Nightshift route with connect-link token
  parsing, provider headers and a /v1/models probe, beside the NVIDIA
  direct route behind one interface.
- **NVIDIA Nemotron (the brain).** All debate and explanation calls run on
  Nemotron (`nvidia/nemotron-3-ultra-550b-a55b`), a reasoning model that
  argues the bull, bear and judge voices; every packet citation it writes
  is then checked in code (`src/agent/grounding.py`), and a TRADE whose
  cited evidence does not verify is downgraded. Why ultra-550b: the originally planned
  `nemotron-3-super-120b-a12b` endpoint has returned 404 on NVIDIA's side
  since Oct 20, 2026 (verified on multiple keys); the model is an env
  setting, and the code flips back to the 120b with one line if it returns.
- **Cursor (development environment).** The repository was built and
  reviewed with Cursor in the loop alongside the test suite; the event
  provides the free version of Cursor (organizers confirmed no Cursor
  credits are issued for this hackathon).

**Prior art.** The bull / bear / judge shape is in the lineage of
TradingAgents (TauricResearch), the reference multi-agent trading
framework - independently rebuilt here for weekly options, with
packet-grounded citations, an evidence-gap loop-back, and the
Zetaris / Meterless / Nemotron sponsor stack. No TradingAgents code is
used; see the pre-existing components declaration below.

## Setup

Requirements: Python 3.12, and (for live runs) a local Zetaris install
and an NVIDIA API key. The sample run needs none of that.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env    # fill in keys for live runs; placeholders only in git
```

Live runs need in `.env`: `MODEL_API_KEY` (an NVIDIA key from
build.nvidia.com), and for the Zetaris provider a running local Zetaris
with the Yahoo REST tables registered (key via `ZETARIS_API_KEY` or
`~/.zetaris-api-key`). Without Zetaris, pass `--provider yahoo` to the
runner for direct Yahoo data.

### Quickstart - SAMPLE_MODE (no keys, no Zetaris, no network)

```bash
SAMPLE_MODE=true .venv/bin/python scripts/run_morning.py
```

This replays the recorded fixture bundle (`samples/morning_run.json`)
through the production pipeline - real journal writes, real briefing and
dashboard rendering - and writes `briefing.txt`, `briefing.md`,
`dashboard.html` and `artifacts.json` into `runs/<date>/`. Deterministic:
the same inputs produce byte-identical briefings.

## Usage

```bash
# Live morning run (top 3 board names debated; writes runs/<date>/)
.venv/bin/python scripts/run_morning.py [--top-n 3] [--provider zetaris|yahoo]
    [--output-dir runs/2026-10-23] [--journal-db PATH] [--account-size 10000]

# Ask the run a question (deterministic path shown; an LLM client
# composes the same grounded answer in natural language when configured)
.venv/bin/python -c "
from scripts.run_morning import load_fixture
from src.agent.ask import answer_question
print(answer_question('Why is TSLA ranked first?', load_fixture())['answer'])
"
```

## Samples

- `samples/morning_run.json` - the frozen input bundle (board, X-Ray,
  packets, debates, cards, journal seeds) produced by the real modules
  over synthetic provider data. Prices in it are fixture prices, labeled
  as sample data everywhere they render.
- `samples/example-run/` - the outputs generated from that bundle by the
  commands above: `briefing.md` / `briefing.txt`, `dashboard.html`,
  `artifacts.json`. (The journal database from the replay is a local
  artifact and is git-ignored.)

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

260 tests, all passing on the Mac with Zetaris up (6 of them are live
Zetaris tests that skip when the harness is down): the pipeline
(indicators, providers, board, order blocks, X-Ray, both guardrails,
packet, debate, cards, risk review, journal, LLM provider layer,
briefing, dashboard, ask layer, live and sample runner), an adversarial
grounding suite (`tests/test_grounding.py`: invented values, invented
paths, empty packets, prose-only evidence - none can ship a TRADE),
plus a 16-question judge regression battery
(`tests/test_judge_battery.py`) that runs judge-style questions against
the sample artifacts and fails if any answer invents, misattributes, or
papers over an unknown. Black-Scholes outputs are verified against
independently computed textbook values (ATM 1-year / 20% IV: call delta
0.6368, put delta -0.3632). Nine tests in `tests/test_yahoo.py` are live
tests against the real Yahoo Finance API and need network access.

## Limitations (honest list)

- **Yahoo open interest reads zero before the open.** Measured Oct 22:
  at 06:00 ET every contract on SPY (328) and AAPL (134) showed OI 0;
  at 10:00 ET the same chains showed real OI (SPY 277/328 contracts,
  908k total). QuantPilot treats a chain with no printed OI as missing
  data: the board's OI component reads unknown and the remaining
  weights are renormalized (each row carries `weight_coverage`), and a
  card's open-interest check reads unknown, which can never confirm a
  trade. Run during market hours for full-weight scores.
- **IV rank builds up from our own snapshots.** No free source publishes a
  52-week IV range, so every run stores each name's at-the-money IV in the
  journal and IV rank is computed against that accumulating history once
  20 days exist (labeled "snapshot-based" until 60). Until then the IV
  rank and crush-risk checks report unknown, and the card prints them.
  Earnings dates come from Yahoo's quoteSummary calendar (index ETFs read
  "not applicable"). The market-wide event calendar (FOMC / CPI / NFP) is
  a static list verified against the Federal Reserve and BLS schedules.
- **Yahoo chains carry no Greeks.** Delta and theta are computed with
  Black-Scholes from the chain's own IV; the risk-free rate is a labeled
  config assumption (0.043), not a quote.
- **The Meterless route cannot be live-verified on an M1 Mac.** The free
  M1-M4 Nightshift edition exposes no callable endpoint (verified
  exhaustively); the provider connection is implemented to the published
  contract and unit-tested with mocked HTTP, and its probe honestly
  reports "offline" on that edition. First live verification needs an
  endpoint-bearing edition (M5 / Windows / DGX Spark) or an
  organizer-hosted endpoint.
- **Latency.** Measured in US hours (Oct 22, top 3 names): 19.5 min end
  to end, 94% of it Nemotron ultra-550b (9 calls, mean 122 s, max 273 s;
  the same calls averaged 35 s premarket). Zetaris queries take 3-15 s
  each on an M1 under emulation; a run-scoped cache makes packet
  assembly sub-second. The demo uses a recorded real run, as the Demo
  Guide allows.
- **Provider nuance.** Through Zetaris, previous_close is the last
  completed daily bar's close rather than Yahoo's chartPreviousClose, so
  day-change percentages can differ slightly between providers.
- **Options chains bypass the harness for now.** Zetaris serves bars and
  quotes; expirations, chains and earnings dates come from the Yahoo
  provider directly (routed inside `ZetarisProvider`).
- **Research only.** QuantPilot produces research artifacts. It places
  no orders, and every output carries the educational-only footer.

## Pre-existing components declaration

- **Sponsor platforms**: Zetaris AI Data Harness (local install, hackathon
  participant setup), Meterless Nightshift + Runtime contract + H-Mem
  engine specification, NVIDIA Nemotron API, Cursor (free version).
- **Vendored code**: the official Meterless H-Mem reference implementation
  at `vendor/meterless-hmem`, unmodified, Apache-2.0 (commit 1742dec),
  with its license and attribution intact.
- **Data**: Yahoo Finance public APIs (quotes, bars, options chains);
  a one-time SEC EDGAR Form 4 insider-pattern scan (Oct 20, 2026) whose
  output JSON is optional packet context; Federal Reserve and BLS release
  schedules for the static event calendar.
- **The author's own work**: the trading playbook the indicator engine
  encodes (EMA stack, 200DMA filter, ATR zones, RSI, relative volume) and
  the desk logic patterns the agent core adapts (debate verdicts, checks
  framing, ledger-style journal, contract filter values) are Pruthvi
  Garlapati's own pre-hackathon work, declared as such.
- Everything else in this repository was written during the build window
  (Oct 22-27, 2026).

## Ground rules

- US markets only. No NSE/BSE data anywhere in this repo.
- The agent proposes; a human approves every order. No discretionary
  trading, no order placement code.
- Market times are stated in ET.
- Educational only - not financial advice.
