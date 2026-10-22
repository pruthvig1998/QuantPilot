"""Liquidity board: scores every watchlist name bullish to bearish.

Score = options OI bias + options volume bias + price momentum +
relative volume, each normalized to [-1, +1] and blended by the weights
in config. Talks only to the MarketDataProvider interface, so it runs
identically on the Yahoo and Zetaris backends.
"""
from .board import build_board, chain_bias, score_symbol

__all__ = ["build_board", "chain_bias", "score_symbol"]
