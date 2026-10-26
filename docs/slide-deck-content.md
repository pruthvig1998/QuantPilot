# QuantPilot - Slide Deck Content Draft

Purpose: content for the submission slide deck (component 2 of 4).
12 slides, covering the 8 required points: problem/target users,
solution, agent workflow/architecture, technical stack, Zetaris +
Meterless usage, what was unique, product visuals, future enhancements.
All numbers are from the codebase and the frozen sample run
(samples/morning_run.json) - do not round them into claims the repo
cannot back. Speaker notes are written at roughly 20-30 seconds each;
the deck supports the demo video, it does not repeat it.

---

## Slide 1 - Title

**QuantPilot - the options research agent that has to show its work**

- Open Agent Hackathon 2026, Track 02: The Agent That Can Explain Why
- Solo build: Pruthvi Garlapati
- One line: "Not the cheapest contract - the cheapest contract that can actually win."

Speaker note: Open on the motto, because it is also the product rule -
only contracts with delta at or above 0.30 are ever ranked, and every
pick carries the math that says whether it can win.

## Slide 2 - The problem (required point 1)

**Retail options research is a black box that sells confidence**

- Buyers of weekly options mostly lose: premium decays daily, IV crushes
  after events, and most "picks" never show breakeven, probability, or risk.
- The evidence lives in fragmented places - options chains, order flow,
  chart structure, sector breadth, event calendars, insider filings - and
  no retail tool assembles it into one auditable argument.
- LLM chatbots make it worse: fluent recommendations with no citations,
  no unknowns, and no record of what they got wrong.

Speaker note: The gap is not data, it is accountability. Nobody shows
the working, states what is unknown, or scores themselves afterwards.
That is the hole QuantPilot is built to fill.

## Slide 3 - Target users (required point 1)

**Who this is for**

- Self-directed options traders running a daily pre-market routine on a
  small, liquid watchlist (the author's own routine: 12 US names).
- Research-first users who want a verdict they can interrogate - why
  this name, why this contract, what would change the answer.
- Anyone burned by pick-selling: the product's answer to a bad setup is
  a printed WATCH with the failed checks named, not a quieter sales pitch.

Speaker note: The first user is the author - QuantPilot automates his
own real morning playbook. That matters for Impact: it is a working
workflow, not a demo invented for the hackathon.

## Slide 4 - The solution (required point 2)

**An investigating agent, not a chatbot**

- Each morning it builds an evidence packet per name (board score,
  order blocks, guardrail checks, event risk, insider context).
- A bull and a bear argue the packet; a judge verdicts TRADE / WATCH /
  SKIP with conviction - and can send the debate back once when the
  evidence has a named gap.
- Output is a trade card with levels, a chosen contract, sizing at 1%
  risk, plain-English Greeks, and every check listed as passed, failed,
  or unknown - plus a journal that scores the agent's own calls.

Speaker note: Three verbs define the product: investigate, argue,
confess. If a value is missing, it is printed as unknown. If a check
fails, it is printed on the card. The agent's honesty is mechanical,
not prompt-deep.

## Slide 5 - Agent workflow (required point 3)

**From fragmented sources to an evidence-backed card**

- Market X-Ray (breadth + sector rotation) sets the posture.
- Liquidity Board ranks the watchlist: OI 0.30, options volume 0.25,
  momentum 0.25, relative volume 0.20.
- Packets assemble for the top names; missing data is null and named.
- Bull -> bear -> judge debate (Nemotron), every claim citing a packet
  value; INSUFFICIENT_EVIDENCE triggers one loop-back round.
- Cards apply the contract filters and the 1% sizing rule; the journal
  records everything, append-only, and scores outcomes later.

Speaker note: Walk the flow left to right and land on the loop-back -
it is the collaboration judges are asked to look for: the judge does
not just verdict, it can refuse the evidence and make the other agents
work again.

## Slide 6 - Architecture (required point 3)

**Pure functions, one brain, honest plumbing**

- Analysis layer: indicators, liquidity board, order blocks, X-Ray,
  probability guardrail, IV/event guard - all pure functions, JSON in
  and out, unit-tested against known references (Black-Scholes verified
  to textbook values: ATM 1y/20% IV call delta 0.6368).
- Agent core: packet assembler, debate loop, card builder, SQLite
  journal on the append-only ledger model.
- Output layer: briefing (text + Markdown), self-contained HTML
  dashboard, and the Ask-QuantPilot Q&A brain shared by every surface.
- 263 automated tests, including a 16-question judge regression battery
  that fails if any answer invents a number.

Speaker note: The architecture choice that matters: the same pure
brain answers the dashboard, the briefing, and a judge's typed
question, so every surface gives the same grounded answer.

## Slide 7 - Technical stack (required point 4)

**What it is built on**

- Python 3.12; requests / pandas / numpy; SQLite; pytest (263 tests on the Mac suite).
- Data: Yahoo Finance public APIs (chart + options) behind a provider
  interface - the harness and the direct route are interchangeable.
- Brain: NVIDIA Nemotron (nvidia/nemotron-3-ultra-550b-a55b) over an
  OpenAI-compatible endpoint; all calls flow through one provider layer.
- Delivery: static dashboard HTML (zero external assets), plain-text
  and Markdown briefings, a CLI morning runner with a deterministic
  SAMPLE_MODE replay for judges.

Speaker note: No framework magic to hide behind - the repo is small
enough for a judge to read, and SAMPLE_MODE lets them re-run the whole
pipeline with no keys and no network.

## Slide 8 - Sponsor tech: Zetaris (required point 5)

**Zetaris - one harness over fragmented market data**

- A local Zetaris platform holds Yahoo's chart API as 46 REST tables:
  daily bars (2y) for 12 watchlist names + 10 sector ETFs, weekly (5y)
  and 5-minute (5d) bars for the watchlist, flattened into SQL views.
- The agent queries a single SQL interface (ZetarisProvider); swapping
  to direct Yahoo is one config value with zero downstream changes.
- This is the Track 02 "fragmented sources" story made literal: one
  question, many sources, one harness.

Speaker note: Be honest about the boundary too: options chains still
come from the Yahoo provider directly - it is in the README limitations,
and naming it ourselves is worth more than a judge finding it.

## Slide 9 - Sponsor tech: Meterless + NVIDIA (required point 5)

**Meterless engines and runtime, Nemotron brain**

- Build rule: the official Meterless H-Mem engine, vendored unmodified
  (Apache-2.0), driven via a Node bridge - the agent's superseding
  long-term memory (remember / recall / count).
- Power rule: a Meterless Runtime provider connection implemented in
  the product to the published Runtime 1.4 contract (connect-link
  token parsing, provider headers, /v1/models probe), per the Meterless
  team's Oct 19 HackOS ruling.
- Brain: Nemotron ultra-550b - the planned super-120b endpoint has
  404'd on NVIDIA's side since Oct 20 (verified on multiple keys); the
  model is one env line and flips back if it returns.

Speaker note: The ruling matters: the Meterless team confirmed engines
satisfy Build, a Runtime provider connection satisfies Power, and
Nemotron need not route through Nightshift for the NVIDIA prize. We
followed the ruling exactly and documented it.

## Slide 10 - What was unique (required point 6)

**The agent that argues with itself - and confesses**

- The loop-back, from the frozen sample run: NVDA round 1 came back
  INSUFFICIENT_EVIDENCE - IV rank was null, so crush risk could not be
  scored. After the forced second round the judge held NVDA at WATCH
  (conviction 4/10) rather than invent a number.
- Cards downgrade themselves: TSLA's TRADE card still prints its failed
  check (FOMC inside the holding window) and 4 unknown checks of 15.
- The journal grades the agent: sample run closes at 5 entries, 2
  scored, hit rate 50.0% - published in its own briefing.

Speaker note: This is the slide to slow down on. Other agents answer;
QuantPilot shows a case where it refused its own trade because the
evidence had a hole, and then shows its own score. That is the Track 02
statement, demonstrated.

## Slide 11 - Product visuals (required point 7)

**What the product looks like (capture list)**

- The judges dashboard: board table with component scores, X-Ray
  posture, both cards with PASS / FAIL / UNKNOWN check pills, the NVDA
  debate with both rounds and the gap box visible.
- The morning briefing (Markdown): TSLA card block with the Greeks line
  "needs +2.8% by 2026-10-27 to break even; model probability of profit
  26%; bleeds $52.26/day in theta per contract".
- Ask-QuantPilot answering "Why is TSLA ranked first?" with the score
  49.12 and its four components cited.
- All visuals are generated from samples/example-run/ - reproducible
  by any judge via SAMPLE_MODE.

Speaker note: Every visual in this deck is a real output file from the
repo's sample run, not a mockup. The filenames and commands to
regenerate them are in the README's Samples section.

## Slide 12 - Future enhancements (required point 8)

**Where QuantPilot goes next**

- Wire the last live verifications in: the R16 expiry-selection fix and
  a non-empty H-Mem recall in a US-hours run (both unit-proven, the
  Oct 23 run is the live check).
- Grow the IV snapshot history: IV rank computes at 20 snapshot days
  and carries its honest sample-size label until 60.
- Live verification of the Meterless route on an endpoint-bearing
  Nightshift edition (M5 / Windows / DGX Spark) when one is available.
- Cursor: optional per Official Rules 8.1 and not used - development
  used Claude Code, and no Cursor credits were provided for this event.
- Options chains through the Zetaris harness, closing the last direct
  Yahoo dependency.

Note (Oct 23): the earnings calendar, IV snapshot accumulation, board
history and the deterministic risk-review pass were listed here as
future work in the first draft - all four shipped in the Oct 22 audit
repairs (see docs/claude-audit-2026-10-22.md, Part C). They are
present features now, not roadmap.

Speaker note: Close on the theme: every future item makes an unknown
smaller or an answer more checkable. The roadmap is the product thesis,
continued. Final line: QuantPilot - the agent that has to show its work.
