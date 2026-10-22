"""Data provider interface.

Every market-data source (Yahoo Finance now, Zetaris AI Data Harness from
Oct 22) implements MarketDataProvider. The rest of QuantPilot only talks to
this interface, so swapping the backend is a one-line config change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import pandas as pd


class MarketDataProvider(ABC):
    """Abstract market-data source. US equities and options only."""

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """Latest quote snapshot: price, change, volume, day range, etc."""

    @abstractmethod
    def get_bars(
        self,
        ticker: str,
        interval: str = "1d",
        period: str = "2y",
    ) -> pd.DataFrame:
        """OHLCV bars. Columns: open, high, low, close, volume.

        interval: 1m, 5m, 15m, 1d, 1wk. period: 1d, 5d, 1mo, 6mo, 1y, 2y, 5y.
        """

    @abstractmethod
    def get_expirations(self, ticker: str) -> List[int]:
        """Option expiration dates as epoch seconds, ascending."""

    @abstractmethod
    def get_option_chain(
        self,
        ticker: str,
        expiration: Optional[int] = None,
    ) -> dict:
        """Full chain for one expiration: {"calls": [...], "puts": [...]}.

        Each contract carries: contractSymbol, strike, bid, ask, lastPrice,
        volume, openInterest, impliedVolatility, inTheMoney.
        expiration=None returns the front (nearest) expiry.
        """
