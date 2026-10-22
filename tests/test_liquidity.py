"""Tests for the liquidity board. Synthetic data via a fake provider."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.data.provider import MarketDataProvider
from src.liquidity import build_board, chain_bias, score_symbol


def make_daily(closes, volumes=None) -> pd.DataFrame:
    """Daily OHLCV from a close series; volume flat unless overridden."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    volume = (
        np.full(n, 1_000_000.0)
        if volumes is None
        else np.asarray(volumes, dtype=float)
    )
    idx = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": volume,
        },
        index=idx,
    )


def make_chain(calls, puts) -> dict:
    """calls/puts: lists of (strike, openInterest, volume) tuples."""

    def _mk(rows, kind):
        return [
            {
                "contractSymbol": f"T{kind}{i}",
                "strike": float(strike),
                "bid": 1.0,
                "ask": 1.1,
                "lastPrice": 1.05,
                "volume": int(vol),
                "openInterest": int(oi),
                "impliedVolatility": 0.3,
                "inTheMoney": False,
            }
            for i, (strike, oi, vol) in enumerate(rows)
        ]

    return {"expiration": 1792108800, "calls": _mk(calls, "C"), "puts": _mk(puts, "P")}


class FakeProvider(MarketDataProvider):
    """Canned provider: quotes/bars/chains keyed by ticker."""

    def __init__(self, quotes, bars, chains, failing=()):
        self._quotes = quotes
        self._bars = bars
        self._chains = chains
        self._failing = set(failing)

    def get_quote(self, ticker):
        if ticker in self._failing:
            raise ValueError(f"no data for {ticker}")
        return self._quotes[ticker]

    def get_bars(self, ticker, interval="1d", period="2y"):
        return self._bars[ticker]

    def get_expirations(self, ticker):
        return [1792108800]

    def get_option_chain(self, ticker, expiration=None):
        return self._chains[ticker]


def bullish_setup():
    closes = [100.0] * 55 + [100.0, 101.0, 102.0, 103.0, 105.0]
    volumes = [1_000_000.0] * 59 + [4_000_000.0]
    quote = {"price": 105.0, "change_pct": 1.9}
    chain = make_chain(
        calls=[(100.0, 6000, 3000), (105.0, 3000, 2000)],
        puts=[(100.0, 700, 300), (105.0, 300, 200)],
    )
    return quote, make_daily(closes, volumes), chain


def bearish_setup():
    closes = [105.0] * 55 + [105.0, 104.0, 103.0, 102.0, 100.0]
    volumes = [1_000_000.0] * 59 + [4_000_000.0]
    quote = {"price": 100.0, "change_pct": -1.9}
    chain = make_chain(
        calls=[(100.0, 300, 200), (105.0, 700, 300)],
        puts=[(100.0, 6000, 3000), (95.0, 3000, 2000)],
    )
    return quote, make_daily(closes, volumes), chain


def choppy_setup():
    closes = [100.0] * 60
    quote = {"price": 100.0, "change_pct": 0.05}
    chain = make_chain(
        calls=[(100.0, 2000, 1000)],
        puts=[(100.0, 2000, 1000)],
    )
    return quote, make_daily(closes), chain


def three_name_provider():
    data = {
        "BULL": bullish_setup(),
        "BEAR": bearish_setup(),
        "CHOP": choppy_setup(),
    }
    return FakeProvider(
        quotes={t: d[0] for t, d in data.items()},
        bars={t: d[1] for t, d in data.items()},
        chains={t: d[2] for t, d in data.items()},
    )


# ----------------------------------------------------------------------
# chain bias
# ----------------------------------------------------------------------
def test_chain_bias_call_heavy_is_positive():
    chain = make_chain(
        calls=[(100.0, 400, 300)],
        puts=[(100.0, 100, 50)],
    )
    bias = chain_bias(chain, price=100.0)
    assert bias["oi_bias"] == pytest.approx(0.6)
    assert bias["volume_bias"] == pytest.approx(250 / 350)
    assert bias["call_oi"] == 400
    assert bias["put_oi"] == 100


def test_chain_bias_ignores_far_strikes():
    chain = make_chain(
        calls=[(100.0, 100, 100), (200.0, 999_999, 999_999)],
        puts=[(100.0, 100, 100), (20.0, 999_999, 999_999)],
    )
    bias = chain_bias(chain, price=100.0)
    assert bias["call_oi"] == 100  # the 200-strike lottery tickets excluded
    assert bias["oi_bias"] == 0.0


def test_chain_bias_empty_chain_is_unknown_not_zero():
    # No data in the band is missing data, not a balanced book.
    bias = chain_bias({"calls": [], "puts": []}, price=100.0)
    assert bias["oi_bias"] is None
    assert bias["volume_bias"] is None


def test_zero_oi_feed_drops_out_and_weights_renormalize():
    """Reference numbers, computed by hand:
    volume bias (5000 - 500) / 5500 = 0.818182
    momentum tanh((0.6 x 0.05 + 0.4 x 0.019) / 0.03) = 0.849216
    relative volume 4.0x -> full intensity, signed up = +1.0
    OI all zero -> unknown, so the blend is over 0.70 of the weight:
    100 x (0.25 x 0.818182 + 0.25 x 0.849216 + 0.20 x 1.0) / 0.70 = 88.12
    (the old code read OI as a neutral 0.0 and reported 61.68)."""
    quote, daily, _ = bullish_setup()
    chain = make_chain(
        calls=[(100.0, 0, 3000), (105.0, 0, 2000)],
        puts=[(100.0, 0, 300), (105.0, 0, 200)],
    )
    provider = FakeProvider({"AAA": quote}, {"AAA": daily}, {"AAA": chain})
    row = score_symbol("AAA", provider)
    assert row["components"]["options_oi"] is None
    assert row["unknown_components"] == ["options_oi"]
    assert row["weight_coverage"] == 0.7
    assert row["score"] == 88.12


def test_unknown_day_change_uses_5d_drift_only():
    quote, daily, chain = bullish_setup()
    quote = {"price": 105.0, "change_pct": None}
    provider = FakeProvider({"AAA": quote}, {"AAA": daily}, {"AAA": chain})
    row = score_symbol("AAA", provider)
    # momentum = tanh(0.05 / 0.03) = 0.931109, not a blend with a fake 0%
    assert row["components"]["momentum"] == 0.9311
    assert row["inputs"]["change_pct"] is None


# ----------------------------------------------------------------------
# per-symbol scores
# ----------------------------------------------------------------------
def test_score_symbol_bullish():
    provider = three_name_provider()
    row = score_symbol("BULL", provider)
    assert row["direction"] == "bullish"
    assert row["score"] > 50
    assert row["components"]["options_oi"] > 0
    assert row["components"]["momentum"] > 0
    assert row["components"]["relative_volume"] > 0


def test_score_symbol_bearish():
    provider = three_name_provider()
    row = score_symbol("BEAR", provider)
    assert row["direction"] == "bearish"
    assert row["score"] < -50
    assert row["components"]["options_oi"] < 0
    assert row["components"]["momentum"] < 0


def test_score_symbol_choppy_near_zero():
    provider = three_name_provider()
    row = score_symbol("CHOP", provider)
    assert row["direction"] == "choppy"
    assert abs(row["score"]) < 2.0


# ----------------------------------------------------------------------
# the board
# ----------------------------------------------------------------------
def test_build_board_ranks_bullish_top_bearish_bottom():
    provider = three_name_provider()
    result = build_board(provider, tickers=["BEAR", "CHOP", "BULL"])
    board = result["board"]
    assert [r["ticker"] for r in board] == ["BULL", "CHOP", "BEAR"]
    assert [r["rank"] for r in board] == [1, 2, 3]
    assert result["count"] == 3
    assert result["errors"] == []
    scores = [r["score"] for r in board]
    assert scores == sorted(scores, reverse=True)


def test_build_board_is_json_serializable():
    provider = three_name_provider()
    result = build_board(provider, tickers=["BULL", "BEAR", "CHOP"])
    json.dumps(result)  # raises if any numpy/pandas type leaked in


def test_build_board_one_bad_name_goes_to_errors():
    data = {"BULL": bullish_setup()}
    provider = FakeProvider(
        quotes={t: d[0] for t, d in data.items()},
        bars={t: d[1] for t, d in data.items()},
        chains={t: d[2] for t, d in data.items()},
        failing=("BAD",),
    )
    result = build_board(provider, tickers=["BULL", "BAD"])
    assert [r["ticker"] for r in result["board"]] == ["BULL"]
    assert result["count"] == 1
    assert result["errors"][0]["ticker"] == "BAD"


def test_caching_provider_serves_repeats_from_memory():
    from src.data.cache import CachingProvider

    quote, daily, chain = bullish_setup()
    calls = []

    class Counting(FakeProvider):
        def get_bars(self, ticker, interval="1d", period="2y"):
            calls.append((ticker, interval, period))
            return super().get_bars(ticker, interval, period)

    cached = CachingProvider(Counting({"AAA": quote}, {"AAA": daily}, {"AAA": chain}))
    first = score_symbol("AAA", cached)
    second = score_symbol("AAA", cached)
    assert first == second
    # one fetch per (interval, period), then the cache
    assert calls == [("AAA", "1d", "2y"), ("AAA", "5m", "5d")]
    assert cached.stats()["hits"] >= 1


def _five_min_bars(prior_sessions, today_bars, prior_vol=1000.0, today_vol=1500.0):
    """Regular-session 5m bars (09:30 ET start = 13:30 UTC in late Oct)."""
    import pandas as pd

    stamps, vols = [], []
    for day in range(prior_sessions):
        start = pd.Timestamp(f"2026-10-{15 + day} 13:30", tz="UTC")
        for i in range(78):  # full session, last bar 15:55 ET
            stamps.append(start + pd.Timedelta(minutes=5 * i))
            vols.append(prior_vol)
    start = pd.Timestamp("2026-10-22 13:30", tz="UTC")
    for i in range(today_bars):
        stamps.append(start + pd.Timedelta(minutes=5 * i))
        vols.append(today_vol)
    n = len(stamps)
    return pd.DataFrame({"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n,
                         "close": [1.0] * n, "volume": vols},
                        index=pd.DatetimeIndex(stamps))


def test_intraday_relative_volume_same_time_of_day_reference():
    """Reference by hand: 12 bars today (09:30-10:25, bar ends 10:30)
    at 1,500 = 18,000; each of 4 prior sessions to the same time:
    12 x 1,000 = 12,000. Relative volume 18,000 / 12,000 = 1.50 - where
    the daily method would compare 18,000 with a 78,000 full day (0.23)."""
    from src.indicators.engine import intraday_relative_volume

    got = intraday_relative_volume(_five_min_bars(4, 12))
    assert got["relative_volume"] == 1.5
    assert got["sessions"] == 4
    assert got["basis"] == "same-time-of-day to 10:30 ET vs 4 prior sessions"


def test_intraday_relative_volume_defers_to_daily_when_session_complete():
    from src.indicators.engine import intraday_relative_volume

    assert intraday_relative_volume(_five_min_bars(4, 78)) is None   # closed
    assert intraday_relative_volume(make_daily([100.0] * 30)) is None  # not intraday
    assert intraday_relative_volume(_five_min_bars(0, 12)) is None   # no history
