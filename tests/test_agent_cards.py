"""Tests for structured trade cards (module 7).

Fixtures are shared with the packet tests (same fake provider and
chain), and the one sizing example is hand-built so the expected
contract count is arithmetic, not a guess.
"""
from __future__ import annotations

import json

import pytest

from src.agent.cards import build_card
from src.agent.packet import assemble_packet, packet_fingerprint
from src.guardrail.probability import evaluate_contract
from tests.test_agent_packet import AS_OF, EXPIRY, FakeProvider, make_chain


def debate(verdict="TRADE", direction="call", conviction=7,
           summary="Packet evidence is one-sided."):
    return {
        "verdict": verdict,
        "conviction": conviction,
        "direction": direction,
        "why": f"{verdict} why text",
        "judge": {"summary": summary, "biggest_risk": "crush risk"},
        "packet_hash": None,
        "rounds": [],
    }


def packet_and_debate(verdict="TRADE", direction="call", provider=None):
    packet = assemble_packet("TST", provider or FakeProvider(), as_of=AS_OF)
    result = debate(verdict, direction)
    result["packet_hash"] = packet_fingerprint(packet)
    return packet, result


# ----------------------------------------------------------------------
# TRADE cards
# ----------------------------------------------------------------------
def test_trade_card_call_picks_the_in_band_contract():
    packet, result = packet_and_debate()
    card = build_card(packet, result)
    assert card["kind"] == "trade"
    assert card["downgraded"] is False
    assert card["contract"]["option_type"] == "call"
    # The 103.5 call is the one in the 0.35 delta band; the 102 call
    # is rankable but out of band, the 105 call fails the delta floor.
    assert card["contract"]["strike"] == 103.5
    sources = {c["source"] for c in card["checks"]}
    assert sources == {"guardrail", "selection", "events"}
    selection = [c for c in card["checks"] if c["source"] == "selection"]
    assert all(c["passed"] is True for c in selection)
    json.dumps(card)


def test_trade_card_levels_and_sizing():
    packet, result = packet_and_debate()
    card = build_card(packet, result)
    levels = card["levels"]
    assert levels["entry_zone"]["type"] == "bullish"
    assert levels["entry"] == pytest.approx(100.2)
    assert levels["stop"] == pytest.approx(99.75)
    assert levels["target"] == 105.0
    assert levels["target_source"] == "liquidity_pool"
    sizing = card["sizing"]
    assert sizing["risk_budget_usd"] == 100.0
    # Delta-adjusted (Oct 22): |delta| 0.3550 (103.5C, spot 102.2, 4 DTE,
    # IV 30%, computed independently) x 0.45 x 100 = $15.98 per contract
    # -> floor(100 / 15.98) = 6 contracts, $0.76 premium -> $456 outlay.
    assert sizing["per_contract_risk_usd"] == pytest.approx(15.98, abs=0.02)
    assert sizing["contracts"] == 6
    assert sizing["premium_outlay_usd"] == 456.0
    assert sizing["executable"] is True
    assert "bleeds $" in card["greeks_plain"]["line"]
    assert "break even" in card["greeks_plain"]["line"]


def test_put_card_mirrors_the_geometry():
    packet, result = packet_and_debate(direction="put")
    # The detector's bearish block above spot is wide ([103.0, 105.0]),
    # so at the default $10k account the 1% risk budget buys zero
    # contracts; size this card on a $100k account to exercise the
    # mirror geometry with a live position size.
    card = build_card(packet, result, account_size=100_000.0)
    assert card["kind"] == "trade"
    assert card["contract"]["option_type"] == "put"
    assert card["contract"]["strike"] == 101.0
    levels = card["levels"]
    assert levels["entry_zone"]["type"] == "bearish"
    assert levels["entry"] == pytest.approx(104.0)
    assert levels["stop"] == pytest.approx(105.5)
    assert levels["stop"] > levels["entry"]  # put stops sit above
    assert levels["target"] == 99.1
    assert levels["target_source"] == "support_resistance"
    # |delta| 0.3465 (101P, IV 31%, computed independently) x 1.5 x 100
    # = $51.98 -> floor(1000 / 51.98) = 19 (5% cap allows 62).
    assert card["sizing"]["per_contract_risk_usd"] == pytest.approx(51.98, abs=0.02)
    assert card["sizing"]["contracts"] == 19


def test_sizing_worked_example_is_exact():
    """Hand-built packet: zone [101.0, 101.6], entry at the 101.3
    midpoint, stop 0.25 zone-widths beyond the zone = 100.85, so
    the stop distance is 0.45; per-contract risk is |delta| 0.3550 x
    0.45 x 100 = $15.98, so the $100 risk budget buys 6 contracts."""
    raw = {
        "contractSymbol": "TST1035C",
        "strike": 103.5,
        "bid": 0.72,
        "ask": 0.80,
        "lastPrice": 0.76,
        "volume": 600,
        "openInterest": 2500,
        "impliedVolatility": 0.30,
        "inTheMoney": False,
    }
    ev = evaluate_contract(raw, "call", spot=102.2, as_of=AS_OF, expiration=EXPIRY)
    candidate = {
        "contract_symbol": ev["contract_symbol"],
        "option_type": "call",
        "evaluation": ev,
        "raw": {
            k: raw[k]
            for k in (
                "contractSymbol", "strike", "bid", "ask", "lastPrice",
                "volume", "openInterest", "impliedVolatility",
            )
        },
    }
    packet = {
        "symbol": "TST",
        "spot": 102.2,
        "as_of": "2026-10-23T13:00:00+00:00",
        "order_blocks": {
            "below": [
                {
                    "type": "bullish",
                    "top": 101.6,
                    "bottom": 101.0,
                    "midpoint": 101.3,
                    "mitigated": False,
                }
            ],
            "above": [],
            "nearest_pools": [
                {"type": "equal_highs", "level": 105.0, "touches": 2}
            ],
            "analysis": {
                "support_resistance": {"resistance": [105.0], "support": [99.1]}
            },
        },
        "guardrails": {"candidates": [candidate], "ranked_count": 1,
                       "rejected_count": 0},
        "events": {"checks": []},
    }
    card = build_card(packet, debate())
    assert card["kind"] == "trade"
    assert card["levels"]["entry"] == pytest.approx(101.3)
    assert card["levels"]["stop"] == pytest.approx(100.85)
    sizing = card["sizing"]
    assert sizing["stop_distance"] == pytest.approx(0.45)
    # Delta-adjusted: |delta| 0.3550 x 0.45 x 100 = $15.98 at the stop
    # (the old delta-1 rule said $45 and bought only 2 contracts).
    assert sizing["per_contract_risk_usd"] == pytest.approx(15.98, abs=0.02)
    assert sizing["contracts"] == 6
    assert sizing["premium_outlay_usd"] == 456.0
    assert sizing["risk_basis"].startswith("|delta| 0.35")


# ----------------------------------------------------------------------
# skeletons and downgrades
# ----------------------------------------------------------------------
def test_watch_card_is_a_skeleton_with_the_same_checks():
    packet, result = packet_and_debate(
        verdict="WATCH", direction="none",
    )
    result["judge"]["summary"] = "Setup plausible, target unproven."
    card = build_card(packet, result)
    assert card["kind"] == "no_trade"
    assert "WATCH" in card["rejection"]["reason"]
    assert "target unproven" in card["rejection"]["reason"]
    # The nearest guardrail survivor is shown for the record.
    assert card["contract"]["strike"] == 103.5
    assert card["sizing"]["contracts"] == 0
    sources = {c["source"] for c in card["checks"]}
    assert "events" in sources and "selection" in sources
    json.dumps(card)


def test_trade_is_downgraded_when_filters_reject_every_contract():
    chain = make_chain()
    for contract in chain["calls"]:
        if contract["contractSymbol"] == "TST1035C":
            contract["volume"] = 10       # below the 50 minimum
            contract["openInterest"] = 50  # below the 100 minimum
    packet, result = packet_and_debate(provider=FakeProvider(chain=chain))
    card = build_card(packet, result)
    assert card["kind"] == "no_trade"
    assert card["downgraded"] is True
    failed = card["rejection"]["failed_checks"]
    assert "option_volume" in failed
    assert "open_interest" in failed
    # The rejected contract is still shown, with its failed checks.
    assert card["contract"]["strike"] == 103.5
    json.dumps(card)


def test_unknown_volume_cannot_confirm_a_trade():
    chain = make_chain()
    for contract in chain["calls"]:
        if contract["contractSymbol"] == "TST1035C":
            contract["volume"] = None  # nothing printed: unknown, not zero
    packet, result = packet_and_debate(provider=FakeProvider(chain=chain))
    card = build_card(packet, result)
    assert card["downgraded"] is True
    volume_check = next(
        c for c in card["checks"] if c["check"] == "option_volume"
    )
    assert volume_check["passed"] is None
