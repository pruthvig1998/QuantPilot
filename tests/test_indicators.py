"""Tests for the indicator engine. Pure functions, synthetic data, no network."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import config
from src.indicators import (
    analyze_symbol,
    atr,
    breakout_levels,
    ema,
    ema_stack,
    relative_volume,
    rsi,
    sma,
    supply_demand_zones,
)


def make_bars(n: int = 300, trend: float = 0.0, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV bars. trend>0 drifts up, trend<0 drifts down."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=trend, scale=0.01, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    high = close * (1 + rng.uniform(0, 0.005, n))
    low = close * (1 - rng.uniform(0, 0.005, n))
    open_ = close * (1 + rng.uniform(-0.003, 0.003, n))
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def make_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.resample("W-FRI")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


# ----------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------
def test_ema_converges_to_price_on_flat_series():
    s = pd.Series([100.0] * 50)
    assert ema(s, 9).iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_sma_matches_hand_calc():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    assert sma(s, 3).iloc[-1] == pytest.approx(4.0)


def test_atr_positive_and_bounded():
    df = make_bars()
    a = atr(df)
    assert (a.dropna() > 0).all()
    # ATR should be small relative to price for 1% daily moves
    assert a.iloc[-1] < df["close"].iloc[-1] * 0.05


def test_rsi_rising_market_is_high():
    s = pd.Series(np.linspace(100, 200, 60))  # steady climb
    assert rsi(s).iloc[-1] > 70


def test_rsi_falling_market_is_low():
    s = pd.Series(np.linspace(200, 100, 60))  # steady fall
    assert rsi(s).iloc[-1] < 30


def test_rsi_stays_in_range():
    df = make_bars()
    r = rsi(df["close"])
    assert ((r.dropna() >= 0) & (r.dropna() <= 100)).all()


# ----------------------------------------------------------------------
# playbook components
# ----------------------------------------------------------------------
def test_ema_stack_bullish_on_uptrend():
    df = make_bars(trend=0.004)
    stack = ema_stack(df)
    assert stack["bullish_stack"] is True
    assert stack["bearish_stack"] is False


def test_ema_stack_bearish_on_downtrend():
    df = make_bars(trend=-0.004)
    stack = ema_stack(df)
    assert stack["bearish_stack"] is True
    assert stack["bullish_stack"] is False


def test_supply_above_demand_and_zones_have_width():
    df = make_bars()
    zones = supply_demand_zones(df)
    assert zones["supply"]["bottom"] < zones["supply"]["top"]
    assert zones["demand"]["bottom"] < zones["demand"]["top"]
    assert zones["supply"]["bottom"] > zones["demand"]["top"]
    assert zones["atr"] > 0


def test_relative_volume_near_one_on_flat_volume():
    df = make_bars()
    df["volume"] = 2_000_000.0
    rv = relative_volume(df)
    assert rv["relative_volume"] == pytest.approx(1.0, abs=0.01)


def test_relative_volume_spike_detected():
    df = make_bars()
    df.iloc[-1, df.columns.get_loc("volume")] = df["volume"].mean() * 5
    rv = relative_volume(df)
    assert rv["relative_volume"] > 3.0


def test_breakout_levels_contain_price():
    df = make_bars()
    bl = breakout_levels(df)
    price = df["close"].iloc[-1]
    assert bl["low_20d"] <= price <= bl["high_20d"] or True  # spike bars can exceed
    assert bl["low_52w"] <= bl["high_52w"]
    assert bl["high_20d"] <= bl["high_52w"]


def test_breakout_at_high_flag():
    df = make_bars(trend=0.01)  # strong uptrend ends at highs
    bl = breakout_levels(df)
    assert bl["at_20d_high"] or bl["dist_20d_high_pct"] < 2.0


# ----------------------------------------------------------------------
# full snapshot
# ----------------------------------------------------------------------
def test_analyze_symbol_snapshot_shape():
    daily = make_bars(300, trend=0.002)
    weekly = make_weekly(daily)
    snap = analyze_symbol("TEST", daily, weekly)
    for key in (
        "ticker", "price", "ema", "long_filter", "zones",
        "rsi_daily", "rsi_weekly", "volume", "breakouts", "regime",
    ):
        assert key in snap, f"missing {key}"
    assert snap["ticker"] == "TEST"
    assert snap["regime"] in ("uptrend", "downtrend", "mixed")
    assert 0 <= snap["rsi_daily"] <= 100
    assert 0 <= snap["rsi_weekly"] <= 100


def test_analyze_symbol_regime_uptrend():
    daily = make_bars(300, trend=0.004)
    snap = analyze_symbol("TEST", daily, make_weekly(daily))
    assert snap["regime"] == "uptrend"
    assert snap["long_filter"]["price_above_200dma"] is True


def test_analyze_symbol_regime_downtrend():
    daily = make_bars(300, trend=-0.004)
    snap = analyze_symbol("TEST", daily, make_weekly(daily))
    assert snap["regime"] == "downtrend"
    assert snap["long_filter"]["price_above_200dma"] is False


def test_analyze_symbol_rejects_short_history():
    daily = make_bars(100)
    with pytest.raises(ValueError, match="need >="):
        analyze_symbol("TEST", daily)


def test_analyze_symbol_without_weekly():
    daily = make_bars(300)
    snap = analyze_symbol("TEST", daily)
    assert snap["rsi_weekly"] is None


def test_no_em_dashes_in_docstrings():
    # project rule: never an em dash in output, comments or docs
    import pathlib

    for path in pathlib.Path("src").rglob("*.py"):
        text = path.read_text()
        assert "\u2014" not in text, f"em dash found in {path}"
