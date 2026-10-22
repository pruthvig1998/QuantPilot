"""Live tests for the Zetaris data provider (queries the local Zetaris).

Zetaris reads Yahoo Finance through the REST tables registered by
sql/yahoo_finance_create.sql. Skipped when Zetaris or the API key is not
available on this machine. Each query re-fetches from Yahoo, so these take
several seconds each.
"""
from __future__ import annotations

import time

import pytest
import requests

from src import config
from src.data.yahoo import get_provider
from src.indicators import analyze_symbol
from src.integrations.zetaris import ZetarisProvider

provider = ZetarisProvider.from_env()


def _zetaris_up() -> bool:
    if not provider.api_key:
        return False
    try:
        return provider.ping()
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _zetaris_up(), reason="local Zetaris not reachable")

QUOTE_KEYS = {
    "ticker", "price", "change", "change_pct", "volume",
    "day_high", "day_low", "open", "previous_close",
}


def test_factory_returns_zetaris_when_configured():
    assert config.DATA_PROVIDER == "zetaris"
    assert isinstance(get_provider(), ZetarisProvider)


def test_daily_bars_spy_through_zetaris():
    df = provider.get_bars("SPY", interval="1d", period="2y")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert str(df.index.tz) == "UTC"
    assert 450 <= len(df) <= 520, f"expected ~500 daily bars, got {len(df)}"
    assert (df["high"] >= df["low"]).all()
    assert (df["close"] > 100).all()  # SPY trades in the hundreds
    assert df.index.is_monotonic_increasing
    # last bar is a recent trading day (allow weekends and holidays)
    assert df.index[-1].timestamp() > time.time() - 5 * 86400


def test_period_trim_and_too_long_period():
    df = provider.get_bars("SPY", interval="1d", period="6mo")
    assert 100 <= len(df) <= 135
    with pytest.raises(ValueError):
        provider.get_bars("SPY", interval="1d", period="5y")


def test_quote_spy_through_zetaris():
    q = provider.get_quote("SPY")
    assert set(q) == QUOTE_KEYS
    assert q["ticker"] == "SPY"
    assert q["price"] > 100
    assert q["day_high"] >= q["day_low"] > 0
    assert q["volume"] > 0
    assert q["previous_close"] and q["previous_close"] > 100


def test_indicator_engine_on_zetaris_fed_data():
    daily = provider.get_bars("SPY", interval="1d", period="2y")
    weekly = provider.get_bars("SPY", interval="1wk", period="5y")
    snap = analyze_symbol("SPY", daily, weekly)
    assert snap["ticker"] == "SPY"
    assert snap["price"] == pytest.approx(float(daily["close"].iloc[-1]))
    assert 0 <= snap["rsi_daily"] <= 100
    assert snap["rsi_weekly"] is not None and 0 <= snap["rsi_weekly"] <= 100


def test_unregistered_ticker_and_options_raise_clearly():
    with pytest.raises(NotImplementedError, match="not registered"):
        provider.get_bars("SPY", interval="15m", period="5d")
    with pytest.raises(NotImplementedError, match="option"):
        provider.get_expirations("SPY")
    with pytest.raises(NotImplementedError, match="option"):
        provider.get_option_chain("SPY")
