"""Tests for the order block detector. Hand-built bars, no network."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from src.orderblocks import (
    analyze,
    detect_order_blocks,
    find_liquidity_pools,
    support_resistance,
)


def make_intraday(rows) -> pd.DataFrame:
    """rows: list of (open, high, low, close) tuples, 5-minute bars."""
    arr = np.asarray(rows, dtype=float)
    idx = pd.date_range(
        "2026-10-22 09:30", periods=len(rows), freq="5min", tz="America/New_York"
    )
    return pd.DataFrame(
        {
            "open": arr[:, 0],
            "high": arr[:, 1],
            "low": arr[:, 2],
            "close": arr[:, 3],
            "volume": np.full(len(rows), 1000.0),
        },
        index=idx,
    )


BULLISH_ROWS = [
    (100.00, 100.05, 99.95, 100.00),  # 0 doji
    (100.00, 100.06, 99.96, 100.02),  # 1 small up
    (100.00, 100.10, 98.90, 99.00),   # 2 origin down candle
    (99.20, 100.60, 99.10, 100.40),   # 3 break above origin high, +1.4%
    (100.40, 101.60, 100.30, 101.50),  # 4 leg continues
    (101.50, 102.10, 101.20, 102.00),  # 5
]

BEARISH_ROWS = [
    (100.00, 100.05, 99.95, 100.00),  # 0 doji
    (100.00, 100.04, 99.94, 99.98),   # 1 small down
    (100.00, 101.10, 99.90, 101.00),  # 2 origin up candle
    (100.80, 100.90, 99.40, 99.60),   # 3 break below origin low, -1.4%
    (99.60, 99.70, 98.40, 98.50),     # 4 leg continues
    (98.50, 98.90, 97.90, 98.00),     # 5
]


# ----------------------------------------------------------------------
# order blocks
# ----------------------------------------------------------------------
def test_bullish_order_block_detected():
    df = make_intraday(BULLISH_ROWS)
    bulls = [b for b in detect_order_blocks(df) if b["type"] == "bullish"]
    assert len(bulls) == 1
    block = bulls[0]
    assert block["origin_index"] == 2
    assert block["top"] == 100.10
    assert block["bottom"] == 98.90
    assert block["break_index"] == 3
    assert block["displacement_pct"] > 1.0
    assert block["mitigated"] is False


def test_bearish_order_block_detected():
    df = make_intraday(BEARISH_ROWS)
    bears = [b for b in detect_order_blocks(df) if b["type"] == "bearish"]
    assert len(bears) == 1
    block = bears[0]
    assert block["origin_index"] == 2
    assert block["top"] == 101.10
    assert block["bottom"] == 99.90
    assert block["break_index"] == 3
    assert block["displacement_pct"] > 1.0
    assert block["mitigated"] is False


def test_last_origin_candle_wins_for_one_break():
    rows = [
        (100.00, 100.05, 99.95, 100.00),  # 0 doji
        (100.02, 100.08, 99.50, 99.60),   # 1 down candle A
        (99.60, 99.70, 99.00, 99.10),     # 2 down candle B (the origin)
        (99.30, 100.90, 99.20, 100.80),   # 3 impulsive break for both
    ]
    blocks = detect_order_blocks(make_intraday(rows))
    assert len(blocks) == 1
    assert blocks[0]["type"] == "bullish"
    assert blocks[0]["origin_index"] == 2
    assert blocks[0]["bottom"] == 99.00


def test_flat_series_has_no_order_blocks():
    rows = [(100.0, 100.2, 99.8, 100.0)] * 10 + [
        (100.0, 100.2, 99.8, 100.05)
    ] * 10
    assert detect_order_blocks(make_intraday(rows)) == []


def test_smooth_ramp_has_no_order_blocks():
    rows = [
        (100.0 + i, 100.6 + i, 99.9 + i, 100.5 + i) for i in range(12)
    ]
    assert detect_order_blocks(make_intraday(rows)) == []


def test_bullish_block_marked_mitigated_after_zone_fails():
    rows = BULLISH_ROWS + [
        (102.00, 102.05, 98.00, 98.50),  # close back through the zone
    ]
    bulls = [
        b
        for b in detect_order_blocks(make_intraday(rows))
        if b["type"] == "bullish" and b["origin_index"] == 2
    ]
    assert len(bulls) == 1
    assert bulls[0]["mitigated"] is True


# ----------------------------------------------------------------------
# liquidity pools + support/resistance
# ----------------------------------------------------------------------
def _pool_frame(high_overrides=None, low_overrides=None, n=20):
    highs = np.full(n, 100.5)
    lows = np.full(n, 99.5)
    for i, v in (high_overrides or {}).items():
        highs[i] = v
    for i, v in (low_overrides or {}).items():
        lows[i] = v
    rows = [
        (100.0, float(highs[i]), float(lows[i]), 100.0) for i in range(n)
    ]
    return make_intraday(rows)


def test_equal_highs_and_lows_form_pools():
    df = _pool_frame(
        high_overrides={3: 110.0, 12: 110.0},
        low_overrides={6: 95.0, 15: 95.0},
    )
    pools = find_liquidity_pools(df)
    by_type = {p["type"]: p for p in pools}
    assert by_type["equal_highs"]["level"] == 110.0
    assert by_type["equal_highs"]["touches"] == 2
    assert by_type["equal_highs"]["indices"] == [3, 12]
    assert by_type["equal_lows"]["level"] == 95.0
    assert by_type["equal_lows"]["touches"] == 2


def test_near_equal_highs_within_tolerance_pool_together():
    df = _pool_frame(high_overrides={3: 110.00, 12: 110.10})
    pools = find_liquidity_pools(df)
    highs = [p for p in pools if p["type"] == "equal_highs"]
    assert len(highs) == 1
    assert highs[0]["touches"] == 2
    assert highs[0]["level"] == 110.05


def test_single_swing_is_not_a_pool():
    df = _pool_frame(high_overrides={3: 110.0}, low_overrides={6: 95.0})
    assert find_liquidity_pools(df) == []


def test_support_resistance_nearest_first():
    df = _pool_frame(
        high_overrides={4: 108.0, 10: 112.0},
        low_overrides={5: 92.0, 14: 96.0},
    )
    sr = support_resistance(df)
    assert sr["price"] == 100.0
    assert sr["resistance"] == [108.0, 112.0]
    assert sr["support"] == [96.0, 92.0]


# ----------------------------------------------------------------------
# full pass
# ----------------------------------------------------------------------
def test_analyze_shape_and_json_serializable():
    result = analyze(make_intraday(BULLISH_ROWS))
    for key in (
        "bars",
        "last_price",
        "order_blocks",
        "liquidity_pools",
        "support_resistance",
    ):
        assert key in result, f"missing {key}"
    assert result["last_price"] == 102.0
    json.dumps(result)  # raises if any numpy/pandas type leaked in
