"""Judge-question regression battery (packaging prep, Oct 22).

The Cluse pattern, applied to QuantPilot: a fixed battery of the
questions a Track 02 judge is most likely to ask, run against the
SAMPLE_MODE fixture artifacts (samples/morning_run.json replayed
through a real Journal, exactly like the runner builds them) via
the DETERMINISTIC path of src/agent/ask.py (no LLM client - the
extractive fallback is what must hold the line on its own).

Every case asserts the answer cites the fixture's real artifact
values (board score, card checks, journal hit rate) or honestly
refuses / reports unknown. If a future change makes the layer
invent, soften, or misattribute a number, this battery fails.

Fixture facts asserted below (from samples/morning_run.json):
- Board of 4: TSLA #1 at 49.12 (bullish), SPY #2 at -5.26,
  AMD #3 at -5.91, NVDA #4 at -40.74 (bearish); NFLX is an honest
  error row, absent from the board.
- TSLA card: TRADE call, conviction 7/10, contract
  TSLA261027C00252500 (strike 252.5, premium 2.81), entry 243.5624,
  stop 242.8335; one failed check (market_event_in_window).
- NVDA card: no-trade WATCH (verdict after an INSUFFICIENT_EVIDENCE
  loop-back over a null IV rank); judge's biggest risk names the
  unscored IV.
- Journal: hit rate 50.0% (1 hit, 1 loss), breaker not tripped.
- X-Ray: posture mixed, breadth 7 bullish / 0 neutral / 5 bearish,
  58.3% above the 200DMA, Technology leading.
- IV rank is null for every packet (no 52-week IV range).
"""
from __future__ import annotations

from src.agent.ask import answer_question
from tests.test_agent_briefing import load_artifacts


def _ask(tmp_path, question: str) -> dict:
    """Deterministic path only: no LLM client is ever passed."""
    return answer_question(question, load_artifacts(tmp_path))


# ----------------------------------------------------------------------
# the board tells the truth about ranks and scores
# ----------------------------------------------------------------------
def test_battery_why_is_tsla_ranked_first(tmp_path):
    result = _ask(tmp_path, "Why is TSLA ranked first?")
    assert result["mode"] == "fallback"
    assert result["refused"] is False and result["unknown"] is False
    assert "49.12" in result["answer"]
    assert "#1 of 4" in result["answer"]
    assert "options OI +0.57" in result["answer"]
    assert result["sources"] == ["board:TSLA"]


def test_battery_why_is_nvda_ranked_first_corrects_the_premise(tmp_path):
    result = _ask(tmp_path, "Why is NVDA ranked first?")
    assert result["refused"] is False and result["unknown"] is False
    assert "not ranked first" in result["answer"]
    assert "#4 of 4" in result["answer"]
    assert "-40.74" in result["answer"]
    assert "TSLA leads" in result["answer"]


def test_battery_board_overview(tmp_path):
    result = _ask(tmp_path, "Who is on the board?")
    assert result["unknown"] is False
    assert "ranks 4 names" in result["answer"]
    assert "TSLA #1 at 49.12" in result["answer"]
    assert "NVDA at -40.74" in result["answer"]


def test_battery_market_posture(tmp_path):
    result = _ask(tmp_path, "What is the market posture right now?")
    assert result["unknown"] is False
    assert "posture is mixed" in result["answer"]
    assert "7 bullish / 0 neutral / 5 bearish" in result["answer"]
    assert "58.3%" in result["answer"]
    assert "Technology" in result["answer"]
    assert result["sources"] == ["xray"]


# ----------------------------------------------------------------------
# cards: the working is cited, including what failed
# ----------------------------------------------------------------------
def test_battery_tsla_card_summary(tmp_path):
    result = _ask(tmp_path, "Show me the TSLA card")
    assert result["unknown"] is False
    assert "verdict TRADE" in result["answer"]
    assert "conviction 7/10" in result["answer"]
    assert "TSLA261027C00252500" in result["answer"]
    assert "strike 252.5" in result["answer"]
    assert "premium 2.81" in result["answer"]
    assert result["sources"] == ["card:TSLA"]


def test_battery_tsla_card_risk_names_failed_check(tmp_path):
    result = _ask(tmp_path, "What is the risk on the TSLA card?")
    assert result["unknown"] is False
    assert "242.8335" in result["answer"]  # the card's own stop level
    assert "Failed checks on the card" in result["answer"]
    assert "market_event_in_window" in result["answer"]
    assert "iv_rank_known" in result["answer"]  # unscored checks named too


def test_battery_nvda_card_fail_explains_the_watch(tmp_path):
    result = _ask(tmp_path, "What could make the NVDA card fail?")
    assert result["refused"] is False
    assert "no-trade" in result["answer"]
    assert "WATCH" in result["answer"]
    assert "unscored IV" in result["answer"]  # judge's biggest risk
    assert "card:NVDA" in result["sources"]
    assert "debate:NVDA" in result["sources"]


def test_battery_why_nvda_watch_cites_the_loop_back(tmp_path):
    result = _ask(tmp_path, "Why did the judge keep NVDA at WATCH?")
    assert result["unknown"] is False
    assert "INSUFFICIENT_EVIDENCE" in result["answer"]
    assert "IV rank" in result["answer"]
    assert "debate:NVDA" in result["sources"]


# ----------------------------------------------------------------------
# unknowns stay unknown - never estimated, never zero
# ----------------------------------------------------------------------
def test_battery_tsla_iv_rank_is_unknown(tmp_path):
    result = _ask(tmp_path, "What is TSLA's IV rank?")
    assert result["unknown"] is True
    assert "Unknown in the artifacts" in result["answer"]
    assert "no 52-week IV range" in result["answer"]


def test_battery_nvda_iv_rank_is_unknown(tmp_path):
    result = _ask(tmp_path, "What is NVDA's IV rank?")
    assert result["unknown"] is True
    assert "Unknown in the artifacts" in result["answer"]
    assert "IV rank unknown" in result["answer"]  # packet one-liner cited


def test_battery_watched_but_absent_symbol_is_unknown(tmp_path):
    result = _ask(tmp_path, "Why is AAPL ranked where it is?")
    assert result["unknown"] is True
    assert result["refused"] is False  # watched name, honest gap
    assert "no board row, card, packet or debate in this run" in result["answer"]


def test_battery_error_row_symbol_is_unknown(tmp_path):
    # NFLX is the fixture's honest error row: on the watchlist, in the
    # board's error list, but with no artifacts to answer from.
    result = _ask(tmp_path, "Why is NFLX missing from the board?")
    assert result["unknown"] is True
    assert result["refused"] is False
    assert "NFLX is on the watchlist" in result["answer"]


# ----------------------------------------------------------------------
# the journal answers for itself
# ----------------------------------------------------------------------
def test_battery_hit_rate(tmp_path):
    result = _ask(tmp_path, "What is our hit rate?")
    assert result["unknown"] is False
    assert "50.0%" in result["answer"]
    assert "1 hit and 1 loss" in result["answer"]
    assert result["sources"] == ["journal_stats"]


# ----------------------------------------------------------------------
# the scope gate: advice and foreign tickers refused, deterministically
# ----------------------------------------------------------------------
def test_battery_personal_advice_refused(tmp_path):
    result = _ask(tmp_path, "Should I buy TSLA with my savings?")
    assert result["refused"] is True
    assert result["mode"] == "fallback"  # gate is deterministic
    assert "out of scope" in result["answer"]


def test_battery_sell_now_advice_refused(tmp_path):
    result = _ask(tmp_path, "Should we sell now and move to cash?")
    assert result["refused"] is True
    assert "out of scope" in result["answer"]


def test_battery_foreign_ticker_refused(tmp_path):
    result = _ask(tmp_path, "What about COIN?")
    assert result["refused"] is True
    assert result["unknown"] is True
    assert "outside QuantPilot's watchlist" in result["answer"]
