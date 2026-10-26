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

Footage rule (Oct 26 revision): live footage is runs/2026-10-23
(dashboard.html, briefing.txt, run_stdout.txt). Narration states only
numbers that are on screen in that footage. Sample footage appears
only where labeled SAMPLE on screen.

On screen: the Oct 23 dashboard debate panel for TSLA - bull case,
bear case, judge verdict - then the grounding table under the round
(Citations / Verified / Failed citations). Hold on the failed row:
"guardrails.candidates[4].evaluation.metrics.probability_of_profit =
0.3339 - mismatch (packet: 0.3031)". Then a 5-second cut to the SAMPLE
NVDA loop-back (gap box "events.iv.rank_pct is null"), with an
on-screen label "SAMPLE RUN - loop-back".

Narration:
"Three agents, three jobs. The bull argues the packet, the bear argues
against it, and the judge decides: trade, watch, or skip. Every claim
must cite a packet value - and the code checks every citation. In
Friday's live run, Nemotron wrote a hundred and fifteen citations;
a hundred and thirteen matched the packet, and the two that didn't
were caught and named, like this probability of profit. When evidence
is missing, the judge can send both sides back - shown here on our
sample run - and if the gap survives, the answer is watch, never a
guess."

## Segment 4 - Live run (1:25-2:20, guide range 45-60s, ~135 words)

On screen: the recorded Oct 23 run, time-lapsed: the run command; the
board landing (MSFT #1 at 20.50, all twelve rows with components); the
three cards (META SKIP, MSFT WATCH, TSLA WATCH) with their checks
lists; the TSLA judge's biggest risk line (FOMC in 5 days, IV rank
unknown, theta over $70/day on the 5-day options). Then a labeled
insert: "SAMPLE RUN - what a trade card looks like" showing the sample
TSLA trade card (levels, sizing, checks). Do NOT narrate sample numbers.

Narration:
"This is a real run, Friday morning at the open, recorded and sped
up. The board ranks twelve names; Microsoft leads at twenty point
five, and every score shows its four components. Three names go to
debate. All three judges stand aside - and they say why: the Fed
decides on the very day these options expire, the implied-volatility
rank is still unknown, and Microsoft reports earnings inside the
window. No trade beats a bad trade. When the evidence does line up,
the card looks like this one from our sample run: entry, stop and
target from order blocks, sized at one percent risk, every check
printed - passed, failed, or unknown."

## Segment 5 - Sponsor technology (2:20-2:45, guide range 20-30s, ~70 words)

On screen: (1) Zetaris web UI: YAHOO_FINANCE_REST container and one
SQL query returning rows; then run_stdout.txt line "data calls: 59
zetaris queries, 15804 rows". (2) The Oct 23 TSLA packet's memory
block: its Oct 22 WATCH recalled from H-Mem (and META's Oct 22 SKIP).
(3) run_stdout.txt line "model calls: 10 (nvidia/nvidia/nemotron-3-
ultra-550b-a55b x10)". No keys anywhere in frame.
(4) Nightshift beat (live since Oct 26): the Nightshift Command Center
with the Runtime online at 127.0.0.1:8088 (hide the API key field),
then runs/2026-10-26/run_stdout.txt line "model calls: 9
(meterless/nvidia/nemotron-3-ultra-550b-a55b x9)". Trim Segment 4 by
the 10 s this adds.

Narration:
"Under the hood: Zetaris is the data harness - forty-six REST tables
behind one SQL interface; this run made fifty-nine queries through it.
Meterless H-Mem is the agent's memory: on Friday, the packet for each
returning name carried its call from Thursday. And every model call
goes through the Meterless Nightshift runtime on this Mac, pinned to
NVIDIA Nemotron Ultra - nine of nine in Monday's run, each one logged
with the model that served it."

## Segment 6 - Output and impact (2:45-3:20, guide range 30-40s, ~87 words)

On screen: terminal, scripts/ask.py against runs/2026-10-23:
1. "Why is MSFT ranked first?" -> rank #1 of 12, score 20.50, the four
   components and their inputs.
2. "What is META's IV rank?" -> "Unknown in the artifacts".
3. "Should I buy TSLA calls with my savings?" -> refused, out of scope.
Closing card: the motto, the repo URL, "Educational only - not
financial advice."

Narration:
"And because the explanation layer reads the same artifacts, a judge
can question the run directly. Ask why Microsoft leads, and it cites
the score and all four components. Ask for a number the packet never
had, and it says unknown - never a guess. Ask for personal advice, and
it declines. QuantPilot: the options research agent that has to show
its work. It investigates, it argues, it checks its own citations -
and it is not afraid to say no trade."

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

## Final cut - Oct 26 (as rendered)

File: ~/Downloads/OAH2026-QuantPilot-Track02-Demo.mp4 - 2:54, 1920x1080, H.264 30 fps,
AAC 48 kHz stereo, 8 MB, -16.7 LUFS. Narration: macOS voice Samantha at 175 wpm
(synthetic, by Pruthvi's choice). Every visual is a real capture or real text from
the run artifacts; every shot carries a LIVE (with date) or SAMPLE caption. The
Nightshift Console capture has the API key and LAN IP covered by solid boxes.
This table supersedes the segment narration above where they differ.

| Start | On screen | Narration |
|---|---|---|
| 0:00 | title card | Every morning, retail options traders are sold confident picks with no evidence behind them. |
| 0:06 | title card | No breakeven, no probability, no record of what the picker got wrong yesterday. The data to check a pick exists. It is just scattered across options chains, price charts, sector data, and event calendars. |
| 0:20 | title card | Quant Pilot is an options research agent that investigates before it recommends. It ranks a twelve-name watchlist by options flow and price action, builds an evidence packet for each top name, and makes three agents argue over it. |
| 0:34 | LIVE RUN - Mon Oct 26, 2026 - US market hours - 12:15 ET - scripts/run_morning.py | One command runs the whole morning. Every number it prints comes from that packet, and the code checks that it does. |
| 0:40 | LIVE RUN - Mon Oct 26, 2026 - US market hours - TSLA debate - judge + grounding check | Three agents, three jobs. The bull argues for the trade, the bear argues against it, and the judge decides: trade, watch, or skip. Every claim must cite a value from the packet, and code verifies every citation. In Monday's run, all ninety-one checked out. |
| 0:58 | LIVE RUN - Fri Oct 23, 2026 - TSLA debate - misquote caught by the verifier | On Friday, two did not. Here the bear quoted a probability of profit of thirty-three percent, where the packet said thirty. The verifier caught it, and named it. |
| 1:08 | SAMPLE RUN (fixture data) - evidence-gap loop-back | When evidence is missing, the judge sends both sides back with the gap named, shown here on our sample run. If the gap survives, the answer is watch. Never a guess. |
| 1:19 | LIVE RUN - Mon Oct 26, 2026 - US market hours - Liquidity Board | This is a real run, recorded Monday during market hours. Tesla tops the board at forty-six point eight, and every score shows its four components. |
| 1:28 | LIVE RUN - Mon Oct 26, 2026 - US market hours - TSLA trade card | Three names go to debate, and all three judges stand aside. |
| 1:32 | LIVE RUN - Mon Oct 26, 2026 - US market hours - TSLA card checks | And they say exactly why. The Fed decides in two days, the implied volatility rank is still unknown, and every check is printed: passed, failed, or unknown. |
| 1:43 | SAMPLE RUN (fixture data) - what a trade card looks like | No trade beats a bad trade. When the evidence does line up, the card looks like this one, from our sample run: entry, stop and target from order blocks, sized at one percent risk. |
| 1:55 | LIVE RUN - Mon Oct 26, 2026 - US market hours - Zetaris SQL trace | Under the hood, Zetaris is the data harness: forty-six REST tables behind one SQL interface. Monday's run made fifty-nine queries through it. |
| 2:05 | LIVE RUN - Mon Oct 26, 2026 - US market hours - TSLA packet memory - Meterless H-Mem | Meterless H Mem is the agent's memory. Tesla's packet carried its last two calls, and Thursday's call had already been updated with how it played out. |
| 2:14 | Meterless Nightshift M1-M4 0.92.7 - Runtime online at 127.0.0.1:8088 - API key redacted | And every model call goes through the Meterless Nightshift runtime, running on this Mac. |
| 2:19 | LIVE RUN - Mon Oct 26, 2026 - US market hours - model_calls log | Pinned to NVIDIA Nemotron Ultra. Nine calls out of nine, each one logged with the model that served it. |
| 2:26 | LIVE RUN - Mon Oct 26, 2026 - US market hours - Ask QuantPilot (scripts/ask.py) | Because the explanation layer reads the same artifacts, anyone can question the run. Ask why Tesla leads, and it cites the score and all four components. Ask for a number the packet never had, and it says unknown. Ask for personal advice, and it declines. |
| 2:42 | title card | Quant Pilot. The options research agent that has to show its work. It investigates, it argues, it checks its own citations, and it is not afraid to say no trade. |
