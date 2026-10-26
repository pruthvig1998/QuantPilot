"""Grounding verifier: citations are checked against the packet, and
the debate cannot ship a TRADE whose evidence does not verify.

Adversarial on purpose: invented values, invented paths, an empty
packet, percent-vs-fraction rewrites, and prose numbers that appear
nowhere in the evidence. The LLM is a scripted fake throughout."""
from __future__ import annotations

import json

from src.agent.debate import run_debate
from src.agent.grounding import (
    grounding_report,
    unsupported_numbers,
    verify_citations,
    verify_key_evidence,
)

PACKET = {
    "symbol": "TST",
    "spot": 773.09,
    "liquidity": {"score": 42.5, "direction": "bullish"},
    "indicators": {"regime": "uptrend",
                   "long_filter": {"price_above_200dma": True}},
    "guardrails": {"candidates": [
        {"evaluation": {"metrics": {"delta": 0.3632,
                                    "probability_of_profit": 0.6368}}}
    ]},
    "events": {"iv": {"rank_pct": None}, "red_flag": False},
}


def judge(verdict="TRADE", direction="call", evidence=("liquidity.score = 42.5",)):
    return json.dumps({
        "verdict": verdict, "conviction": 7, "direction": direction,
        "gap": None, "key_evidence": list(evidence),
        "biggest_risk": "IV crush.", "summary": "One-sided.",
    })


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat_text(self, prompt, model=None, max_tokens=4096):
        return self.responses.pop(0)


# ----------------------------------------------------------------------
# citation checks
# ----------------------------------------------------------------------
def test_citation_statuses():
    text = (
        "Score is strong [liquidity.score = 42.5], trend is up "
        "[indicators.regime = uptrend], spot [spot = 780.00], "
        "and the analyst rating [analyst.rating = buy]."
    )
    status = {c["path"]: c["status"] for c in verify_citations(text, PACKET)}
    assert status == {
        "liquidity.score": "verified",
        "indicators.regime": "verified",
        "spot": "mismatch",          # 780.00 vs 773.09
        "analyst.rating": "unresolved",  # no such path in the packet
    }


def test_rounding_bool_null_and_percent_forms():
    text = (
        "[spot = 773.1] [indicators.long_filter.price_above_200dma = true] "
        "[events.iv.rank_pct = null] "
        "[guardrails.candidates[0].evaluation.metrics.delta = 0.36] "
        "[guardrails.candidates.0.evaluation.metrics.probability_of_profit = 63.7%]"
    )
    assert [c["status"] for c in verify_citations(text, PACKET)] == ["verified"] * 5
    # Precision is honored: 773.2 is not 773.09 at one decimal.
    assert verify_citations("[spot = 773.2]", PACKET)[0]["status"] == "mismatch"


def test_unsupported_numbers_flag_invented_prices():
    text = "Target 812.50 by Friday; spot 773.09; conviction 7 of 10."
    assert unsupported_numbers(text, PACKET) == ["812.50"]


def test_key_evidence_accepts_bare_and_flags_uncited():
    cites = verify_key_evidence(
        ["liquidity.score = 42.5", "[indicators.regime = uptrend]",
         "momentum looks great"],
        PACKET,
    )
    assert [c["status"] for c in cites] == ["verified", "verified", "uncited"]


def test_grounding_report_clean_flag():
    assert grounding_report("[liquidity.score = 42.5]", PACKET)["clean"] is True
    dirty = grounding_report("[liquidity.score = 42.5] and 912.40 upside", PACKET)
    assert dirty["clean"] is False
    assert dirty["unsupported_numbers"] == ["912.40"]


# ----------------------------------------------------------------------
# the debate cannot ship ungrounded TRADEs
# ----------------------------------------------------------------------
def test_trade_with_invented_value_is_downgraded():
    llm = FakeLLM(["bull", "bear", judge(evidence=["liquidity.score = 99.0"])])
    result = run_debate(PACKET, llm)
    assert result["verdict"] == "WATCH"
    assert "mismatch" in result["judge"]["loop_note"]
    assert "packet: 42.5" in result["judge"]["loop_note"]
    assert "Code override" in result["why"]


def test_trade_with_invented_path_is_downgraded():
    llm = FakeLLM(["bull", "bear",
                   judge(evidence=["analyst.price_target = 900"])])
    result = run_debate(PACKET, llm)
    assert result["verdict"] == "WATCH"
    assert "unresolved" in result["judge"]["loop_note"]


def test_trade_with_prose_only_evidence_is_downgraded():
    llm = FakeLLM(["bull", "bear", judge(evidence=["strong setup, buy it"])])
    assert run_debate(PACKET, llm)["verdict"] == "WATCH"


def test_empty_packet_cannot_produce_a_trade():
    llm = FakeLLM(["bull", "bear", judge(evidence=["liquidity.score = 42.5"])])
    result = run_debate({"symbol": "TST"}, llm)
    assert result["verdict"] == "WATCH"


def test_grounded_trade_survives_and_reports_totals():
    bull = "Uptrend [indicators.regime = uptrend], score [liquidity.score = 42.5]."
    bear = "Spot [spot = 780] is stretched; downside to 700.25."
    llm = FakeLLM([bull, bear, judge()])
    result = run_debate(PACKET, llm)
    assert result["verdict"] == "TRADE"
    g = result["grounding"]
    # bull 2 verified; bear 1 mismatch + 1 free number; judge 1 verified
    assert g["verified"] == 3
    assert g["mismatched"] == 1
    assert g["unsupported_numbers"] == 1
    bear_rep = result["rounds"][0]["grounding"]["bear"]
    assert bear_rep["mismatched"][0]["actual"] == 773.09
    assert bear_rep["unsupported_numbers"] == ["700.25"]


# ----------------------------------------------------------------------
# regressions from the first live ultra-550b debate (NFLX, Oct 22)
# ----------------------------------------------------------------------
LIVE = {
    "liquidity": {"inputs": {"call_volume": 212003.0, "put_volume": 167850.0}},
    "guardrails": {"candidates": [
        {"raw": {"impliedVolatility": 1.0000000000000003e-05},
         "evaluation": {"metrics": {"breakeven_move_pct": 1.23}}},
        {"evaluation": {"metrics": {"breakeven_move_pct": 0.62}}},
    ]},
}


def test_scientific_notation_citation_verifies():
    text = "[guardrails.candidates[0].raw.impliedVolatility = 1.0000000000000003e-05]"
    assert verify_citations(text, LIVE)[0]["status"] == "verified"


def test_several_pairs_in_one_bracket_are_each_checked():
    text = ("[guardrails.candidates[0].evaluation.metrics.breakeven_move_pct = 1.23, "
            "guardrails.candidates[1].evaluation.metrics.breakeven_move_pct = 0.62, "
            "guardrails.candidates[0].metrics.breakeven_move_pct = 1.23]")
    assert [c["status"] for c in verify_citations(text, LIVE)] == [
        "verified", "verified",
        # the model dropped ".evaluation": one unambiguous real path, value matches
        "verified_path_corrected"]


def test_path_correction_never_guesses_between_candidates_or_values():
    ev = {"a": {"x": {"score": 1.0}, "y": {"score": 2.0}}, "b": {"z": {"delta": 0.4}}}
    # two real leaves end in a...score: ambiguous, so unresolved
    assert verify_citations("[a.score = 1.0]", ev)[0]["status"] == "unresolved"
    # unique path but wrong value: still a mismatch
    assert verify_citations("[b.delta = 0.9]", ev)[0]["status"] == "mismatch"
    assert verify_citations("[b.delta = 0.4]", ev)[0]["resolved_path"] == "b.z.delta"


def test_thousands_shorthand_is_not_an_invented_number():
    text = "Call volume (212k) exceeds put volume (168k)."
    assert unsupported_numbers(text, LIVE) == []
    assert unsupported_numbers("Call volume (250k)", LIVE) == ["250k"]


def test_clock_times_are_not_claimed_values():
    """Live META bear case, Oct 22: "formed at 13:50 today" flagged 13."""
    assert unsupported_numbers("The block formed at 13:50 today.", PACKET) == []
    # A derived percentage the model computed itself still shows.
    assert unsupported_numbers("Price sits 7.2% below the 9-day EMA.", PACKET) == ["7.2%"]


def test_empty_judge_reply_retries_once_then_says_so():
    """Live TSLA judge, Oct 22: ultra-550b returned no answer."""
    class Budgeted:
        def __init__(self, replies):
            self.replies = list(replies)
            self.budgets = []

        def chat_text(self, prompt, model=None, max_tokens=4096):
            self.budgets.append(max_tokens)
            return self.replies.pop(0)

    retried = Budgeted(["bull", "bear", "", judge()])
    result = run_debate(PACKET, retried)
    assert retried.budgets == [4096, 4096, 4096, 8192]
    assert result["verdict"] == "TRADE"
    assert result["judge"]["retried_empty"] is True

    silent = Budgeted(["bull", "bear", "", ""])
    result = run_debate(PACKET, silent)
    assert result["verdict"] == "WATCH"
    assert result["judge"]["no_reply"] is True
    assert "no verdict was invented" in result["why"]


def test_semicolon_separated_pairs_in_one_bracket():
    """Live TSLA bear, Oct 23: "[a.mitigated = false; b.bottom = 376.75]"
    read "false; b.bottom = 376.75" as the value of a."""
    ev = {"ob": {"above": [{"mitigated": False, "bottom": 376.75}]}}
    text = "[ob.above[0].mitigated = false; ob.above[0].bottom = 376.75]"
    assert [c["status"] for c in verify_citations(text, ev)] == ["verified", "verified"]
