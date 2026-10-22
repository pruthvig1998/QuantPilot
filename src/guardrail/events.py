"""IV / event-risk guard (build plan module 6).

Buying premium into a scheduled event is how weekly options die:
earnings, an FOMC decision, a CPI print - the event lands, IV
collapses, and the contract bleeds out even if the direction call
was right. This guard answers one question per underlying: is the
implied-volatility price of this trade elevated INTO an event
inside the holding window?

Inputs it needs: the underlying's current IV, its 52-week IV range
(rank = where current IV sits inside that range, 0-100), and its
next earnings date. Data honesty, by design:

- Current IV can be read off the option chain (nearest-the-money
  contract) through the provider - assess_from_provider() does that.
- The MarketDataProvider interface has NO IV history and NO earnings
  calendar, and Yahoo's public endpoints behind it do not offer
  either. So those two inputs are optional parameters, and when they
  are absent the affected checks report passed=None ("unknown")
  rather than inventing a rank or a date. A later data source can
  fill them in without changing the check logic.
- Market-wide events (FOMC / CPI / NFP) come from the static dated
  list in config (MARKET_EVENTS, sourced from the Federal Reserve
  and BLS schedules), so that check always computes.

Same checks contract as the probability guardrail: a list of
{check, passed, detail} with passed True / False / None (unknown).
red_flag is True only for the crush-risk combination: IV rank above
IV_RED_FLAG_PERCENTILE (config, 70) with an event inside the window.

Pure functions over provider data and artifacts: no I/O, no LLM.
US markets only.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Union

from .. import config
from ..data.provider import MarketDataProvider

DateLike = Union[date, datetime, str, int, float]


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _as_date(value: Optional[DateLike]) -> Optional[date]:
    """Normalize date / datetime / ISO string / epoch to a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date()
    return date.fromisoformat(str(value)[:10])


def _check(name: str, passed: Optional[bool], detail: str) -> Dict:
    return {"check": name, "passed": passed, "detail": detail}


def iv_rank(
    current_iv: Optional[float],
    iv_low_52w: Optional[float],
    iv_high_52w: Optional[float],
) -> Optional[float]:
    """Where current IV sits in its 52-week range, 0-100 percentile.

    None when any input is missing or the range is degenerate - an
    IV rank computed from nothing would be invented data.
    """
    if current_iv is None or iv_low_52w is None or iv_high_52w is None:
        return None
    if iv_high_52w <= iv_low_52w:
        return None
    rank = (float(current_iv) - float(iv_low_52w)) / (
        float(iv_high_52w) - float(iv_low_52w)
    ) * 100.0
    return round(min(max(rank, 0.0), 100.0), 1)


def events_in_window(
    as_of: date,
    holding_days: int = config.DEFAULT_HOLDING_DAYS,
    events: Optional[List[Dict]] = None,
) -> List[Dict]:
    """Static-list market events landing in [as_of, as_of + holding]."""
    found: List[Dict] = []
    for event in events if events is not None else config.MARKET_EVENTS:
        day = _as_date(event["date"])
        if day is None:
            continue
        delta = (day - as_of).days
        if 0 <= delta <= holding_days:
            found.append({**event, "date": day.isoformat(), "days_away": delta})
    return sorted(found, key=lambda e: e["days_away"])


# ----------------------------------------------------------------------
# per-underlying assessment (pure)
# ----------------------------------------------------------------------
def assess_risk(
    ticker: str,
    as_of: Optional[DateLike] = None,
    holding_days: int = config.DEFAULT_HOLDING_DAYS,
    current_iv: Optional[float] = None,
    iv_low_52w: Optional[float] = None,
    iv_high_52w: Optional[float] = None,
    earnings_date: Optional[DateLike] = None,
    iv_basis: Optional[str] = None,
    earnings_not_applicable: bool = False,
) -> Dict:
    """Run the IV/event checks for one underlying.

    iv_basis labels where the IV range came from (default: a 52-week
    range); earnings_not_applicable marks an index ETF, which has no
    earnings of its own.

    Any input left None is reported as unknown in the checks that
    depend on it - never estimated, never defaulted.
    """
    start = _as_date(as_of) or date.today()
    rank = iv_rank(current_iv, iv_low_52w, iv_high_52w)

    earn_day = _as_date(earnings_date)
    earn_away = (earn_day - start).days if earn_day is not None else None
    earn_in = earn_away is not None and 0 <= earn_away <= holding_days

    market = events_in_window(start, holding_days)
    market_in = len(market) > 0
    any_event_in = earn_in or market_in

    checks: List[Dict] = []
    # 1. IV rank availability
    if rank is None:
        checks.append(_check(
            "iv_rank_known", None,
            "unknown - 52-week IV range unavailable, so no IV rank can be computed",
        ))
    else:
        checks.append(_check(
            "iv_rank_known", True,
            f"IV rank {rank:.0f} (IV {float(current_iv) * 100:.1f}% vs "
            f"{iv_basis or '52-week'} range "
            f"{float(iv_low_52w) * 100:.1f}-{float(iv_high_52w) * 100:.1f}%)",
        ))
    # 2. Is IV itself elevated?
    if rank is None:
        checks.append(_check(
            "iv_elevated", None,
            "unknown - no IV rank, so elevation cannot be judged",
        ))
    else:
        checks.append(_check(
            "iv_elevated",
            rank <= config.IV_RED_FLAG_PERCENTILE,
            (
                f"IV rank {rank:.0f} - above the {config.IV_RED_FLAG_PERCENTILE:.0f} "
                "red-flag line"
                if rank > config.IV_RED_FLAG_PERCENTILE
                else f"IV rank {rank:.0f} - at or below the "
                f"{config.IV_RED_FLAG_PERCENTILE:.0f} red-flag line"
            ),
        ))
    # 3. Earnings inside the holding window?
    if earn_away is None and earnings_not_applicable:
        checks.append(_check(
            "earnings_in_window", True,
            f"not applicable - {ticker} is an index ETF with no earnings of "
            "its own (constituent earnings are not scored)",
        ))
    elif earn_away is None:
        checks.append(_check(
            "earnings_in_window", None,
            "unknown - earnings date unavailable from the data provider",
        ))
    elif earn_in:
        checks.append(_check(
            "earnings_in_window", False,
            f"earnings on {earn_day.isoformat()}, {earn_away} day(s) away, "
            f"inside the {holding_days}-day holding window",
        ))
    else:
        checks.append(_check(
            "earnings_in_window", True,
            f"earnings on {earn_day.isoformat()} is {earn_away} day(s) away, "
            f"outside the {holding_days}-day holding window",
        ))
    # 4. Market-wide event inside the window? (static list: always known)
    if market_in:
        names = ", ".join(
            f"{e['type']} {e['date']} ({e['days_away']}d)" for e in market
        )
        checks.append(_check(
            "market_event_in_window", False,
            f"market event(s) inside the {holding_days}-day window: {names}",
        ))
    else:
        checks.append(_check(
            "market_event_in_window", True,
            f"no FOMC / CPI / NFP release inside the {holding_days}-day window",
        ))
    # 5. The crush-risk gate: elevated IV into an event.
    if rank is None:
        crush_passed: Optional[bool] = None
        crush_detail = "unknown - no IV rank, so crush risk cannot be judged"
    elif rank <= config.IV_RED_FLAG_PERCENTILE:
        crush_passed = True
        crush_detail = f"IV rank {rank:.0f} is not elevated - no crush-risk flag"
    elif any_event_in:
        crush_passed = False
        which = "earnings" if earn_in else "a market event"
        crush_detail = (
            f"IV rank {rank:.0f} into {which} inside the window - "
            "premium is priced for the event; crush risk"
        )
    elif earn_away is not None or earnings_not_applicable:
        crush_passed = True
        crush_detail = (
            f"IV rank {rank:.0f} is elevated but no event lands inside "
            "the window"
        )
    else:
        crush_passed = None
        crush_detail = (
            f"unknown - IV rank {rank:.0f} is elevated and no market event "
            "is in the window, but the earnings date is unavailable"
        )
    checks.append(_check("event_crush_risk", crush_passed, crush_detail))

    red_flag = crush_passed is False
    one_liner = _one_liner(ticker, rank, earn_away, earn_in, market, red_flag)
    return {
        "ticker": ticker,
        "as_of": start.isoformat(),
        "holding_days": holding_days,
        "iv": {
            "current": float(current_iv) if current_iv is not None else None,
            "low_52w": float(iv_low_52w) if iv_low_52w is not None else None,
            "high_52w": float(iv_high_52w) if iv_high_52w is not None else None,
            "rank_pct": rank,
            "basis": (iv_basis or "52-week") if rank is not None else None,
        },
        "earnings": {
            "date": earn_day.isoformat() if earn_day is not None else None,
            "days_away": earn_away,
            "in_window": earn_in if earn_away is not None else None,
            "not_applicable": bool(earnings_not_applicable and earn_away is None),
        },
        "market_events_in_window": market,
        "checks": checks,
        "red_flag": red_flag,
        "one_liner": one_liner,
    }


def _one_liner(
    ticker: str,
    rank: Optional[float],
    earn_away: Optional[int],
    earn_in: bool,
    market: List[Dict],
    red_flag: bool,
) -> str:
    """The plan's one line per pick, built only from what is known."""
    if rank is None:
        return (
            f"{ticker}: IV rank unknown - 52-week IV history unavailable; "
            "event risk cannot be scored"
        )
    base = f"{ticker}: IV rank {rank:.0f}"
    if red_flag and earn_in:
        return f"{base}, earnings in {earn_away} days - crush risk."
    if red_flag and market:
        first = market[0]
        return (
            f"{base}, {first['type']} in {first['days_away']} days - crush risk."
        )
    if earn_in:
        return f"{base}, earnings in {earn_away} days (IV not elevated)."
    if earn_away is not None:
        return f"{base}, no earnings inside the holding window."
    return f"{base}, earnings date unknown - treat event risk as unscored."


# ----------------------------------------------------------------------
# provider-backed wrapper
# ----------------------------------------------------------------------
def nearest_money_iv(chain: Dict, spot: float) -> Optional[float]:
    """IV of the contract closest to spot across both chain sides."""
    best_iv: Optional[float] = None
    best_dist: Optional[float] = None
    for side in ("calls", "puts"):
        for contract in chain.get(side, []):
            iv = contract.get("impliedVolatility")
            strike = contract.get("strike")
            # Yahoo prints placeholder IVs (0 or ~1e-5) on stale quotes;
            # those are missing data, not a real volatility.
            if iv is None or strike is None or float(iv) < config.MIN_VALID_IV:
                continue
            dist = abs(float(strike) - spot)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_iv = float(iv)
    return best_iv


def assess_from_provider(
    ticker: str,
    provider: MarketDataProvider,
    as_of: Optional[DateLike] = None,
    holding_days: int = config.DEFAULT_HOLDING_DAYS,
) -> Dict:
    """Assess one ticker with whatever the provider can supply.

    Current IV comes off the front chain (nearest-the-money contract).
    The 52-week IV range and the earnings date stay None: neither
    exists behind the MarketDataProvider interface, so the dependent
    checks honestly report unknown until a source for them lands.
    """
    quote = provider.get_quote(ticker)
    spot = float(quote["price"])
    chain = provider.get_option_chain(ticker)
    current_iv = nearest_money_iv(chain, spot)
    result = assess_risk(
        ticker,
        as_of=as_of,
        holding_days=holding_days,
        current_iv=current_iv,
    )
    result["spot"] = spot
    return result
