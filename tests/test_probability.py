"""Tests for the probability guardrail. Pure data, fixed clock.

Reference Greeks computed independently of the module (textbook
Black-Scholes at S=100, K=100, T=1y, IV=20%, r=5%, q=0):
d1=0.35, call delta N(0.35)=0.6368, put delta -0.3632,
call theta -6.414/yr (-0.01757/day), put theta -1.658/yr (-0.00454/day).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.guardrail import (
    black_scholes,
    evaluate_chain,
    evaluate_contract,
    guard_provider_chain,
)
from src.data.provider import MarketDataProvider

# 10:00 ET on Oct 22 (14:00 UTC): DTE counts on the ET trading date.
AS_OF = datetime(2026, 10, 22, 14, tzinfo=timezone.utc).timestamp()
EXP_5D = int(AS_OF + 5 * 86400)
EXP_PAST = int(AS_OF - 86400)


def contract(**overrides):
    base = {
        "contractSymbol": "TST261027C00101000",
        "strike": 101.0,
        "bid": 1.40,
        "ask": 1.60,
        "lastPrice": 1.50,
        "volume": 500,
        "openInterest": 2000,
        "impliedVolatility": 0.30,
        "inTheMoney": False,
        "expiration": EXP_5D,
    }
    base.update(overrides)
    return base


def checks_by_name(result):
    return {c["check"]: c["passed"] for c in result["checks"]}


# ----------------------------------------------------------------------
# Black-Scholes primitives
# ----------------------------------------------------------------------
def test_black_scholes_reference_values():
    bs = black_scholes(100.0, 100.0, 1.0, 0.20, "call", rate=0.05, div_yield=0.0)
    assert bs["delta"] == pytest.approx(0.6368, abs=1e-3)
    assert bs["theta_per_day"] == pytest.approx(-0.01757, abs=5e-4)
    bs = black_scholes(100.0, 100.0, 1.0, 0.20, "put", rate=0.05, div_yield=0.0)
    assert bs["delta"] == pytest.approx(-0.3632, abs=1e-3)
    assert bs["theta_per_day"] == pytest.approx(-0.00454, abs=5e-4)


def test_black_scholes_moneyness_ordering():
    itm = black_scholes(100.0, 70.0, 0.5, 0.30, "call")
    otm = black_scholes(100.0, 150.0, 0.5, 0.30, "call")
    assert itm["delta"] > 0.9
    assert otm["delta"] < 0.1


def test_black_scholes_rejects_bad_inputs():
    assert black_scholes(100.0, 100.0, 1.0, 0.0, "call") is None
    assert black_scholes(100.0, 100.0, 0.0, 0.20, "call") is None
    assert black_scholes(0.0, 100.0, 1.0, 0.20, "call") is None


# ----------------------------------------------------------------------
# a rankable weekly call
# ----------------------------------------------------------------------
def test_rankable_call_metrics_and_checks():
    result = evaluate_contract(contract(), "call", spot=100.0, as_of=AS_OF)
    m = result["metrics"]
    assert result["days_to_expiry"] == 5
    assert m["premium"] == pytest.approx(1.50)
    assert m["premium_source"] == "mid"
    assert m["breakeven"] == pytest.approx(102.50)
    assert m["breakeven_move_pct"] == pytest.approx(2.50)
    assert m["delta"] == pytest.approx(0.40, abs=0.01)
    assert m["probability_of_profit"] == pytest.approx(0.24, abs=0.01)
    assert m["theta_burn_usd_per_day"] > 0
    passed = checks_by_name(result)
    assert passed["delta_floor"] is True
    assert passed["premium_known"] is True
    assert passed["iv_known"] is True
    assert passed["not_expired"] is True
    assert result["rankable"] is True


def test_rankable_put_mirrors_the_math():
    put = contract(
        contractSymbol="TST261027P00099000", strike=99.0,
        bid=1.40, ask=1.60, lastPrice=1.50,
    )
    result = evaluate_contract(put, "put", spot=100.0, as_of=AS_OF)
    m = result["metrics"]
    assert m["delta"] == pytest.approx(-0.37, abs=0.01)
    assert m["breakeven"] == pytest.approx(97.50)
    assert m["breakeven_move_pct"] == pytest.approx(-2.50)
    assert result["rankable"] is True


# ----------------------------------------------------------------------
# the delta floor does its job
# ----------------------------------------------------------------------
def test_lottery_contract_fails_delta_floor():
    lottery = contract(strike=130.0, bid=0.05, ask=0.15, lastPrice=0.10)
    result = evaluate_contract(lottery, "call", spot=100.0, as_of=AS_OF)
    assert abs(result["metrics"]["delta"]) < 0.05
    passed = checks_by_name(result)
    assert passed["delta_floor"] is False
    assert result["rankable"] is False
    detail = {c["check"]: c["detail"] for c in result["checks"]}["delta_floor"]
    assert "0.30" in detail


def test_wide_spread_fails_spread_check_but_not_ranking():
    wide = contract(bid=0.50, ask=1.50, lastPrice=1.00)  # 100% of mid
    result = evaluate_contract(wide, "call", spot=100.0, as_of=AS_OF)
    passed = checks_by_name(result)
    assert passed["spread_within_limit"] is False
    # Ranking is the delta gate's call, per the locked rule.
    assert result["rankable"] is True


# ----------------------------------------------------------------------
# honest unknowns
# ----------------------------------------------------------------------
def test_missing_iv_makes_delta_unknown():
    no_iv = contract(impliedVolatility=None)
    result = evaluate_contract(no_iv, "call", spot=100.0, as_of=AS_OF)
    assert result["metrics"]["delta"] is None
    assert result["metrics"]["probability_of_profit"] is None
    assert result["metrics"]["theta_burn_usd_per_day"] is None
    passed = checks_by_name(result)
    assert passed["delta_floor"] is None
    assert passed["iv_known"] is False
    assert result["rankable"] is False


def test_missing_premium_blocks_ranking():
    dark = contract(bid=None, ask=None, lastPrice=None)
    result = evaluate_contract(dark, "call", spot=100.0, as_of=AS_OF)
    assert result["metrics"]["premium"] is None
    assert result["metrics"]["breakeven"] is None
    assert checks_by_name(result)["premium_known"] is False
    assert result["rankable"] is False


def test_expired_and_zero_dte_fail_not_expired():
    dead = contract(expiration=EXP_PAST)
    result = evaluate_contract(dead, "call", spot=100.0, as_of=AS_OF)
    assert result["days_to_expiry"] == -1
    assert checks_by_name(result)["not_expired"] is False
    assert result["rankable"] is False

    today = contract(expiration=int(AS_OF))
    result = evaluate_contract(today, "call", spot=100.0, as_of=AS_OF)
    assert result["days_to_expiry"] == 0
    assert checks_by_name(result)["not_expired"] is False


# ----------------------------------------------------------------------
# whole chain + provider wrapper
# ----------------------------------------------------------------------
def sample_chain():
    return {
        "expiration": EXP_5D,
        "calls": [
            contract(),  # rankable, premium 1.50
            contract(contractSymbol="LOTTO", strike=130.0,
                     bid=0.05, ask=0.15, lastPrice=0.10),
        ],
        "puts": [
            contract(contractSymbol="PUT1", strike=99.0,
                     bid=1.10, ask=1.30, lastPrice=1.20),
        ],
    }


def test_evaluate_chain_ranks_only_passers_cheapest_first():
    result = evaluate_chain(sample_chain(), spot=100.0, as_of=AS_OF)
    assert result["ranked_count"] == 2
    assert result["rejected_count"] == 1
    premiums = [r["metrics"]["premium"] for r in result["ranked"]]
    assert premiums == sorted(premiums)
    assert result["ranked"][0]["option_type"] == "put"  # 1.20 < 1.50
    assert [r["rank"] for r in result["ranked"]] == [1, 2]
    json.dumps(result)


class FakeProvider(MarketDataProvider):
    def get_quote(self, ticker):
        return {"price": 100.0}

    def get_bars(self, ticker, interval="1d", period="2y"):
        raise NotImplementedError

    def get_expirations(self, ticker):
        return [EXP_5D]

    def get_option_chain(self, ticker, expiration=None):
        return sample_chain()


def test_guard_provider_chain_end_to_end():
    result = guard_provider_chain("TST", FakeProvider(), as_of=AS_OF)
    assert result["ticker"] == "TST"
    assert result["spot"] == 100.0
    assert result["ranked_count"] == 2
    json.dumps(result)


def test_dte_counts_on_the_et_date_for_an_evening_run():
    """21:00 ET Oct 21 is already Oct 22 in UTC. Counting on the UTC
    date would call a next-day expiry 0 DTE (expired today); on the
    ET trading date it is correctly 1 DTE."""
    from src.guardrail.probability import days_to_expiry

    evening = datetime(2026, 10, 22, 1, tzinfo=timezone.utc).timestamp()
    expiry = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp())
    assert days_to_expiry(expiry, evening) == 1


def test_select_expiration_skips_same_day_and_prefers_dte_window():
    from src.guardrail.probability import select_expiration

    day = 86400
    today = int(datetime(2026, 10, 22, tzinfo=timezone.utc).timestamp())
    # Daily expiries 0-7 DTE: the nearest one that outlives the 5-day
    # holding window wins (5 DTE), not tomorrow's 1 DTE.
    daily = [today + i * day for i in range(8)]
    picked = select_expiration(daily, AS_OF)
    assert picked == {"expiration": today + 5 * day, "dte": 5,
                      "basis": "covers_holding_window"}
    # Only short expiries in the window: the longest of them.
    short = select_expiration([today, today + day, today + 2 * day], AS_OF)
    assert short == {"expiration": today + 2 * day, "dte": 2,
                     "basis": "longest_in_dte_window"}
    # Nothing in 1-7 DTE: nearest beyond the minimum, labeled as such.
    far = select_expiration([today, today + 30 * day], AS_OF)
    assert far["dte"] == 30 and far["basis"] == "nearest_beyond_min_dte"
    assert select_expiration([today], AS_OF) is None


def test_placeholder_iv_is_unknown_not_a_volatility():
    """Measured live (NFLX premarket, Oct 22): IV 1e-05 gave delta 1.0
    and PoP 0%. A placeholder IV must leave delta unknown and the
    contract unrankable."""
    stale = contract(impliedVolatility=1.0000000000000003e-05)
    result = evaluate_contract(stale, "call", spot=100.0, as_of=AS_OF)
    assert result["metrics"]["delta"] is None
    assert result["metrics"]["probability_of_profit"] is None
    assert checks_by_name(result)["iv_known"] is False
    assert result["rankable"] is False
