"""Run-scoped caching provider (audit repair, Oct 22: Zetaris latency).

The board, the X-Ray and each packet ask the provider for the same
quote / daily / weekly bars. Through Zetaris every one of those is a
3-15 s live query on the M1 Mac, so one morning run repeated about a
third of its queries. This wrapper memoizes every MarketDataProvider
call for the lifetime of ONE run: the same question in the same run
gets the same answer (which also keeps the board, the X-Ray and the
packets consistent with each other). It is never shared across runs.

Errors are not cached: a failed fetch is retried by the next caller.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from .provider import MarketDataProvider


class CachingProvider(MarketDataProvider):
    def __init__(self, inner: MarketDataProvider) -> None:
        self.inner = inner
        self._memo: Dict[tuple, object] = {}
        self.hits = 0
        self.misses = 0

    def _get(self, key: tuple, fetch):
        if key in self._memo:
            self.hits += 1
            return self._memo[key]
        self.misses += 1
        value = fetch()
        self._memo[key] = value
        return value

    def get_quote(self, ticker: str) -> dict:
        return dict(self._get(("quote", ticker), lambda: self.inner.get_quote(ticker)))

    def get_bars(self, ticker: str, interval: str = "1d", period: str = "2y") -> pd.DataFrame:
        return self._get(
            ("bars", ticker, interval, period),
            lambda: self.inner.get_bars(ticker, interval=interval, period=period),
        ).copy()

    def get_expirations(self, ticker: str) -> List[int]:
        return list(self._get(("exp", ticker), lambda: self.inner.get_expirations(ticker)))

    def get_option_chain(self, ticker: str, expiration: Optional[int] = None) -> Dict:
        return self._get(
            ("chain", ticker, expiration),
            lambda: self.inner.get_option_chain(ticker, expiration=expiration),
        )

    def get_earnings_date(self, ticker: str):
        getter = getattr(self.inner, "get_earnings_date", None)
        if getter is None:
            return None
        return self._get(("earnings", ticker), lambda: getter(ticker))

    def stats(self) -> Dict:
        return {"hits": self.hits, "misses": self.misses,
                "inner": type(self.inner).__name__}
