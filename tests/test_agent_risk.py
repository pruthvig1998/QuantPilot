"""Risk review pass (Part C addition 1) and sector context (addition 5).

Hand-built cards with hand-computed reference numbers; no LLM."""
from __future__ import annotations

import json

from src.agent.risk import apply_risk_review, review_card, reward_risk, sector_context


def trade_card(**over):
    card = {
        "symbol": "TST",
        "kind": "trade",
        "verdict": "TRADE",
        "direction": "call",
        "contract": {"contract_symbol": "TST1035C"},
        # The cards-test worked example: entry 101.3, stop 100.85, target 105.
        "levels": {"entry": 101.3, "stop": 100.85, "target": 105.0},
        "sizing": {"contracts": 2, "executable": True, "notes": []},
        "checks": [
            {"check": "earnings_in_window", "passed": True, "detail": "outside"},
            {"check": "event_crush_risk", "passed": True, "detail": "not elevated"},
            {"check": "iv_rank_known", "passed": None, "detail": "unknown - no range"},
        ],
    }
    card.update(over)
    return card


def test_reward_risk_reference():
    # |105 - 101.3| / |101.3 - 100.85| = 3.7 / 0.45 = 8.222 -> 8.22
    assert reward_risk({"entry": 101.3, "stop": 100.85, "target": 105.0}) == 8.22
    assert reward_risk({"entry": 101.3, "stop": None, "target": 105.0}) is None


def test_clean_trade_clears_with_cautions_listed():
    review = review_card({"events": {"red_flag": False}}, {}, trade_card())
    assert review["downgraded"] is False
    assert review["verdict_out"] == "TRADE"
    assert review["reward_risk"] == 8.22
    assert any("iv_rank_known unscored" in c for c in review["cautions"])
    assert review["line"].startswith("Risk review: cleared")


def test_crush_risk_vetoes_and_card_becomes_no_trade():
    card = trade_card(checks=[
        {"check": "event_crush_risk", "passed": False,
         "detail": "IV rank 82 into a market event inside the window"},
    ])
    review = review_card({"events": {"red_flag": True}}, {}, card)
    assert review["downgraded"] is True
    assert review["verdict_out"] == "WATCH"
    assert "IV rank 82" in review["line"]
    out = apply_risk_review(card, review)
    assert out["kind"] == "no_trade" and out["downgraded"] is True
    assert out["sizing"]["contracts"] == 0
    assert out["risk_review"] is review
    json.dumps(out)


def test_earnings_in_window_vetoes():
    card = trade_card(checks=[
        {"check": "earnings_in_window", "passed": False,
         "detail": "earnings on 2026-10-26, 3 day(s) away"},
    ])
    review = review_card({"events": {}}, {}, card)
    assert review["downgraded"] is True
    assert "earnings inside the holding window" in review["reasons"][0]


def test_poor_reward_risk_and_missing_target_veto():
    # target 101.6: |101.6 - 101.3| / 0.45 = 0.67 < 1.0
    thin = review_card({}, {}, trade_card(levels={"entry": 101.3, "stop": 100.85,
                                                  "target": 101.6}))
    assert thin["reward_risk"] == 0.67
    assert thin["downgraded"] is True
    blind = review_card({}, {}, trade_card(levels={"entry": 101.3, "stop": 100.85,
                                                   "target": None}))
    assert "no target level" in blind["reasons"][0]


def test_unsized_trade_vetoes():
    card = trade_card(sizing={"contracts": 0, "executable": False,
                              "notes": ["1% risk budget buys less than one contract"]})
    assert review_card({}, {}, card)["downgraded"] is True


def test_review_never_touches_a_no_trade():
    card = trade_card(kind="no_trade", verdict="WATCH")
    review = review_card({"events": {"red_flag": True}}, {}, card)
    assert review["applies"] is False and review["downgraded"] is False
    assert apply_risk_review(card, review)["kind"] == "no_trade"


def test_sector_context_lines():
    xray = {"read": {"posture": "risk_on"},
            "sectors": {"sectors": [
                {"ticker": "XLK", "rank": 1, "label": "leading"},
                {"ticker": "XLY", "rank": 9, "label": "lagging"},
            ]}}
    assert sector_context("NVDA", xray)["line"] == (
        "NVDA: sector XLK ranks #1 of 2 (leading), market posture risk_on."
    )
    assert sector_context("SPY", xray)["sector_etf"] is None
    assert "not ranked" in sector_context("META", xray)["line"]
