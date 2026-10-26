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
