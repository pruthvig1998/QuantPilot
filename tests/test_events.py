"""Tests for the IV / event-risk guard. Pure data, fixed dates.

Static market calendar under test (config.MARKET_EVENTS):
FOMC 2026-10-28 and 2026-12-09, NFP 2026-11-06 and 2026-12-04,
CPI 2026-11-10 and 2026-12-10.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from src.data.provider import MarketDataProvider
from src.guardrail import (
    assess_from_provider,
    assess_risk,
    events_in_window,
    iv_rank,
    nearest_money_iv,
)

# IV 0.50 inside a 0.20-0.55 range = rank 85.7 (elevated).
ELEVATED = {"current_iv": 0.50, "iv_low_52w": 0.20, "iv_high_52w": 0.55}
# IV 0.34 inside the same range = rank 40.0 (not elevated).
CALM = {"current_iv": 0.34, "iv_low_52w": 0.20, "iv_high_52w": 0.55}
QUIET_DAY = date(2026, 11, 16)  # no market event within 5 days


def checks_by_name(result):
    return {c["check"]: c["passed"] for c in result["checks"]}


# ----------------------------------------------------------------------
# iv rank + static calendar (pure)
# ----------------------------------------------------------------------
def test_iv_rank_math_and_clamps():
    assert iv_rank(0.41, 0.18, 0.55) == pytest.approx(62.2)
    assert iv_rank(0.60, 0.18, 0.55) == 100.0  # clamped at the top
    assert iv_rank(0.10, 0.18, 0.55) == 0.0    # clamped at the bottom


def test_iv_rank_unknown_without_a_range():
    assert iv_rank(0.41, None, 0.55) is None
    assert iv_rank(0.41, 0.18, None) is None
    assert iv_rank(None, 0.18, 0.55) is None
    assert iv_rank(0.41, 0.30, 0.30) is None  # degenerate range


def test_events_in_window_hits_and_boundaries():
    hits = events_in_window(date(2026, 10, 26), holding_days=5)
    assert [(e["type"], e["days_away"]) for e in hits] == [("FOMC", 2)]

    hits = events_in_window(date(2026, 12, 7), holding_days=5)
    assert [(e["type"], e["days_away"]) for e in hits] == [
        ("FOMC", 2),
        ("CPI", 3),
    ]

    # Exactly at the window edge counts; one day further does not.
    hits = events_in_window(date(2026, 11, 1), holding_days=5)
    assert [(e["type"], e["days_away"]) for e in hits] == [("NFP", 5)]
    assert events_in_window(QUIET_DAY, holding_days=5) == []


# ----------------------------------------------------------------------
# the red flag: elevated IV into an event
# ----------------------------------------------------------------------
def test_red_flag_elevated_iv_into_earnings():
    result = assess_risk(
        "NVDA", as_of=date(2026, 10, 26), holding_days=5,
        earnings_date=date(2026, 10, 29), **ELEVATED,
    )
    assert result["iv"]["rank_pct"] == pytest.approx(85.7)
    assert result["earnings"]["in_window"] is True
    passed = checks_by_name(result)
    assert passed["iv_rank_known"] is True
    assert passed["iv_elevated"] is False
    assert passed["earnings_in_window"] is False
    assert passed["event_crush_risk"] is False
    assert result["red_flag"] is True
    assert "IV rank 86" in result["one_liner"]
    assert "earnings in 3 days" in result["one_liner"]
    assert "crush risk" in result["one_liner"]


def test_red_flag_elevated_iv_into_market_event():
    # Earnings are far away, but the FOMC lands inside the window.
    result = assess_risk(
        "SPY", as_of=date(2026, 10, 26), holding_days=5,
        earnings_date=date(2026, 12, 15), **ELEVATED,
    )
    passed = checks_by_name(result)
    assert passed["earnings_in_window"] is True
    assert passed["market_event_in_window"] is False
    assert passed["event_crush_risk"] is False
    assert result["red_flag"] is True
    assert "FOMC" in result["one_liner"]


def test_elevated_iv_no_event_is_not_flagged():
    result = assess_risk(
        "AMD", as_of=QUIET_DAY, holding_days=5,
        earnings_date=date(2026, 12, 20), **ELEVATED,
    )
    assert checks_by_name(result)["event_crush_risk"] is True
    assert result["red_flag"] is False


def test_calm_iv_into_earnings_is_not_flagged():
    result = assess_risk(
        "META", as_of=date(2026, 10, 26), holding_days=5,
        earnings_date=date(2026, 10, 28), **CALM,
    )
    assert result["iv"]["rank_pct"] == pytest.approx(40.0)
    passed = checks_by_name(result)
    assert passed["iv_elevated"] is True
    assert passed["earnings_in_window"] is False
    assert passed["event_crush_risk"] is True
    assert result["red_flag"] is False
    assert "not elevated" in result["one_liner"]


# ----------------------------------------------------------------------
# honest unknowns
# ----------------------------------------------------------------------
def test_unknown_iv_range_makes_rank_checks_unknown():
    result = assess_risk(
        "TSLA", as_of=QUIET_DAY, holding_days=5, current_iv=0.42,
    )
    assert result["iv"]["rank_pct"] is None
    passed = checks_by_name(result)
    assert passed["iv_rank_known"] is None
    assert passed["iv_elevated"] is None
    assert passed["event_crush_risk"] is None
    assert result["red_flag"] is False
    assert "unknown" in result["one_liner"]


def test_unknown_earnings_with_elevated_iv_is_unscored_not_safe():
    result = assess_risk(
        "NFLX", as_of=QUIET_DAY, holding_days=5, earnings_date=None,
        **ELEVATED,
    )
    passed = checks_by_name(result)
    assert passed["earnings_in_window"] is None
    # IV is elevated and no market event is in the window, but with no
    # earnings date the crush gate must NOT claim all-clear.
    assert passed["event_crush_risk"] is None
    assert result["red_flag"] is False
    assert passed["market_event_in_window"] is True


def test_market_event_check_is_never_unknown():
    result = assess_risk("SPY", as_of=date(2026, 10, 26), holding_days=5)
    assert checks_by_name(result)["market_event_in_window"] is False
    assert result["market_events_in_window"][0]["type"] == "FOMC"


# ----------------------------------------------------------------------
# provider wrapper: IV off the chain, the rest honestly unknown
# ----------------------------------------------------------------------
def sample_chain():
    return {
        "expiration": 1792108800,
        "calls": [
            {"contractSymbol": "C100", "strike": 100.0, "impliedVolatility": 0.33},
            {"contractSymbol": "C105", "strike": 105.0, "impliedVolatility": 0.40},
        ],
        "puts": [
            {"contractSymbol": "P95", "strike": 95.0, "impliedVolatility": 0.38},
        ],
    }


def test_nearest_money_iv_picks_closest_strike():
    assert nearest_money_iv(sample_chain(), spot=100.0) == pytest.approx(0.33)
    assert nearest_money_iv(sample_chain(), spot=104.0) == pytest.approx(0.40)
    assert nearest_money_iv({"calls": [], "puts": []}, spot=100.0) is None


class FakeProvider(MarketDataProvider):
    def get_quote(self, ticker):
        return {"price": 100.0}

    def get_bars(self, ticker, interval="1d", period="2y"):
        raise NotImplementedError

    def get_expirations(self, ticker):
        return [1792108800]

    def get_option_chain(self, ticker, expiration=None):
        return sample_chain()


def test_assess_from_provider_reports_what_it_cannot_know():
    result = assess_from_provider(
        "TST", FakeProvider(), as_of=QUIET_DAY, holding_days=5
    )
    assert result["spot"] == 100.0
    assert result["iv"]["current"] == pytest.approx(0.33)
    assert result["iv"]["rank_pct"] is None       # no IV history exists
    assert result["earnings"]["date"] is None     # no calendar exists
    passed = checks_by_name(result)
    assert passed["iv_rank_known"] is None
    assert passed["earnings_in_window"] is None
    assert passed["market_event_in_window"] is True  # static list computes
    json.dumps(result)
