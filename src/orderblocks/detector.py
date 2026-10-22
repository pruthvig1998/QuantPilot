"""Order block detector (build plan module 2).

Three things come out of one pass over the bars:

1. Order blocks. A bullish order block is the last DOWN candle before an
   impulsive leg up: within the next `impulse_bars` bars some close breaks
   above that candle's high with at least `impulse_pct` total displacement
   from the candle's close. The zone is the origin candle's full range
   (low to high). Bearish blocks mirror this (last UP candle before a leg
   down). When several origin candles feed the same break, only the last
   one before the break is kept - that is the zone price left from.
   A block is "mitigated" once a later close trades through the far side
   of its zone; unmitigated blocks are the ones still worth trading.

2. Liquidity pools. Equal highs and equal lows - swing points that repeat
   within `tolerance` of each other. Stops cluster just beyond them, so
   price hunts them; they are the natural targets on a trade card.

3. Support / resistance. Nearest swing lows below price (support) and
   swing highs above price (resistance), closest first.

Everything is a pure function of the bars DataFrame (columns open, high,
low, close, volume; DatetimeIndex), and every number that comes out is a
plain float/int/str so the result is JSON-serializable as-is.

US markets only.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from .. import config


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _ts(df: pd.DataFrame, i: int):
    """Bar timestamp as an ISO string when the index carries one."""
    idx = df.index[i]
    return idx.isoformat() if hasattr(idx, "isoformat") else int(i)


def _swing_points(
    df: pd.DataFrame, window: int = config.OB_SWING_WINDOW
) -> Dict[str, List[Dict]]:
    """Strict local extrema: a swing high beats every high within
    +/-window bars, a swing low undercuts every low in the same span."""
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    out: Dict[str, List[Dict]] = {"highs": [], "lows": []}
    for i in range(window, len(df) - window):
        span_h = highs[i - window : i + window + 1]
        span_l = lows[i - window : i + window + 1]
        if highs[i] == span_h.max() and (span_h == highs[i]).sum() == 1:
            out["highs"].append(
                {"index": i, "price": float(highs[i]), "timestamp": _ts(df, i)}
            )
        if lows[i] == span_l.min() and (span_l == lows[i]).sum() == 1:
            out["lows"].append(
                {"index": i, "price": float(lows[i]), "timestamp": _ts(df, i)}
            )
    return out


# ----------------------------------------------------------------------
# order blocks
# ----------------------------------------------------------------------
def detect_order_blocks(
    df: pd.DataFrame,
    impulse_pct: float = config.OB_IMPULSE_PCT,
    impulse_bars: int = config.OB_IMPULSE_BARS,
) -> List[Dict]:
    """Find bullish and bearish order blocks in intraday bars."""
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)

    # break bar -> origin index, one block per break (last origin wins)
    found: Dict[int, Dict] = {}
    for i in range(n):
        bearish_candle = closes[i] < opens[i]
        bullish_candle = closes[i] > opens[i]
        if not (bearish_candle or bullish_candle):
            continue  # doji: no direction, cannot originate a block
        for j in range(i + 1, min(i + 1 + impulse_bars, n)):
            if bearish_candle:
                displaced = (closes[j] - closes[i]) / closes[i]
                if closes[j] > highs[i] and displaced >= impulse_pct:
                    found[j] = _block(df, "bullish", i, j, displaced, closes)
                    break
            else:
                displaced = (closes[i] - closes[j]) / closes[i]
                if closes[j] < lows[i] and displaced >= impulse_pct:
                    found[j] = _block(df, "bearish", i, j, displaced, closes)
                    break
    return [found[j] for j in sorted(found)]


def _block(
    df: pd.DataFrame,
    kind: str,
    origin: int,
    break_bar: int,
    displacement: float,
    closes,
) -> Dict:
    top = float(df["high"].iloc[origin])
    bottom = float(df["low"].iloc[origin])
    # Mitigated once a close after the break trades through the far side
    after = closes[break_bar + 1 :]
    if kind == "bullish":
        mitigated = bool((after < bottom).any()) if len(after) else False
    else:
        mitigated = bool((after > top).any()) if len(after) else False
    return {
        "type": kind,
        "origin_index": int(origin),
        "timestamp": _ts(df, origin),
        "top": top,
        "bottom": bottom,
        "midpoint": round((top + bottom) / 2, 4),
        "break_index": int(break_bar),
        "displacement_pct": round(float(displacement) * 100, 2),
        "mitigated": mitigated,
    }


# ----------------------------------------------------------------------
# liquidity pools
# ----------------------------------------------------------------------
def find_liquidity_pools(
    df: pd.DataFrame,
    tolerance: float = config.POOL_TOLERANCE,
    min_touches: int = 2,
) -> List[Dict]:
    """Equal highs / equal lows: repeated swing points at one level."""
    swings = _swing_points(df)
    pools: List[Dict] = []
    for kind, key in (("equal_highs", "highs"), ("equal_lows", "lows")):
        points = sorted(swings[key], key=lambda p: p["price"])
        clusters: List[List[Dict]] = []
        for point in points:
            if clusters and abs(
                point["price"] - clusters[-1][-1]["price"]
            ) <= tolerance * point["price"]:
                clusters[-1].append(point)
            else:
                clusters.append([point])
        for cluster in clusters:
            if len(cluster) >= min_touches:
                level = sum(p["price"] for p in cluster) / len(cluster)
                pools.append(
                    {
                        "type": kind,
                        "level": round(float(level), 4),
                        "touches": len(cluster),
                        "indices": [int(p["index"]) for p in cluster],
                    }
                )
    return sorted(pools, key=lambda p: p["level"])


# ----------------------------------------------------------------------
# support / resistance
# ----------------------------------------------------------------------
def support_resistance(df: pd.DataFrame, max_levels: int = 5) -> Dict:
    """Nearest swing levels around the last close, closest first."""
    price = float(df["close"].iloc[-1])
    swings = _swing_points(df)

    def _levels(points: List[Dict], keep, reverse: bool) -> List[float]:
        prices = sorted(
            {round(p["price"], 4) for p in points if keep(p["price"])},
            reverse=reverse,
        )
        return [float(p) for p in prices[:max_levels]]

    return {
        "price": price,
        "resistance": _levels(
            swings["highs"], lambda p: p > price, reverse=False
        ),
        "support": _levels(
            swings["lows"], lambda p: p < price, reverse=True
        ),
    }


# ----------------------------------------------------------------------
# full pass
# ----------------------------------------------------------------------
def analyze(df: pd.DataFrame) -> Dict:
    """One-call summary for the charts and trade cards."""
    return {
        "bars": int(len(df)),
        "last_price": float(df["close"].iloc[-1]),
        "order_blocks": detect_order_blocks(df),
        "liquidity_pools": find_liquidity_pools(df),
        "support_resistance": support_resistance(df),
    }
