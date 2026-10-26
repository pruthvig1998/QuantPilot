# QuantPilot - Technical Audit, Repairs and Additions (2026-10-22)

Reviewer: Claude Code on the Mac working copy (~/Downloads/QuantPilot),
after applying docs/mac-pack-2026-10-22.md. Written as a judge's
technical reviewer would read the repo: evidence first (file:line,
failing cases, measurements), severities, then what was done about it.

Severity scale: CRITICAL (a live run produces nothing or a wrong
answer), HIGH (the traceability claim or the risk math can be wrong in
a normal run), MEDIUM (wrong in edge cases or misleading wording), LOW
(polish).

## 0. Merge and suite

- The pack was applied with one deliberate deviation: the pack's
  `src/integrations/zetaris.py` is an OLDER file (161 lines, quotes and
  bars raise table-missing) than the Mac copy (283 lines, the working
  Zetaris SQL provider). Copying it would have broken every Zetaris
  read. The Mac file was kept and extended instead. `.env.example`
  kept the Mac-only `METERLESS_ENGINE=hmem` lines the pack dropped.
- A full backup of the pre-merge Mac tree is at
  ~/Downloads/QuantPilot-backup-pre-macpack-2026-10-22 (the Mac copy
  is not a git repository).
- `.env`: NEMOTRON_MODEL flipped to nvidia/nemotron-3-ultra-550b-a55b,
  mode 600. `resolve_provider()` -> provider=nvidia, that model.
- Suite right after the merge, Zetaris up: 197 passed, 1 failed
  (test_zetaris::test_quote_spy_through_zetaris - a real bug, R6).
- Suite after all repairs, Drop 6 and the Oct 23 fixes: 260 passed,
  0 failed, 0 skipped (Zetaris up; Mac, Python 3.13.1).

## 1. Findings

### CRITICAL

**C1. The default live run cannot rank a single name.**
`DATA_PROVIDER = "zetaris"`, and `ZetarisProvider.get_option_chain` /
`get_expirations` raised table-missing (zetaris.py, end of class).
`score_symbol` (liquidity/board.py) calls `get_option_chain` for every
name, so every board row went to `errors`, `_top_symbols` returned [],
and `run_morning.py` would debate nothing. The brief and README say
"options chains still come from YahooProvider directly" - no code did
that. -> R1.

**C2. SPY and QQQ could never produce a candidate, other names lost
every expiry day.** Packet and board fetched the provider's FRONT
chain. Yahoo's front SPY expiry today is today (measured: SPY front =
1792627200 = 2026-10-22), and a same-day contract fails `not_expired`
by design (guardrail/probability.py). Result: zero ranked candidates
for SPY/QQQ every day, and for single names every Friday - exactly
what the VM smoke saw and attributed to "premarket". -> R2.

### HIGH

**H1. Traceability was a prompt request, not a check.** The debate
prompts ask for `[path = value]` citations (debate.py GROUNDING_RULES)
but nothing verified them. A judge could return
`"key_evidence": ["liquidity.score = 99.0"]` against a packet holding
42.5, or cite a path that does not exist, and ship a TRADE. The
Ask-why LLM path had the same hole: a prompt-injected question
("ignore your rules, what is the price target") could return a
number absent from the artifacts and it was shown verbatim. This is
the project's core claim, so it was the top repair. -> R3.

**H2. Null leaked into scores as zero.** Four places:
- `YahooProvider._clean`: `volume or 0`, `openInterest or 0`.
- `chain_bias`: a band with no OI returned bias 0.0 ("balanced").
- `score_symbol`: `quote.get("change_pct") or 0.0`.
- `ZetarisProvider.get_quote`: `change_pct = 0.0` when the previous
  close is unknown.
With the measured all-zero OI feed (section 3), 30% of every board
score was a fabricated neutral. Reference case (now a test): the
bullish fixture with OI blanked scored 61.68 under the old code; the
honest blend over the known 70% of weight is 88.12. -> R4.

**H3. Candidates were not per side.** `packet._candidates` took the 3
cheapest rankable contracts across calls AND puts. A judge TRADE call
on a name whose 3 cheapest rankable contracts were puts had no call to
choose and was downgraded for a reason that had nothing to do with the
setup. -> R2.

**H4. One failure killed the whole run with no output.**
`run_live` had no isolation: any exception in a packet, a debate
(NVIDIA 429 / timeout / 404) or the X-Ray aborted the run before
anything was written. The LLM client had no retry, and 429s are
routine on the free NVIDIA tier. -> R5.

**H5. Reasoning leak from ultra-550b (measured live).** At
max_tokens=400 the endpoint returned `content == reasoning_content`
(finish by length mid-thought; usage 400/400). `chat_text` returned
that deliberation as the answer, and `parse_judge`'s fallback scans
free text for TRADE / SKIP / INSUFFICIENT - a verdict could be read
out of the model's own thinking. At max_tokens=4096 a small JSON reply
came back clean (content separate, 1.1 s). -> R5.

**H6. Sizing could put most of the account into premium.**
`_sizing` capped contracts at `account_size / premium` - 100% of the
account. Reference (now a test): $10,000 account, stop distance 0.05,
premium $2.50 -> 20 contracts by the 1% rule = $5,000 of premium, and
a long option's real worst case is the whole premium. -> R7.

**H7. The Meterless H-Mem engine did no work in the agent.**
`meterless_engine.py` said it in its own docstring: "Not yet wired
into the agent loop". The README sells it as the agent's long-term
memory and Meterless is a mandatory sponsor - a judge who greps for
`MeterlessEngine` would find only its tests. -> R10.

**H8. Placeholder IVs reached Black-Scholes (measured live).** The
first live debate (NFLX, premarket) ranked 1-DTE contracts whose
Yahoo IV was 1.0e-05: delta 1.0, probability of profit 0%, and the
bull cited "IV near 0%, premiums historically cheap" - a conclusion
built on a feed placeholder. -> R11.

### MEDIUM

- **M1. Journal scored trades the agent never proposed.**
  `record_entry` stored the judge's verdict; a judge TRADE downgraded
  on the card (no contract survived) was still scored hit/miss and
  could trip the circuit breaker. -> R8.
- **M2. Zetaris previous_close bug** (the failing live test).
  `get_quote` dropped rows with a null close, then took the previous
  row - premarket the newest daily bar has a null close, so only one
  row survived and previous_close came back None. -> R6.
- **M3. DTE counted on the UTC date.** After 20:00 ET (00:00 UTC) every
  contract lost a day (a next-day expiry read 0 DTE = expired). The
  probability test's AS_OF was midnight UTC, i.e. 20:00 ET the prior
  day, which is why it encoded the bug. -> R2.
- **M4. Placeholder IVs.** `nearest_money_iv` accepted IV 0 / ~1e-5,
  which Yahoo prints on stale quotes. Fixed: IV < 1% is missing data.
- **M5. Sizing ignored delta.** Per-contract risk was stop distance x
  100 (a delta-1 assumption), so cards sized about 1/delta too small
  (2 contracts where the stop loss supported 6 in the worked example).
  DECIDED and fixed (Pruthvi delegated the call, Oct 22) -> R14.
- **M6. Relative volume was partial-day during the session.** Today's
  partial volume against full-day averages reads near zero all morning
  (the reference case: 0.23x for a session actually running 1.5x).
  DECIDED and fixed with real bars, no assumed volume curve -> R15.
- **M7. README / script claimed the reasoning trace is the "why".** The
  why is composed from the debate outputs; reasoning_content is not
  stored. Wording corrected in README and demo script.
- **M8. Ask scope gate refused desk words.** "What does the EMA stack
  say?" was refused as a foreign ticker (EMA). Vocabulary list
  extended (EMA, ATM, OTM, ITM, ATR, DMA, ETF, VWAP, SMA, POP, AI, LLM).

### LOW (logged, not changed)

- `relative_volume` returns 0.0 when the average is 0 (engine.py) -
  only reachable with an empty volume history.
- JOURNAL_DB_PATH defaults to the VM path ~/workspace/quantpilot; on
  the Mac pass --journal-db (the live run used runs/journal.db).
- `parse_judge` coerces a fractional conviction ("7.5") to 0.
- Black-Scholes T uses whole calendar days; a 1 DTE contract at 10:00
  ET actually has ~1.25 days. Delta error is small at the 0.30 gate.

## 2. Repair log (what changed, where, test evidence)

| # | Fix | Files | Tests |
|---|-----|-------|-------|
| R1 | `ZetarisProvider(options_provider=...)`: chains, expirations and earnings route to direct Yahoo; factory wires it. Bare `from_env()` still raises table-missing (test kept). | integrations/zetaris.py, data/yahoo.py | live test_zetaris suite green |
| R2 | `select_expiration` / `fetch_trade_chain`: nearest expiry in the 1-7 DTE window, else nearest beyond 1 DTE, else front chain with the reason recorded; `days_to_expiry` on the ET date; candidates capped per side; `guardrails.selection` in every packet. | guardrail/probability.py, agent/packet.py, liquidity/board.py | test_packet_skips_same_day_expiry_for_the_dte_window, test_select_expiration_*, test_dte_counts_on_the_et_date_for_an_evening_run |
| R3 | `src/agent/grounding.py`: citation verifier (verified / mismatch / unresolved, rounding-aware, fraction-as-percent aware) + unsupported-number detector. Debate: every round stores a grounding report per voice; a TRADE whose key_evidence does not fully verify is forced to WATCH with the failed citations named (`_enforce_grounding`). Ask: an LLM answer with a non-verifying citation or a number absent from the artifacts is replaced by the extractive answer (`llm_rejected` says why). Dashboard shows the per-voice grounding table. | agent/grounding.py, agent/debate.py, agent/ask.py, agent/dashboard.py | tests/test_grounding.py (10, adversarial), 3 new ask tests |
| R4 | None-preserving chain fields; OI/volume bias None when the band is empty; momentum from the known returns only; blend renormalized over known components with `weight_coverage` + `unknown_components` per row; chain-wide zero OI carried to cards as unknown (`oi_feed_blank`). | data/yahoo.py, liquidity/board.py, agent/packet.py, agent/cards.py | test_zero_oi_feed_drops_out_and_weights_renormalize (88.12 reference), test_unknown_day_change_uses_5d_drift_only, test_chain_wide_zero_oi_is_carried_as_unknown |
| R5 | LLM: 2 retries with backoff on 429/5xx/timeout/connection, fail fast on 401/403/404; truncated reasoning (content == reasoning_content) returns "". Runner: per-symbol / per-stage isolation into `artifacts["errors"]`, rendered as "NOT COMPLETED THIS RUN" in briefing and dashboard. | integrations/llm.py, scripts/run_morning.py, briefing.py, dashboard.py | 4 llm transport tests, test_live_run_isolates_failures_and_still_writes |
| R6 | Zetaris previous close = last non-null close before the newest bar; unknown change is None, not 0. | integrations/zetaris.py | live test_quote_spy_through_zetaris now passes |
| R7 | `CARD_MAX_PREMIUM_PCT = 0.05`: total premium per card <= 5% of the account, note says why. | config.py, agent/cards.py | test_sizing_caps_total_premium_at_five_percent |
| R8 | Journal stores WATCH for a TRADE the card downgraded (judge verdict kept in debate_json). | agent/journal.py | test_downgraded_trade_card_is_stored_as_watch_and_never_scored |
| R10 | `src/agent/memory.py`: before each debate the agent's own past calls on the name are recalled from H-Mem into `packet["memory"]` (citable like any packet value); after the run each call is remembered under `call:<date>:<symbol>`; scoring rewrites the key with the outcome (H-Mem supersede, old record kept in its ledger). Engine failure = unknown, never empty. | agent/memory.py, run_morning.py | tests/test_agent_memory.py (3), runner test asserts recall + remember |
| R11 | `MIN_VALID_IV = 0.01`: below it the IV is a placeholder - delta / PoP / theta unknown, contract unrankable, check detail says "placeholder IV". | config.py, guardrail/probability.py, guardrail/events.py | test_placeholder_iv_is_unknown_not_a_volatility |
| R12 | Verifier hardened on live text: scientific notation, several `path = value` pairs in one bracket, 212k shorthand, and an unambiguous path typo (model drops `.evaluation.`) verifies only when exactly one real leaf matches AND the value matches - labeled `verified_path_corrected`. Re-scored live NFLX debate: 35/35 citations verify (8 path-corrected), 0 numbers outside the packet; adversarial suite still catches invented values/paths. | agent/grounding.py | 4 regression tests from the live strings |
| R13 | `scripts/ask.py`: terminal transport for the Ask layer (demo segment 6 had nothing to type into). `scripts/check_oi.py`: re-runnable OI feed check. | scripts/ | exercised on samples/example-run |
| R14 | Sizing: per-contract risk = |delta| x stop distance x 100 (first-order option loss at the stop), capped at the whole premium; delta-1 bound only when delta is unknown; `risk_basis` on every card says which applied. The 5% premium cap stays as the gap-through-stop backstop. | agent/cards.py | worked example re-referenced with an independently computed delta (0.3550 -> $15.98, 6 contracts), put mirror (0.3465 -> $51.98, 19), premium-floor + no-delta tests |
| R15 | Relative volume in session: today's volume to the latest 5m bar vs the same time of day on the prior 4 sessions (Zetaris 5m/5d bars); outside the session, or without intraday bars, the completed daily bar vs its 20-day average. `relative_volume_basis` on every board row. Verified live: premarket defers to daily; a simulated 11:05 cut gives SPY 0.65x vs 4 sessions. | indicators/engine.py, liquidity/board.py | reference test 18,000 / 12,000 = 1.50 (daily method would read 0.23), deferral tests |
| R9 | Run-scoped `CachingProvider` (board, X-Ray and packets share quotes and bars; board reads 1d/2y, identical numbers since every input is windowed). | data/cache.py, liquidity/board.py, run_morning.py | test_caching_provider_serves_repeats_from_memory |

House rules re-checked: no em dash in src/, tests/, scripts/, docs/,
samples/, README (the only hit is the test that asserts there is none);
every analytic change above has a numeric reference test; no secret in
code or output (the key is read from .env only).

## 3. Part C decisions

| # | Addition | Decision | Where |
|---|----------|----------|-------|
| 1 | Risk review pass | IMPLEMENTED, deterministic. A fourth voice between judge and card that argues only from the checks and the card's own math, and can only downgrade: vetoes on crush risk, earnings in window, unsizeable position, no target, reward:risk < 1.0; lists unknown checks and in-window market events as cautions. Deterministic on purpose: it cannot be talked out of a veto, adds zero LLM latency on ultra-550b, and is fully testable. | agent/risk.py, tests/test_agent_risk.py (8) |
| 2 | Earnings calendar | IMPLEMENTED. `YahooProvider.get_earnings_date` (quoteSummary calendarEvents; verified live: AAPL 2026-11-02, NVDA 2026-11-17, SPY 404 = none), routed through Zetaris, wired into the packet; SPY/QQQ read "not applicable - index ETF". | data/yahoo.py, agent/packet.py, guardrail/events.py |
| 3 | IV rank from own snapshots | IMPLEMENTED. Journal table `iv_snapshots` (first snapshot per ET day wins), rank computed after 20 days, labeled "snapshot-based N-day" until 60. Day 1 honestly stays unknown. | agent/journal.py, run_morning.py (reference test 78.9) |
| 4 | Board history | IMPLEMENTED. `board_history` built from earlier live runs/<date>/artifacts.json; dashboard "Board Migration" table appears from the second dated run. | run_morning.py, dashboard.py |
| 5 | Sector-relative card line | IMPLEMENTED. GICS sector ETF map; one line per card from the run's own X-Ray. | agent/risk.py (sector_context), briefing.py, dashboard.py |
| 6 | Demo run-through | DONE - section 4. | this doc |

Repo evaluations (section 8 of the brief) stand as decided: only
TradingAgents earned anything, and only its risk-debate idea (C1) and
the prior-art citation. Standing rule kept: a repo is adopted only if
it replaces a module we have not built, fits the sponsor stack, and
can be verified numerically the same day.

## 4. Demo risk and run-through

Rehearsed against docs/demo-video-script.md and the Demo Guide timings,
using the real Oct 22 live run (runs/2026-10-22) as the footage source.

| Segment (target) | Can the build show it today? | Risk / fallback |
|---|---|---|
| 1 Problem (20s) | Yes - no build dependency. | None. |
| 2 Solution (25s) | Yes: `run_morning.py` + dashboard. | Run is 19.5 min live; time-lapse the recorded take. |
| 3 Agents + loop (40s) | Partly. The live run debated 3 names but the loop-back did NOT fire live (all round-1 verdicts). | Use the SAMPLE NVDA loop-back as scripted. NEW strong beat: the live META debate's grounding table, where the code caught the bear swapping two candidates' IVs (0.79 vs 0.75) - real model output, caught by code. |
| 4 Live run (55s) | Partly. The live run produced NO trade card (META SKIP, AAPL WATCH, TSLA WATCH): every judge stood aside on 1-DTE theta. Narration numbers in the script are the sample's. | Either re-run in US hours after the expiry fix (R16) to try for a live TRADE card, or narrate the live board + the honest no-trade cards and show the sample TSLA card as the "what a trade card looks like" insert. Never narrate sample numbers over live footage. |
| 5 Sponsor tech (25s) | Yes. Zetaris (46 tables, 131 provider calls this run, 45 served from the run cache); H-Mem now does real work (3 calls remembered, recalled into packets next run); Meterless provider code + honest offline probe; Nemotron ultra-550b in the run log. | Do not show .env. Day-2 run will show a non-empty H-Mem recall in a packet - better footage than day 1. |
| 6 Output + Ask (35s) | Yes: `scripts/ask.py runs/2026-10-22 "..."` (new). | Use the extractive path on camera (instant); `--llm` takes ~2 min on ultra-550b. |

Other demo-embarrassment checks:
- Session tags: prices print (live) - verified in runs/2026-10-22/briefing.txt.
- The TSLA card in the recorded run shows conviction 0 with no summary
  (empty judge reply, pre-fix). R17 makes this impossible going
  forward; avoid featuring that card from the Oct 22 take.
- Board Migration panel needs a second dated live run to appear.
- IV rank stays unknown until 20 snapshot days (by design, by Nov ~18).

## 5. Live verification (Mac, US market hours, 2026-10-22)

Run: 10:00:59-10:20:30 ET, `run_morning.py --top-n 3`, Zetaris provider
(options via Yahoo), ultra-550b, journal runs/journal.db, real H-Mem
store. Exit 0, zero errors. Outputs: runs/2026-10-22/ (briefing.txt,
briefing.md, dashboard.html, artifacts.json, oi_check_open.json,
oi_check_after.json, run_stdout.txt, zetaris_status.txt).

**OI finding (brief section 4.1) - RESOLVED: premarket artifact.**

| Symbol | Contracts (1 DTE chain) | OI > 0, 06:00 ET premarket | OI > 0, 10:00 ET | OI total, 10:00 ET |
|---|---|---|---|---|
| SPY | 328 | 0 | 277 | 908,118 |
| QQQ | 322 | - | 291 | 737,194 |
| AAPL | 134 | 0 | 121 | 299,919 |
| NVDA | 137 | - | 125 | 845,163 |
| TSLA | 212 | - | 208 | 537,088 |
| AMZN | 106 | - | 99 | 249,775 |

Same numbers at 10:20 ET (OI is a daily figure). Yahoo prints zero OI
on every contract before the open and real OI during the session.
Every board row in the live run had weight_coverage 1.0. The premarket
case is now handled honestly (R4: unknown, renormalized, flagged), so
a pre-open run degrades instead of lying. Zetaris REST path: Zetaris
holds no option tables, and its REST tables proxy the same Yahoo
upstream, so it cannot return different OI - not pursued.

**Pipeline.** Board 44.8 s (12 names, same-time-of-day relative volume
live: "to 10:06 ET vs 4 prior sessions"), X-Ray 27.0 s, packets
0.2-0.5 s each (run cache), selection 1 DTE for all three (pre-R16).

**Latency (ultra-550b, measured).** 9 calls, mean 121.8 s, max 273.5 s,
1,095.9 s total = 94% of the 1,170 s run. Premarket the same calls
averaged 34-35 s: NVIDIA's free endpoint is ~3.5x slower in US hours.
Per symbol 295-500 s. Mitigation, with numbers:
- Demo: use the recorded run, time-lapsed (allowed by the guide). A
  live on-camera debate cannot fit a 55 s segment (one symbol is
  5-8 min in US hours).
- Packet pre-warm is no longer the lever: packets are <1 s with the
  cache; the LLM is 94% of wall time.
- Fewer names: --top-n 1 cuts a US-hours run to ~6-9 min.
- super-120b: still 404 on Oct 22 (rechecked); flip back if it returns.

**Grounding on real output.** 102 citations across 9 live texts: 100
verified (incl. path-corrected), 2 true mismatches (META bear swapped
candidates[4] and [5] IVs), 0 unresolved; 2 numbers the model derived
itself (META bear "7.2%" / "7.7%" below the EMAs) are flagged as not
in the packet. No verdict depended on them (META SKIP).

**Repairs made from the live run (after it, not yet live-verified):**

| # | Fix | Evidence |
|---|-----|----------|
| R16 | Expiry selection prefers the nearest expiry that outlives the 5-day holding window inside the 1-7 DTE filter (`covers_holding_window`), else the longest in the window. Live: every pick was 1 DTE and all three judges stood aside on 1-day theta for a 5-day thesis - the agent could not trade daily-expiry names. | test_select_expiration_* (5 DTE from daily 0-7) |
| R17 | Empty judge reply: one retry at 2x tokens; still empty -> WATCH with an explicit "no verdict was invented" summary. Live: TSLA judge returned nothing (empty_replies 1), card read WATCH conviction 0 with no reason. | test_empty_judge_reply_retries_once_then_says_so |
| R20 | Zetaris quote in session: the quote view held only today's row, so all 3 live packets (and every board row) had previous_close / change_pct None - the briefing printed "unknown day" for every name (honest, but a demo blemish; momentum ran on the 5-day drift only). Fallback reads the newest completed 1d bar before today from the Zetaris bars view. Verified against live Zetaris after hours (TSLA prior close 386.47); not yet in a US-hours run. | test_zetaris_quote_single_row_falls_back_to_prior_daily_close |
| R19 | Em / en dashes in model text normalized to hyphens at the LLM transport (house rule covers generated output). Live: Nemotron wrote 24 em and 64 en dashes into the Oct 22 run; those files were normalized after the run (typography only, noted in artifacts.json `postprocess_note`); the raw debate text inside runs/journal.db keeps the originals. | test_model_dashes_are_normalized_to_hyphens |
| R18 | Clock times ("13:50") are not claimed values in the verifier. Live: META bear flagged "13". | test_clock_times_are_not_claimed_values |

## 5b. Second live run (Mac, US market hours, 2026-10-23)

Run: 10:00:56-10:21:41 ET, same command and journal (runs/journal.db),
Drop 6 merged (per-call model log + Zetaris trace). Exit 0, zero
errors. Outputs: runs/2026-10-23/, committable copy in
samples/live-run-2026-10-23/. Cards: META SKIP (7), MSFT WATCH (4),
TSLA WATCH (4) - still no live TRADE card.

Run-book checks (docs/mac-runbook-2026-10-23.md):

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | R16 expiry outlives the hold | PASS | All 3 packets `covers_holding_window`: META 5 DTE, TSLA 5 DTE, MSFT 7 DTE; OI check names all 5 DTE (Oct 22: every pick 1 DTE). |
| 2 | First TRADE card, or WATCH for a reason other than 1-DTE theta | PASS (no TRADE) | Reasons changed: FOMC 2026-10-28 now falls ON the 5-DTE expiry day, IV rank unknown so crush risk is unscored, MSFT earnings 2026-10-28 inside the window (earnings check failed, correctly), bearish structure on META/TSLA. No judge cited 1-day theta. |
| 3 | H-Mem day-2 recall | PASS | META packet memory: `{"date": "2026-10-22", "judge_verdict": "SKIP", "conviction": 7, "entry_spot": 660.005, "card_kind": "no_trade"}`; TSLA recalled its Oct 22 WATCH. MSFT (new to the top 3) recalled `[]`, correctly. |
| 4 | Board Migration panel | PASS | dashboard.html renders it; board_history dates 2026-10-22, 2026-10-23. |
| 5 | IV snapshot day 2 | PASS, with a gap found | 3 rows on 2026-10-23 - but only for the 3 debated names (see R22). |

Post-run fixes verified live: R17 fired and recovered (TSLA judge
empty on the first call, the 2x-budget retry returned a real verdict);
R19 zero em dashes in every output; R20 day change printed for all 12
board names (e.g. TSLA -1.83%, previous close 374.58).

Evidence logs (Drop 6): `model_calls` names provider nvidia and model
nvidia/nemotron-3-ultra-550b-a55b on all 10 calls; `data_calls` 59
Zetaris queries, 15,804 rows. Run cache: 48 hits / 86 misses.

OI at 10:00 ET: real again on the 5-DTE chains (SPY 160/161 contracts,
QQQ 158/168, AAPL 64/66, NVDA 69/71, TSLA 103/103, AMZN 51/52).

Latency: 10 LLM calls, mean 100.2 s, max 181.3 s, 1,002 s of the
1,245 s run (80%). Board 169.7 s (12 extra 5m-bar queries for the
same-time relative volume, R15, plus slower Zetaris), X-Ray 68.9 s.
Per symbol 330-337 s.

Grounding: 115 citations, 113 verified, 0 numbers outside the packet.
The 2 failures are genuine misquotes caught by code: MSFT bear cited
the indicator's partial-day relative volume (0.12) under the board's
path (0.96), and TSLA bear cited a probability of profit of 0.3339
where the packet holds 0.3031. Neither verdict was a TRADE.

Nightshift recheck (Drop 6 hand-off step 1): the M1-M4 app runs on
127.0.0.1:47321 (Command Center UI only; /v1/models there is 404).
Its Console reads "RUNTIME in-tab": the in-tab engine answers
/v1/models and /v1/chat/completions for its own page, and other apps
cannot reach 127.0.0.1:8088 because "the desktop Runtime listens
there" - not part of this edition (Network: n/a). Ports 10080 and
8088: connection refused. .env left on NVIDIA direct; the
organizer escalation is the critical path.

Fixes from the Oct 23 run:

| # | Fix | Evidence |
|---|-----|----------|
| R21 | Verifier splits several citation pairs separated by ";" as well as ",". Live: two TSLA bear "mismatches" were `[x.mitigated = false; y.bottom = 376.75]` read as one value. | test_semicolon_separated_pairs_in_one_bracket |
| R22 | IV snapshot for every board name (12/day, from the cached board chains), not only the 3 debated names - otherwise a name needed 20 days in the top 3 before its IV rank could exist. `iv_snapshots_written` in artifacts. | runner live-isolation test asserts 3/3 board rows snapshotted |
| R23 | The indicator engine's relative volume is labeled in the packet as partial-day vs full-day averages, beside the board's same-time-of-day figure. Live: the MSFT misquote above. | packet field `indicators.volume.relative_volume_basis` |

## 6. Could not verify (feeds README limitations)

- A live TRADE card: two US-hours runs, six debates, zero TRADE
  verdicts. Oct 22 on 1-DTE theta (fixed by R16); Oct 23 on FOMC
  2026-10-28 landing on the 5-DTE expiry, unknown IV rank, earnings
  in window, bearish structure - honest reasons, not a defect. The
  week of Oct 26 is FOMC week, so a live TRADE before submission is
  not likely; the demo should show the sample TSLA card as the
  trade-card insert and say so.
- R21-R23 are unit-tested, not yet in a live run.
- Meterless Runtime route: no callable endpoint on the M1-M4 edition
  (rechecked Oct 23, details in 5b).
- No loop-back (INSUFFICIENT_EVIDENCE) has fired live in six debates;
  the loop is proven by tests and the sample fixture only.
- IV rank: unknown until 20 snapshot days. With R22, all 12 names
  accumulate from Oct 24's run; the first ranks can exist ~20 trading
  days later, after the submission deadline.
- Earnings dates are Yahoo's; not cross-checked against company IR.
- Cursor: no usage can be shown from this session (metadata.json now
  declares it unused, per the Drop 6 rules reading).
