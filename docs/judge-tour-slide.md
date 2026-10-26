# Slide: How to evaluate QuantPilot in 3 minutes (for the deck)

Suggested position: right after the title slide, or as the last slide.
Paste as one slide; keep the link large.

---

**Title:** Evaluate QuantPilot in 3 minutes - nothing to install

**Link (large):** pruthvig1998.github.io/QuantPilot/explorer

**Body - five clicks, each a "Show me" button on the page:**

1. **What happened in a live run** - Mon Oct 26, US hours: 12 names ranked,
   289 option contracts screened (184 rejected), 91/91 citations verified.
2. **The verifier catches a misquote** - Oct 23: the bear cited a TSLA
   probability of profit of 0.3339; the packet said 0.3031. Flagged in code.
3. **Every check, including the failures** - why all three judges stood
   aside: the Fed decision 2 days out; UNKNOWN where data does not exist.
4. **Ask it why** - plain-English answers from the run's own evidence;
   personal advice refused.
5. **Sponsor tech, proven by the logs** - 9/9 calls via Meterless
   Nightshift on NVIDIA Nemotron Ultra; 59 Zetaris SQL queries.

**Footer:** Prefer code? `SAMPLE_MODE=true python scripts/run_morning.py`
runs offline in under 30 seconds (README, "Try it in 60 seconds").

**Speaker note:** Every number on the page comes from a committed run in
the repo; each step link (`.../explorer/#tour=1` to `#tour=5`) opens that
step directly. Screenshots of the five steps: docs/img/tour-1..5.jpg.

## Two more slides (impact + red team)

**Slide: Why it matters - live data, Oct 26 (US market hours)**
- 5,349 tradeable weekly contracts (12 names, 1-7 days out) run through QuantPilot's guardrail.
- 1,888 cost $1 or less: median modeled chance of profit 0.4%; 99.8% under 20%.
- They need a median 11.1% move to break even and lose ~42.8% of their value per day.
- Every name: the cheapest contract ~0% vs the cheapest that passes the guardrail ~20-29%.
- Link: pruthvig1998.github.io/QuantPilot/explorer/#sec=impact

**Slide: We tried to make it lie - 8 attacks, 8 caught**
- Invented number, invented field, prose-only evidence, empty packet, directionless TRADE: all downgraded to WATCH, reason named.
- Prompt injection into Ask: model's "512.40" rejected; grounded answer shown.
- Model cut off mid-thought: treated as no reply. Personal advice: refused.
- Run against the real code on every build; permanent tests.
- Link: pruthvig1998.github.io/QuantPilot/explorer/#sec=redteam
