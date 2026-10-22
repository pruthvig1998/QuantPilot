"""Yahoo Finance data provider.

Uses raw HTTP requests (the yfinance library fails from this VM):
- v8 chart API for quotes and intraday/daily/weekly bars (no auth needed)
- v7 options API with the cookie + crumb flow for full option chains
  carrying open interest, volume, bid/ask and implied volatility

Both flows were validated working from this VM on 2026-10-16.
US markets only.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import requests

from .. import config
from .provider import MarketDataProvider

# Interval -> maximum sensible range for the v8 chart API
_INTERVAL_RANGE = {
    "1m": "5d",
    "5m": "1mo",
    "15m": "3mo",
    "1d": "2y",
    "1wk": "5y",
}


class YahooProvider(MarketDataProvider):
    """MarketDataProvider backed by Yahoo Finance's public APIs."""

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self._session: Optional[requests.Session] = None
        self._crumb: Optional[str] = None

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _chart(self, ticker: str, interval: str, period: str) -> dict:
        url = config.YAHOO_CHART_URL.format(ticker=ticker)
        resp = requests.get(
            url,
            params={"interval": interval, "range": period},
            headers=config.YAHOO_UA,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        result = (payload.get("chart") or {}).get("result")
        if not result:
            error = (payload.get("chart") or {}).get("error") or {}
            raise ValueError(
                f"no chart data for {ticker}: {error.get('description', 'unknown error')}"
            )
        return result[0]

    def _auth_session(self) -> requests.Session:
        """Session with Yahoo cookies and a crumb for the options API."""
        if self._session is not None and self._crumb is not None:
            return self._session
        session = requests.Session()
        session.headers.update(config.YAHOO_UA)
        # Step 1: fetch the consent page to plant the auth cookies
        session.get(config.YAHOO_COOKIE_URL, timeout=self.timeout)
        # Step 2: exchange cookies for a crumb token
        crumb_resp = session.get(config.YAHOO_CRUMB_URL, timeout=self.timeout)
        crumb_resp.raise_for_status()
        self._session = session
        self._crumb = crumb_resp.text.strip()
        if not self._crumb:
            raise RuntimeError("Yahoo returned an empty crumb token")
        return session

    @staticmethod
    def _bars_to_df(result: dict) -> pd.DataFrame:
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators") or {}).get("quote", [{}])[0]
        df = pd.DataFrame(
            {
                "open": quote.get("open", []),
                "high": quote.get("high", []),
                "low": quote.get("low", []),
                "close": quote.get("close", []),
                "volume": quote.get("volume", []),
            },
            index=pd.to_datetime(timestamps, unit="s", utc=True),
        )
        df.index.name = "timestamp"
        return df.dropna(subset=["close"])

    # ------------------------------------------------------------------
    # MarketDataProvider interface
    # ------------------------------------------------------------------
    def get_quote(self, ticker: str) -> dict:
        result = self._chart(ticker, interval="1d", period="5d")
        meta = result.get("meta", {})
        df = self._bars_to_df(result)
        last = df.iloc[-1]
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        price = meta.get("regularMarketPrice") or float(last["close"])
        change = (price - prev_close) if prev_close else 0.0
        return {
            "ticker": ticker,
            "price": float(price),
            "change": float(change),
            "change_pct": float(change / prev_close * 100) if prev_close else 0.0,
            "volume": int(last["volume"] or 0),
            "day_high": float(last["high"]),
            "day_low": float(last["low"]),
            "open": float(last["open"]),
            "previous_close": float(prev_close) if prev_close else None,
        }

    def get_bars(
        self,
        ticker: str,
        interval: str = "1d",
        period: str = "2y",
    ) -> pd.DataFrame:
        period = period or _INTERVAL_RANGE.get(interval, "2y")
        result = self._chart(ticker, interval=interval, period=period)
        return self._bars_to_df(result)

    def get_expirations(self, ticker: str) -> List[int]:
        session = self._auth_session()
        url = config.YAHOO_OPTIONS_URL.format(ticker=ticker)
        resp = session.get(
            url, params={"crumb": self._crumb}, timeout=self.timeout
        )
        resp.raise_for_status()
        payload = resp.json()
        result = (payload.get("optionChain") or {}).get("result")
        if not result:
            raise ValueError(f"no options data for {ticker}")
        return sorted(result[0].get("expirationDates", []))

    def get_option_chain(
        self,
        ticker: str,
        expiration: Optional[int] = None,
    ) -> Dict[str, List[dict]]:
        session = self._auth_session()
        url = config.YAHOO_OPTIONS_URL.format(ticker=ticker)
        params: dict = {"crumb": self._crumb}
        if expiration is not None:
            params["date"] = expiration
        resp = session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = resp.json()
        result = (payload.get("optionChain") or {}).get("result")
        if not result or not result[0].get("options"):
            raise ValueError(
                f"no option chain for {ticker} expiry={expiration}"
            )
        chain = result[0]["options"][0]

        def _clean(contracts: list) -> List[dict]:
            out = []
            for c in contracts:
                out.append(
                    {
                        "contractSymbol": c.get("contractSymbol"),
                        "strike": c.get("strike"),
                        "bid": c.get("bid"),
                        "ask": c.get("ask"),
                        "lastPrice": c.get("lastPrice"),
                        # Missing stays None (unknown), never 0.
                        "volume": c.get("volume"),
                        "openInterest": c.get("openInterest"),
                        "impliedVolatility": c.get("impliedVolatility"),
                        "inTheMoney": bool(c.get("inTheMoney")),
                        "expiration": c.get("expiration"),
                    }
                )
            return out

        return {
            "expiration": chain.get("expirationDate"),
            "calls": _clean(chain.get("calls", [])),
            "puts": _clean(chain.get("puts", [])),
        }

    def get_earnings_date(self, ticker: str) -> Optional[Dict]:
        """Next earnings date from quoteSummary calendarEvents, or None.

        None means "no date published" (index ETFs have none, and Yahoo
        answers 404 for them) - callers report it as unknown, never as
        "no earnings". A two-date entry is Yahoo's estimate window; the
        first date is used and the estimate flag rides along.
        """
        session = self._auth_session()
        url = config.YAHOO_SUMMARY_URL.format(ticker=ticker)
        resp = session.get(
            url,
            params={"modules": "calendarEvents", "crumb": self._crumb},
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        result = (resp.json().get("quoteSummary") or {}).get("result") or []
        earnings = ((result[0] if result else {}).get("calendarEvents") or {}).get(
            "earnings"
        ) or {}
        dates = [d.get("fmt") for d in earnings.get("earningsDate") or [] if d.get("fmt")]
        if not dates:
            return None
        return {
            "date": dates[0],
            "window_end": dates[-1] if len(dates) > 1 else None,
            "estimate": bool(earnings.get("isEarningsDateEstimate")),
            "source": "yahoo quoteSummary calendarEvents",
        }


def get_provider(name: str = config.DATA_PROVIDER) -> MarketDataProvider:
    """Factory: returns the configured provider.

    "zetaris" returns the Zetaris-backed provider from
    src/integrations/zetaris.py, built from .env settings via from_env().
    Everything downstream keeps calling the MarketDataProvider interface
    unchanged.
    """
    if name == "yahoo":
        return YahooProvider()
    if name == "zetaris":
        from ..integrations.zetaris import ZetarisProvider

        # Quotes and bars read Zetaris; option chains and earnings dates
        # are not Zetaris tables yet, so they route to direct Yahoo.
        return ZetarisProvider.from_env(options_provider=YahooProvider())
    raise ValueError(f"unknown data provider: {name}")
