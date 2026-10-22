"""Tests for the data packet assembler. Synthetic data, fake provider."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.agent.packet import assemble_packet, packet_fingerprint
from src.data.provider import MarketDataProvider

AS_OF = datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc).timestamp()
EXPIRY = int(datetime(2026, 10, 27, 20, 0, tzinfo=timezone.utc).timestamp())
SPOT = 102.2


def make_daily(closes) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": np.full(len(closes), 1_000_000.0),
        },
        index=idx,
    )


def daily_bars():
    return make_daily([60.0 + (42.2 / 299.0) * i for i in range(300)])


def weekly_bars():
    return make_daily([50.0 + 0.65 * i for i in range(80)])


def intraday_bars() -> pd.DataFrame:
    """Hand-built 5m bars: a bullish order block at [99.9, 100.5]
    (origin bar 1, break bar 2) and equal highs at 105.0 (bars 4, 7)."""
    rows = [
        (100.0, 100.6, 99.6, 100.3),
        (100.3, 100.5, 99.9, 99.95),
        (99.95, 101.6, 99.1, 101.4),
        (101.4, 102.2, 101.0, 101.9),
        (101.9, 105.0, 101.8, 104.6),
        (104.6, 104.9, 103.0, 103.4),
        (103.4, 103.8, 102.6, 103.1),
        (103.1, 105.0, 103.0, 104.7),
        (104.7, 104.8, 103.9, 104.1),
        (104.1, 104.3, 102.2, 102.5),
        (102.5, 102.9, 101.8, 102.2),
    ]
    idx = pd.date_range("2026-10-23 13:30", periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [10_000.0] * len(rows),
        },
        index=idx,
    )


def _contract(symbol, strike, bid, ask, volume, oi, iv):
    return {
        "contractSymbol": symbol,
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "lastPrice": (bid + ask) / 2,
        "volume": volume,
        "openInterest": oi,
        "impliedVolatility": iv,
        "inTheMoney": False,
    }


def make_chain():
    return {
        "expiration": EXPIRY,
        "calls": [
            _contract("TST102C", 102.0, 3.40, 3.60, 300, 1500, 0.30),
            _contract("TST1035C", 103.5, 0.72, 0.80, 600, 2500, 0.30),
            _contract("TST105C", 105.0, 0.30, 0.42, 700, 3000, 0.30),
            _contract("TST120C", 120.0, 0.02, 0.10, 5, 20, 0.35),
        ],
        "puts": [
            _contract("TST101P", 101.0, 0.76, 0.84, 450, 2200, 0.31),
            _contract("TST103P", 103.0, 1.90, 2.05, 250, 1200, 0.31),
            _contract("TST90P", 90.0, 0.05, 0.12, 10, 40, 0.33),
        ],
    }


class FakeProvider(MarketDataProvider):
    def __init__(self, chain=None, fail_chain=False):
        self._chain = make_chain() if chain is None else chain
        self._fail_chain = fail_chain

    def get_quote(self, ticker):
        return {
            "ticker": ticker,
            "price": SPOT,
            "change": 1.2,
            "change_pct": 1.19,
            "volume": 5_000_000,
            "day_high": 103.0,
            "day_low": 100.9,
            "open": 101.0,
            "previous_close": 101.0,
        }

    def get_bars(self, ticker, interval="1d", period="2y"):
        if interval == "5m":
            return intraday_bars()
        if interval == "1wk":
            return weekly_bars()
        return daily_bars()

    def get_expirations(self, ticker):
        return [EXPIRY]

    def get_option_chain(self, ticker, expiration=None):
        if self._fail_chain:
            raise ValueError("chain unavailable")
        return self._chain


# ----------------------------------------------------------------------
# assembly
# ----------------------------------------------------------------------
def test_packet_has_every_section():
    packet = assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    assert packet["symbol"] == "TST"
    assert packet["spot"] == SPOT
    assert packet["indicators"]["regime"] == "uptrend"
    assert packet["liquidity"]["direction"] == "bullish"
    assert packet["liquidity"]["score"] > 15
    assert set(packet["liquidity"]["components"]) == {
        "options_oi",
        "options_volume",
        "momentum",
        "relative_volume",
    }
    json.dumps(packet)


def test_packet_order_blocks_and_pools():
    packet = assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    below = packet["order_blocks"]["below"]
    assert below[0]["type"] == "bullish"
    assert below[0]["bottom"] == 99.9
    assert below[0]["midpoint"] == 100.2
    assert below[0]["mitigated"] is False
    pools = packet["order_blocks"]["nearest_pools"]
    highs = [p for p in pools if p["type"] == "equal_highs"]
    assert highs and highs[0]["level"] == 105.0
    assert highs[0]["touches"] == 2


def test_packet_candidates_carry_raw_chain_fields():
    packet = assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    guard = packet["guardrails"]
    assert guard["ranked_count"] == 4  # 102C, 103.5C, 101P, 103P survive
    # Capped PER SIDE (3 each), cheapest first within a side: both
    # calls and both puts survive, so a put verdict has put candidates.
    assert len(guard["candidates"]) == 4
    sides = [c["option_type"] for c in guard["candidates"]]
    assert sides == ["call", "call", "put", "put"]
    first = guard["candidates"][0]
    assert first["contract_symbol"] == "TST1035C"
    assert first["raw"]["volume"] == 600
    assert first["raw"]["openInterest"] == 2500
    assert first["evaluation"]["rankable"] is True


def test_packet_events_are_honest_about_unknowns():
    packet = assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    events = packet["events"]
    # Oct 28, 2026 FOMC sits exactly 5 days after the Oct 23 as_of.
    assert events["market_events_in_window"][0]["type"] == "FOMC"
    # No IV history behind the provider: rank stays unknown, not invented.
    assert events["iv"]["rank_pct"] is None
    check_names = {c["check"] for c in events["checks"]}
    assert "event_crush_risk" in check_names
    assert events["one_liner"].startswith("TST: IV rank unknown")


def test_packet_missing_insider_is_null_not_invented(tmp_path):
    missing = tmp_path / "no_such_file.json"
    packet = assemble_packet(
        "TST", FakeProvider(), as_of=AS_OF, insider_path=str(missing)
    )
    assert packet["insider"] is None
    assert packet["insider_source"] is None
    assert "insider" in packet["data_quality"]["missing"]
    json.dumps(packet)


def test_packet_insider_context_when_file_exists(tmp_path):
    entry = {
        "runup_days": 3,
        "hits": 1,
        "hit_rate": 0.333,
        "latest_hit": {"insider": "DOE JANE", "planned": True},
        "active_now": False,
        "note": "1 of 3 run-up days followed by insider sales",
    }
    path = tmp_path / "insider_patterns.json"
    path.write_text(json.dumps({"TST": entry}))
    packet = assemble_packet(
        "TST", FakeProvider(), as_of=AS_OF, insider_path=str(path)
    )
    assert packet["insider"]["hit_rate"] == 0.333
    assert packet["insider"]["active_now"] is False
    assert "insider" not in packet["data_quality"]["missing"]


def test_packet_survives_a_failed_chain():
    packet = assemble_packet(
        "TST", FakeProvider(fail_chain=True), as_of=AS_OF
    )
    assert packet["guardrails"]["candidates"] == []
    assert packet["events"] is None
    assert "option_chain" in packet["data_quality"]["missing"]
    assert packet["data_quality"]["complete"] is False
    # The rest of the packet still assembles.
    assert packet["indicators"]["regime"] == "uptrend"
    json.dumps(packet)


def test_packet_fingerprint_is_stable():
    packet = assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    assert packet_fingerprint(packet) == packet_fingerprint(dict(packet))
    packet["spot"] = 999.0
    assert packet_fingerprint(packet) != packet_fingerprint(
        assemble_packet("TST", FakeProvider(), as_of=AS_OF)
    )


def test_packet_skips_same_day_expiry_for_the_dte_window():
    """Front expiry is same-day (0 DTE fails not_expired); the packet
    must trade the nearest expiry inside the 1-7 DTE window instead."""
    same_day = int(datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc).timestamp())

    class DailyExpiryProvider(FakeProvider):
        def get_expirations(self, ticker):
            return [same_day, EXPIRY]

        def get_option_chain(self, ticker, expiration=None):
            assert expiration == EXPIRY, "packet asked for the 0DTE chain"
            return super().get_option_chain(ticker, expiration=expiration)

    packet = assemble_packet("TST", DailyExpiryProvider(), as_of=AS_OF)
    selection = packet["guardrails"]["selection"]
    assert selection == {
        # 4 DTE is the longest in the window; none outlives the 5-day hold
        "expiration": EXPIRY, "dte": 4, "basis": "longest_in_dte_window",
    }
    assert packet["guardrails"]["ranked_count"] == 4


def test_packet_wires_earnings_date_from_provider():
    class EarningsProvider(FakeProvider):
        def get_earnings_date(self, ticker):
            return {"date": "2026-10-26", "window_end": None,
                    "estimate": False, "source": "test calendar"}

    packet = assemble_packet("TST", EarningsProvider(), as_of=AS_OF)
    events = packet["events"]
    assert events["earnings"]["date"] == "2026-10-26"
    assert events["earnings"]["days_away"] == 3
    by_name = {c["check"]: c for c in events["checks"]}
    assert by_name["earnings_in_window"]["passed"] is False
    assert events["earnings_source"] == "test calendar"


def test_chain_wide_zero_oi_is_carried_as_unknown():
    class BlankOIProvider(FakeProvider):
        def get_option_chain(self, ticker, expiration=None):
            chain = super().get_option_chain(ticker, expiration=expiration)
            return {
                **chain,
                "calls": [{**c, "openInterest": 0} for c in chain["calls"]],
                "puts": [{**c, "openInterest": 0} for c in chain["puts"]],
            }

    packet = assemble_packet("TST", BlankOIProvider(), as_of=AS_OF)
    guard = packet["guardrails"]
    assert guard["oi_feed_blank"] is True
    assert all(c["raw"]["openInterest"] is None for c in guard["candidates"])
