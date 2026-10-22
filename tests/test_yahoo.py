"""Live tests for the Yahoo data provider (hits the real Yahoo Finance API).

These verify the v8 chart API and the v7 options cookie+crumb flow work
from this machine. They need network access and take a few seconds.
"""
from __future__ import annotations

import time

import pytest

from src.data.yahoo import YahooProvider, get_provider
from src.integrations.zetaris import ZetarisProvider

provider = YahooProvider()


def test_get_quote_spy():
    q = provider.get_quote("SPY")
    assert q["ticker"] == "SPY"
    assert q["price"] > 100  # SPY is a ~$700 ETF; sanity floor
    assert q["day_high"] >= q["day_low"] > 0
    assert q["volume"] > 0


def test_get_daily_bars_shape():
    df = provider.get_bars("SPY", interval="1d", period="2y")
    assert len(df) >= 252, f"need 1y+ of daily bars, got {len(df)}"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert (df["high"] >= df["low"]).all()


def test_get_weekly_bars_shape():
    df = provider.get_bars("QQQ", interval="1wk", period="5y")
    assert len(df) >= 100, f"need 2y+ of weekly bars, got {len(df)}"


def test_get_intraday_bars_shape():
    df = provider.get_bars("NVDA", interval="5m", period="5d")
    assert len(df) > 0
    assert (df["close"] > 0).all()


def test_option_expirations_nonempty():
    exps = provider.get_expirations("SPY")
    assert len(exps) >= 4, f"expected several expiries, got {len(exps)}"
    assert exps == sorted(exps)
    # first expiry is in the future (allow a small clock skew margin)
    assert exps[0] > time.time() - 86400


def test_option_chain_carries_greeks_inputs():
    chain = provider.get_option_chain("SPY")  # front expiry
    assert len(chain["calls"]) > 50, "front SPY expiry should have 50+ calls"
    assert len(chain["puts"]) > 50
    call = chain["calls"][len(chain["calls"]) // 2]
    for field in (
        "contractSymbol", "strike", "bid", "ask",
        "volume", "openInterest", "impliedVolatility",
    ):
        assert field in call, f"missing {field}"
    assert call["strike"] > 0
    # live bid>0 quotes only exist during US market hours; the fields above
    # are what the probability guardrail needs, and they are always present


def test_option_chain_specific_expiry():
    exps = provider.get_expirations("QQQ")
    chain = provider.get_option_chain("QQQ", expiration=exps[1])
    assert chain["expiration"] == exps[1]
    assert len(chain["calls"]) > 0


def test_factory_returns_zetaris_by_default():
    # DATA_PROVIDER flipped to "zetaris" on 2026-10-20 (Zetaris serves the
    # Yahoo data on the Mac); from_env() construction needs no live server.
    p = get_provider()
    assert isinstance(p, ZetarisProvider)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError, match="unknown data provider"):
        get_provider("bloomberg")


def test_zetaris_quote_single_row_falls_back_to_prior_daily_close():
    """Live Oct 22, 10:00 ET: the quote view held only today's row, so
    every quote had previous_close None. The 1d bars view supplies it.
    Reference: price 388.39 vs prior close 386.47 -> +0.4968%."""
    from src.integrations.zetaris import ZetarisProvider

    today_ts = 1792675800  # 2026-10-22 13:30 UTC
    calls = []

    class Stub(ZetarisProvider):
        def run_sql(self, sql, limit=1000):
            calls.append(sql)
            if "_quote" in sql:
                return [["388.39", "388.859", "373.71", str(today_ts),
                         "374.03", "388.85", "373.71", "388.39", "20000000"]]
            assert f"ts < {today_ts - 3600}" in sql and "DESC" in sql
            return [[str(today_ts - 86400), "386.47"]]

    q = Stub(api_key="x").get_quote("TSLA")
    assert q["previous_close"] == 386.47
    assert round(q["change_pct"], 4) == 0.4968
    assert len(calls) == 2
