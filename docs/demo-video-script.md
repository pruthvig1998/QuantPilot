# QuantPilot - Demo Video Script

Target runtime: 3:20 (official window 1:00-4:00; over 4:00 FAILS the
requirement; organizers recommend 2:30-3:30). Segment timings follow
the official Demo Video Guide plan. Narration is written at roughly
150 words per minute; word counts are noted per segment so a re-take
can be trimmed by line, not by feel.

Format: MP4, 1080p, 16:9, narration audio required. File name:
**OAH2026-QuantPilot-Track02-Demo.mp4**. The published link must open
without permission and stay live until judging ends (judging opens
Oct 28; results Nov 6, 2026).

The video must show, per the guide: at least two agents with clear
roles, a real collaboration/feedback loop, a live or recorded real
run, sponsor technology doing real work, and the final output.
Primary footage is the recorded REAL run from the Mac during US
market hours (see shot list). The SAMPLE_MODE replay is the fallback
for any segment that fails on recording day - it is deterministic and
shows the same loop-back.

---

## Segment 1 - Problem (0:00-0:20, guide range 15-25s, ~50 words)

On screen: a blurred montage of generic "options pick" posts, then a
raw options chain with the theta column highlighted. Text overlay,
the official Track 02 statement: "Build agents that investigate
complex questions across multiple data sources, connect findings,
and produce evidence-backed answers or recommendations."

Narration:
"Every morning, retail options traders are sold confident picks with
no evidence behind them. No breakeven, no probability, no record of
what the picker got wrong yesterday. The data to check a pick exists -
it is just scattered across chains, charts, calendars, and filings."

## Segment 2 - Solution (0:20-0:45, guide range 20-30s, ~62 words)

On screen: terminal running scripts/run_morning.py, then the judges
dashboard opening on the finished run. Motto card: "Not the cheapest
contract - the cheapest contract that can actually win."

Narration:
"QuantPilot is a pre-market research agent that investigates before
it recommends. It reads market breadth, ranks a twelve-name watchlist
by options flow, builds an evidence packet for each top name, and
argues every pick before printing it - with the breakeven, the
probability of profit, and the daily theta cost on the card. If the
evidence has a hole, it says so."

## Segment 3 - Agents and collaboration (0:45-1:25, guide range 30-45s, ~100 words)

On screen: the dashboard's debate panel for the recorded run. Bull
case, bear case, judge verdict - then scroll to the featured debate
(the NVDA loop-back from the sample dashboard if the live run did not
produce one): round 1 verdict INSUFFICIENT_EVIDENCE, the gap box
("events.iv.rank_pct is null"), round 2 arguments, final WATCH.

Narration:
"Three agents, three jobs. The bull argues the packet. The bear
argues against it. The judge verdicts: trade, watch, or skip - and
every claim has to cite a packet value. Watch what the judge does
here. Round one comes back 'insufficient evidence': the packet has
no IV rank, so the crash-risk check cannot be scored. The judge
names the gap and sends both sides back. The gap survives round two,
so the verdict is a watch - not a trade built on a number nobody
had. That refusal is the product."

## Segment 4 - Live run (1:25-2:20, guide range 45-60s, ~135 words)

Numbers note: the narration below quotes the SAMPLE run's values
(49.12, 243.56, 50.0%). If the segment uses the live Mac take,
re-record those lines with the live run's actual top name, score,
card levels, check counts, and hit rate before locking the audio -
the script's rule is that narration never describes a number that
is not the number on screen.

On screen: the recorded Mac run, lightly time-lapsed through the
3-15s Zetaris queries, real time on the card rendering. Show, in
order: the run command; board rows landing (TSLA at the top of the
sample board, score 49.12, components visible); the TSLA trade card
(entry 243.56, stop 242.83, target 255.10, 1 contract at a $100 risk
budget); the checks list with 1 failed and 4 unknown of 15; the
briefing file; the journal line "hit rate 50.0%".

Narration:
"This is a real run. The board ranks TSLA first at 49.12 - and the
score is not a black box: open-interest bias, options volume,
momentum, relative volume, each shown with its weight. The packet
adds order blocks, guardrail checks, and event risk, including an
FOMC decision five days out. The card it produces is sized at one
percent risk, and it prints its own weaknesses: one failed check,
four unknown, out of fifteen. The Greeks are plain English - it
needs plus 2.8 percent by expiry to break even, and it bleeds
fifty-two dollars a day in theta. Then the journal writes it all
down, append-only, and grades the agent's earlier calls: fifty
percent, in print, in its own briefing."

## Segment 5 - Sponsor technology (2:20-2:45, guide range 20-30s, ~62 words)

On screen: three quick beats. (1) Zetaris web UI: the
YAHOO_FINANCE_REST container and one SQL query returning live rows.
(2) The Meterless H-Mem bridge: a remember and a recall in the
terminal; Nightshift window with the NVIDIA provider configured.
(3) The provider layer probe and the Nemotron model id in the run
log (no keys anywhere in frame).

Narration:
"Under the hood: Zetaris is the data harness - forty-six REST tables
behind one SQL interface, so the agent never hand-rolls per-source
ETL. Meterless supplies the H-Mem memory engine and the Runtime
provider connection, implemented to the published contract. And the
brain is NVIDIA Nemotron - and every citation it writes is checked
against the packet in code before a card can say TRADE."

## Segment 6 - Output and impact (2:45-3:20, guide range 30-40s, ~87 words)

On screen: the final dashboard in full; then Ask-QuantPilot being
asked two questions against the run: "Why is TSLA ranked first?"
(answered with 49.12 and the four components) and "What is NVDA's
IV rank?" (answered: unknown in the artifacts). Closing card: the
motto, the repo name, "Educational only - not financial advice."

Narration:
"And because the explanation layer is grounded in the same
artifacts, a judge can interrogate the run directly. Ask why TSLA
leads, and it cites the score and its components. Ask for a number
the packet never had, and it answers 'unknown' - never a guess.
QuantPilot: the options research agent that has to show its work.
It investigates, it argues, and it confesses. Then it grades
itself."

---

## Shot list - capture on the Mac during US hours (9:30 AM-4:00 PM ET)

Record at 1080p, 16:9, with the wall clock or a timestamp visible in
at least the run footage (proves the run is real and in-hours):

1. Zetaris web UI: YAHOO_FINANCE_REST container expanded; run one
   SQL query against a watchlist bars table and show rows returning.
2. Terminal, full live run: `python scripts/run_morning.py` start to
   finish (default top 3). Keep the whole take; time-lapse in edit.
3. The runs/<date>/ folder appearing; briefing.txt opening; the
   journal stats line visible.
4. The dashboard rendered from the LIVE run's artifacts: full slow
   scroll - X-Ray, board, cards with check pills, the featured
   debate (both rounds if a loop-back occurred), journal stats.
5. Meterless H-Mem bridge: one remember + one recall with output.
6. Nightshift window showing the NVIDIA provider configured - ONLY
   if no token or key value is visible in that view; otherwise show
   the provider probe output in the terminal instead.
7. Ask-QuantPilot: the two scripted questions against the live
   artifacts (fallback: against the sample artifacts).
8. Fallback takes (record regardless): a SAMPLE_MODE run and the
   sample dashboard's NVDA loop-back panel, in case the live debate
   does not loop on recording day.

## Production reminders

- NO API KEYS OR SECRETS ON SCREEN, ever: keep .env closed, check
  terminal scrollback and Nightshift screens before recording, and
  re-check every frame in edit. This is an explicit guide rule.
- Hard limits: over 4:00 fails; audio is required; MP4 preferred.
- The video must show at least two agents with clear roles, a real
  feedback loop, a real run, sponsor tech doing real work, and the
  final output - the segment plan above covers each at least once.
- Prices in the sample footage are fixture prices; the narration and
  captions must not present sample numbers as live market data. The
  live-run segment uses the real Mac run for exactly this reason.
- Keep the published video link live and permission-free until
  judging ends (results Nov 6, 2026).
