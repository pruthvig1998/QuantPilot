"""Tests for the debate loop. The LLM client is a scripted fake:
no live calls, and no model output is invented by the code under
test - every response below is fixture text the fake returns."""
from __future__ import annotations

import json

from src.agent.debate import parse_judge, run_debate
from src.agent.journal import Journal
from src.agent.packet import packet_fingerprint

PACKET = {
    "symbol": "TST",
    "spot": 100.0,
    "as_of": "2026-10-23T13:00:00+00:00",
    "quote": {"price": 100.0, "change_pct": 1.25},
    "liquidity": {
        "score": 42.5,
        "direction": "bullish",
        "components": {"options_oi": 0.4, "momentum": 0.3},
    },
    "indicators": {
        "regime": "uptrend",
        "long_filter": {"price_above_200dma": True},
    },
    "order_blocks": {
        "below": [
            {"type": "bullish", "top": 99.0, "bottom": 98.0, "midpoint": 98.5}
        ],
        "above": [],
        "nearest_pools": [],
    },
    "guardrails": {"candidates": [], "ranked_count": 0, "rejected_count": 0},
    "events": {"red_flag": False, "one_liner": "TST: IV rank unknown"},
    "insider": None,
    "data_quality": {"complete": False, "missing": ["insider"]},
}

BULL_1 = (
    "TST is in an uptrend [indicators.regime = uptrend] with price above "
    "the 200DMA [indicators.long_filter.price_above_200dma = true]. The "
    "liquidity score backs the move [liquidity.score = 42.5]. "
    "STRONGEST BULL EVIDENCE: liquidity.score = 42.5"
)
BEAR_1 = (
    "The packet shows no target level above price "
    "[order_blocks.nearest_pools = []], so the bull case has no defined "
    "upside objective. IV rank is unknown in packet. "
    "STRONGEST BEAR EVIDENCE: order_blocks.nearest_pools = []"
)
GAP = "order_blocks.nearest_pools is empty - no target level in the packet"
BULL_2 = (
    "CONCEDED: this gap cannot be resolved from the packet. The uptrend "
    "evidence stands [indicators.regime = uptrend], but no pool level "
    "exists to target. STRONGEST BULL EVIDENCE: liquidity.score = 42.5"
)
BEAR_2 = (
    "The concession confirms the bear point: without a pool the trade "
    "has no target. Momentum still leans up [liquidity.score = 42.5]. "
    "STRONGEST BEAR EVIDENCE: order_blocks.nearest_pools = []"
)


def judge_json(verdict, conviction=7, direction="call", gap=None,
               summary="Packet evidence is one-sided.",
               risk="IV crush into the print."):
    return json.dumps(
        {
            "verdict": verdict,
            "conviction": conviction,
            "direction": direction,
            "gap": gap,
            "key_evidence": ["liquidity.score = 42.5"],
            "biggest_risk": risk,
            "summary": summary,
        }
    )


class FakeLLM:
    """Scripted chat_text client: returns responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def chat_text(self, prompt, model=None, max_tokens=4096):
        self.prompts.append(prompt)
        return self.responses.pop(0)


# ----------------------------------------------------------------------
# straight path: no loop
# ----------------------------------------------------------------------
def test_straight_trade_path_no_loop():
    llm = FakeLLM([BULL_1, BEAR_1, judge_json("TRADE")])
    result = run_debate(PACKET, llm)
    assert len(llm.prompts) == 3  # bull, bear, judge - and stop
    assert result["looped"] is False
    assert len(result["rounds"]) == 1
    assert result["verdict"] == "TRADE"
    assert result["direction"] == "call"
    assert result["conviction"] == 7
    assert result["packet_hash"] == packet_fingerprint(PACKET)
    # Grounding discipline is in the prompts, with the packet inside.
    assert "GROUNDING RULES" in llm.prompts[0]
    assert "42.5" in llm.prompts[0]
    # The bear sees the bull's actual text.
    assert BULL_1 in llm.prompts[1]
    # Why is composed from the outputs.
    assert "TRADE (conviction 7/10, call bias)" in result["why"]
    assert "one-sided" in result["why"]
    json.dumps(result)


# ----------------------------------------------------------------------
# loop-back path: INSUFFICIENT_EVIDENCE, then a final verdict
# ----------------------------------------------------------------------
def looped_llm(final_judge):
    return FakeLLM(
        [
            BULL_1,
            BEAR_1,
            judge_json(
                "INSUFFICIENT_EVIDENCE",
                conviction=0,
                direction="none",
                gap=GAP,
                summary="Cannot verdict without a target level.",
            ),
            BULL_2,
            BEAR_2,
            final_judge,
        ]
    )


def test_loop_back_on_insufficient_evidence():
    llm = looped_llm(judge_json("TRADE", conviction=6))
    result = run_debate(PACKET, llm)
    assert len(llm.prompts) == 6  # two full rounds
    assert result["looped"] is True
    assert len(result["rounds"]) == 2
    # Round 1 is preserved whole, gap and all.
    assert result["rounds"][0]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert result["rounds"][0]["gap"] == GAP
    assert result["gap_history"] == [GAP]
    # Round 2 prompts carry the judge's gap note and the concede rule.
    assert "EVALUATOR FEEDBACK" in llm.prompts[3]
    assert GAP in llm.prompts[3]
    assert "CONCEDED" in llm.prompts[3]
    assert GAP in llm.prompts[4]
    # The final judge was told INSUFFICIENT is off the table.
    assert "not available this round" in llm.prompts[5]
    # Final verdict comes from round 2.
    assert result["verdict"] == "TRADE"
    assert result["conviction"] == 6
    assert "INSUFFICIENT_EVIDENCE" in result["why"]
    json.dumps(result)


def test_gap_persists_defaults_to_watch():
    llm = looped_llm(
        judge_json(
            "INSUFFICIENT_EVIDENCE",
            conviction=0,
            direction="none",
            gap=GAP,
            summary="Still no target level.",
        )
    )
    result = run_debate(PACKET, llm)
    assert len(result["rounds"]) == 2
    # The second INSUFFICIENT is overridden in code, not trusted.
    assert result["verdict"] == "WATCH"
    assert result["judge"]["forced_default"] is True
    assert "defaulted to WATCH" in result["why"]


def test_journal_entry_logs_both_rounds(tmp_path):
    llm = looped_llm(judge_json("TRADE", conviction=6))
    result = run_debate(PACKET, llm)
    journal = Journal(str(tmp_path / "journal.db"))
    entry_id = journal.record_entry(
        result, {"kind": "trade", "verdict": result["verdict"]}, packet=PACKET
    )
    stored = journal.get_entry(entry_id)
    assert stored["packet_hash"] == result["packet_hash"]
    rounds = stored["debate"]["rounds"]
    assert len(rounds) == 2
    assert rounds[0]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert rounds[0]["gap"] == GAP
    assert rounds[1]["verdict"] == "TRADE"
    assert rounds[1]["gap_note_in"] == GAP
    journal.close()


# ----------------------------------------------------------------------
# parsing + invariants
# ----------------------------------------------------------------------
def test_parse_judge_tolerates_fences():
    text = "Here is my verdict:\n```json\n" + judge_json("SKIP", direction="none") + "\n```"
    parsed = parse_judge(text)
    assert parsed["parse_ok"] is True
    assert parsed["verdict"] == "SKIP"


def test_parse_judge_garbage_falls_back_to_watch():
    parsed = parse_judge("I cannot decide from this.")
    assert parsed["parse_ok"] is False
    assert parsed["verdict"] == "WATCH"
    assert parsed["direction"] == "none"


def test_trade_without_direction_is_downgraded():
    llm = FakeLLM([BULL_1, BEAR_1, judge_json("TRADE", direction="none")])
    result = run_debate(PACKET, llm)
    assert result["verdict"] == "WATCH"
    assert "downgraded" in result["judge"]["loop_note"]
