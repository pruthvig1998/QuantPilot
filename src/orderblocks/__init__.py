"""Order block detection: origin zones, liquidity pools, support/resistance.

Pure functions over OHLCV bars (intraday for the blocks, any timeframe
for pools and levels). Output is JSON-serializable and feeds the order
block charts (module 2) and the trade cards, where a bullish zone is the
entry and the next liquidity pool up is the target.
"""
from .detector import (
    analyze,
    detect_order_blocks,
    find_liquidity_pools,
    support_resistance,
)

__all__ = [
    "analyze",
    "detect_order_blocks",
    "find_liquidity_pools",
    "support_resistance",
]
