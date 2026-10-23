# QuantPilot - HackOS submission form text (drafted Oct 23)

Copy-paste source for the submission form. Everything below is verified
against the codebase and docs/claude-audit-2026-10-22.md. Lines marked
[TO COMPLETE] must be filled truthfully at submission time - do not
invent them.

## Project name

QuantPilot

## Primary track

Track 02 - The Agent That Can Explain Why

## Short description (one or two lines)

An autonomous pre-market options research agent for US markets that
investigates a 12-name liquid-options watchlist across fragmented data
sources and produces evidence-backed trade recommendations whose every
claim is verified in code against the underlying data packet.

## Long description

QuantPilot runs a full pre-market research desk every morning. A
liquidity board ranks the watchlist on open interest, options volume,
momentum and relative volume. A market X-Ray reads breadth and sector
rotation. For the top names, the agent assembles one evidence packet
per symbol (quote, indicator snapshot, liquidity row, order blocks and
liquidity pools, guardrail-checked option candidates, IV and event
assessment, earnings date, and the agent's own remembered past calls on
that name).

Three Nemotron-powered voices then debate the packet: a bull case, a
bear case, and a judge. Every voice must cite packet values in
brackets, and a citation verifier in code checks each citation against
the packet - a TRADE verdict whose key evidence does not fully verify
is forced to WATCH with the failed citations named. The judge may also
return INSUFFICIENT_EVIDENCE with the exact missing field named; the
bull and bear re-argue once with that gap in front of them, and the
second verdict cannot dodge the question again. A deterministic risk
review then argues only from the guardrail and event checks and can
veto a TRADE to WATCH; it cannot be talked out of a veto.

Surviving verdicts become structured trade cards: entry at the
order-block zone midpoint, stop beyond the zone, target at the nearest
liquidity pool, a contract that must pass explicit filter checks
(delta band, spread, volume, open interest, days to expiry), sized at
1 percent account risk with total premium capped at 5 percent. Every
check on the card is shown as passed, failed or unknown - unknown
values never confirm a trade. All calls are written to an append-only
SQLite journal and scored against live prices later, with a two-loss
circuit breaker. The morning output is a briefing, a judges dashboard,
and an Ask-QuantPilot layer that answers questions about the run from
the run's own artifacts - and refuses, deterministically and before
any model call, anything outside them.

## Sponsor technology explanation

### Zetaris (data harness)
Zetaris runs locally in Docker on the build machine and holds 46 REST
tables over Yahoo Finance market data (daily bars 2 years, weekly bars
5 years, 5-minute bars 5 days, for the 12 watchlist names plus 10
sector ETFs). QuantPilot's data layer implements one provider
interface; the default provider issues SQL through the Zetaris REST
API for quotes and bars. Options chains route to Yahoo directly
because Zetaris holds no options tables - the provider split is
explicit in code and in the README limitations.

### Meterless (engines + runtime)
Two integrations, matching the Official Rules (8.1/15.2/16/23) and
the Technical Execution Requirements. (1) The H-Mem memory engine:
the official Meterless H-MEM reference implementation, vendored
unmodified under Apache-2.0, runs through a Node bridge. It is wired
into the agent loop: before each debate, the agent's past calls on
that symbol are recalled into the evidence packet as citable values;
after outcomes are scored, the memory record is superseded with the
result. (2) Nightshift as the primary AI provider: the Meterless
Runtime (Runtime 1.4) is implemented in the application as an
OpenAI-compatible provider route (base-URL normalization,
connect-link parsing, the meterless-app and meterless-scope headers,
a /v1/models probe that reports online, unauthorized or offline
honestly). Per the Technical Execution Requirements, the NVIDIA key
lives in Nightshift's Providers tab; the application itself holds
only the Nightshift URL and the runtime token, and routes its model
calls through Nightshift when that route is configured
(LLM_PROVIDER=meterless, or auto when a Meterless URL or token is
present). Every model call is logged per run (provider, the model
that actually served, latency) in the run artifacts. The NVIDIA
direct route below is retained only as a development fallback.

### NVIDIA (the brain)
All reasoning runs on NVIDIA Nemotron:
nvidia/nemotron-3-ultra-550b-a55b (the originally targeted
nemotron-3-super-120b-a12b chat endpoint has returned 404 since
Oct 20, 2026; the model is an env setting and flips back in one line).
In the rules configuration the key is registered in Nightshift's
Providers tab and Nightshift serves the calls (see Meterless above);
NVIDIA's direct API is retained as a development fallback only. Bull,
bear and judge are separate Nemotron calls over the same evidence
packet, and the model that served each call is logged in the run
artifacts.

### Cursor (development environment)
Optional per Official Rules 8.1; not used. Development used Claude
Code. No Cursor credits were provided for this event.

## Pre-existing components declaration

- Sponsor platforms: Zetaris, Meterless (H-Mem reference implementation
  vendored unmodified, Apache-2.0, commit 1742dec, LICENSE and
  SOURCE.txt in vendor/meterless-hmem), NVIDIA Nemotron API.
- Market data: Yahoo Finance (public endpoints).
- The trading indicator playbook (EMA stack, 200DMA, ATR zones, RSI,
  relative volume) is the author's own, developed before the hackathon
  in his separate paper-trading project; it was re-implemented inside
  QuantPilot during the event.
- Architecture prior art: the bull/bear/judge debate shape follows the
  lineage of TauricResearch/TradingAgents (no code used).
- Everything else - data providers, liquidity board, order blocks,
  X-Ray, guardrails, agent loop, citation verifier, risk review,
  journal, briefing, dashboard, Ask layer - was built during the
  event (Oct 22-27, 2026).

## Links (fill at submission)

- Public GitHub repo: https://github.com/pruthvig1998/QuantPilot (created Oct 23; snapshot commit 0875be0f - re-push after the Oct 23 live-run fixes, then update this note)
- Demo video: [TO COMPLETE - file name OAH2026-QuantPilot-Track02-Demo.mp4]
- Slide deck: [TO COMPLETE]
