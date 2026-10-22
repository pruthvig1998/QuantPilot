"""Market X-Ray: market-wide breadth plus sector rotation.

breadth() classifies the watchlist off the indicator engine's
snapshots (200DMA position, EMA stack, RSI zones); sector_rotation()
ranks the 10 US sector ETFs by momentum with relative strength vs SPY.
market_xray() combines both into one posture read. Pure functions of
MarketDataProvider data - no I/O beyond the provider interface.
"""
from .xray import breadth, classify_snapshot, market_xray, rsi_zone, sector_rotation

__all__ = [
    "breadth",
    "classify_snapshot",
    "market_xray",
    "rsi_zone",
    "sector_rotation",
]
