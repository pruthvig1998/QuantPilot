"""Tests for the Market X-Ray. Synthetic data via a fake provider."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src import config
from src.data.provider import MarketDataProvider
from src.xray import (
    breadth,
    classify_snapshot,
    market_xray,
    rsi_zone,
    sector_rotation,
)


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


def uptrend_bars(n=260):
    return make_daily([100.0 + 0.08 * i for i in range(n)])


def downtrend_bars(n=260):
    return make_daily([200.0 - 0.15 * i for i in range(n)])


def mixed_bars(n=260):
    """Long ramp up, sharp recent dip: above the 200DMA, bearish stack."""
    closes = [80.0 + (40.0 / 239.0) * i for i in range(240)]
    closes += [120.0 - 0.2 * (i + 1) for i in range(20)]
    return make_daily(closes)


class FakeProvider(MarketDataProvider):
    """Bars keyed by ticker (any interval/period); named names fail."""

    def __init__(self, bars, failing=()):
        self._bars = bars
        self._failing = set(failing)

    def get_quote(self, ticker):
        return {"price": float(self._bars[ticker]["close"].iloc[-1])}

    def get_bars(self, ticker, interval="1d", period="2y"):
        if ticker in self._failing:
            raise ValueError(f"no data for {ticker}")
        return self._bars[ticker]

    def get_expirations(self, ticker):
        return []

    def get_option_chain(self, ticker, expiration=None):
        return {"expiration": None, "calls": [], "puts": []}


def snapshot(direction_bits, rsi_daily=55.0):
    """Hand-built analyze_symbol-shaped snapshot for classify tests."""
    return {
        "ticker": "TST",
        "price": 100.0,
        "regime": "mixed",
        "ema": {
            "bullish_stack": direction_bits[0],
            "bearish_stack": direction_bits[1],
        },
        "long_filter": {
            "price_above_200dma": direction_bits[2],
            "distance_200dma_pct": 5.0,
        },
        "rsi_daily": rsi_daily,
    }


# ----------------------------------------------------------------------
# classify + rsi zones (pure)
# ----------------------------------------------------------------------
def test_rsi_zone_bounds():
    assert rsi_zone(70.0) == "overbought"
    assert rsi_zone(85.0) == "overbought"
    assert rsi_zone(30.0) == "oversold"
    assert rsi_zone(12.0) == "oversold"
    assert rsi_zone(50.0) == "neutral"
    assert rsi_zone(None) is None


def test_classify_bullish_needs_stack_and_200dma():
    row = classify_snapshot(snapshot((True, False, True)))
    assert row["direction"] == "bullish"
    assert row["above_200dma"] is True
    assert row["bullish_stack"] is True


def test_classify_bearish_needs_stack_and_below_200dma():
    row = classify_snapshot(snapshot((False, True, False), rsi_daily=25.0))
    assert row["direction"] == "bearish"
    assert row["rsi_zone"] == "oversold"


def test_classify_mixed_signals_are_neutral():
    # Bullish stack but below the 200DMA: not bullish, not bearish.
    row = classify_snapshot(snapshot((True, False, False)))
    assert row["direction"] == "neutral"
    # Bearish stack but still above the 200DMA: also neutral.
    row = classify_snapshot(snapshot((False, True, True)))
    assert row["direction"] == "neutral"


# ----------------------------------------------------------------------
# breadth over the watchlist
# ----------------------------------------------------------------------
def three_name_provider():
    return FakeProvider(
        {
            "UP": uptrend_bars(),
            "DOWN": downtrend_bars(),
            "MIX": mixed_bars(),
        },
        failing=("BAD",),
    )


def test_breadth_counts_signal_families():
    result = breadth(three_name_provider(), tickers=["UP", "DOWN", "MIX"])
    counts = result["counts"]
    assert counts["total"] == 3
    assert counts["bullish"] == 1
    assert counts["bearish"] == 1
    assert counts["neutral"] == 1
    assert counts["above_200dma"] == 2  # UP and MIX
    assert counts["below_200dma"] == 1
    assert counts["bullish_stack"] == 1
    assert counts["bearish_stack"] == 2  # DOWN and MIX
    assert counts["pct_above_200dma"] == 66.7


def test_breadth_rows_carry_the_signals():
    result = breadth(three_name_provider(), tickers=["UP"])
    row = result["symbols"][0]
    assert row["ticker"] == "UP"
    assert row["direction"] == "bullish"
    assert row["above_200dma"] is True
    assert row["rsi_zone"] in ("overbought", "neutral", "oversold")


def test_breadth_bad_name_goes_to_errors():
    result = breadth(three_name_provider(), tickers=["UP", "BAD"])
    assert [r["ticker"] for r in result["symbols"]] == ["UP"]
    assert result["errors"][0]["ticker"] == "BAD"


def test_breadth_is_json_serializable():
    result = breadth(three_name_provider(), tickers=["UP", "DOWN", "MIX"])
    json.dumps(result)


# ----------------------------------------------------------------------
# sector rotation
# ----------------------------------------------------------------------
def sector_provider():
    bars = {"SPY": make_daily([300.0 + 0.15 * i for i in range(260)])}
    bars["XLK"] = make_daily([100.0 + 0.30 * i for i in range(260)])
    bars["XLE"] = make_daily([200.0 - 0.45 * i for i in range(260)])
    for ticker in config.SECTOR_ETFS:
        bars.setdefault(ticker, make_daily([100.0 + 0.02 * i for i in range(260)]))
    return FakeProvider(bars, failing=("XLB",))


def test_sector_rotation_ranks_strongest_top():
    result = sector_rotation(sector_provider())
    sectors = result["sectors"]
    assert len(sectors) == 9  # XLB failed and went to errors
    assert result["errors"][0]["ticker"] == "XLB"
    assert sectors[0]["ticker"] == "XLK"
    assert sectors[0]["label"] == "leading"
    assert sectors[0]["rs_21d_pct"] > 0
    assert sectors[-1]["ticker"] == "XLE"
    assert sectors[-1]["label"] == "lagging"
    assert sectors[-1]["rs_21d_pct"] < 0
    assert [s["rank"] for s in sectors] == list(range(1, 10))


def test_sector_rotation_is_json_serializable():
    json.dumps(sector_rotation(sector_provider()))


# ----------------------------------------------------------------------
# full x-ray
# ----------------------------------------------------------------------
def test_market_xray_posture_risk_on_when_all_bullish():
    bars = {t: uptrend_bars() for t in config.WATCHLIST}
    bars["SPY"] = make_daily([300.0 + 0.15 * i for i in range(260)])
    for ticker in config.SECTOR_ETFS:
        bars.setdefault(ticker, make_daily([100.0 + 0.05 * i for i in range(260)]))
    result = market_xray(FakeProvider(bars))
    assert result["read"]["posture"] == "risk_on"
    assert result["read"]["bullish_share_pct"] == 100.0
    assert result["read"]["pct_above_200dma"] == 100.0
    assert len(result["read"]["leading_sectors"]) == 3
    json.dumps(result)
