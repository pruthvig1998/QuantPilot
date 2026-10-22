"""Probability guardrail (build plan module 5).

The cheap-contract finder surfaces cheap weeklies; this guardrail
decides which of them can actually win. For every contract it computes:

- breakeven price and the percent move the underlying needs by expiry
- delta-implied probability of profit (lognormal probability that the
  underlying finishes beyond breakeven)
- daily theta burn in dollars per contract

Ranking rule (locked): only contracts with |delta| >= MIN_DELTA
(config, 0.30) are rankable. Demo line: "not the cheapest contract -
the cheapest contract that can actually win."

Data honesty: the Yahoo chain carries implied volatility but no
Greeks, so delta and theta are computed here with Black-Scholes from
the chain's own IV, spot, strike and time to expiry, using the
assumption constants in config (RISK_FREE_RATE, DIVIDEND_YIELD).
Anything that cannot be computed comes back null, and the check that
depends on it reports passed=None ("unknown") instead of a guess.

Every evaluation carries an explicit checks list of
{check, passed, detail} entries (passed True / False / None for
unknown) so the trade card can show its gate results verbatim - the
explain-why layer never has to re-derive them.

Pure functions over provider data and artifacts: no I/O, no LLM.
The one provider-touching helper is guard_provider_chain(), which
only fetches through the MarketDataProvider interface.

US markets only.
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .. import config
from ..data.provider import MarketDataProvider


# ----------------------------------------------------------------------
# Black-Scholes primitives
# ----------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def black_scholes(
    spot: float,
    strike: float,
    years: float,
    iv: float,
    option_type: str,
    rate: float = config.RISK_FREE_RATE,
    div_yield: float = config.DIVIDEND_YIELD,
) -> Optional[Dict[str, float]]:
    """Delta and theta (per day) for one contract, or None.

    Returns None when the inputs cannot support the math (non-positive
    spot/strike/IV/time). Theta is the standard Black-Scholes theta
    divided by 365: the dollar change in the option's value per calendar
    day, per share. It is negative for a long position - that negative
    is the burn.
    """
    if spot <= 0 or strike <= 0 or iv <= 0 or years <= 0:
        return None
    sqrt_t = math.sqrt(years)
    d1 = (
        math.log(spot / strike)
        + (rate - div_yield + 0.5 * iv * iv) * years
    ) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    disc_r = math.exp(-rate * years)
    disc_q = math.exp(-div_yield * years)
    decay = -(spot * disc_q * _norm_pdf(d1) * iv) / (2.0 * sqrt_t)
    if option_type == "call":
        delta = disc_q * _norm_cdf(d1)
        theta_year = decay - rate * strike * disc_r * _norm_cdf(d2) \
            + div_yield * spot * disc_q * _norm_cdf(d1)
    else:
        delta = -disc_q * _norm_cdf(-d1)
        theta_year = decay + rate * strike * disc_r * _norm_cdf(-d2) \
            - div_yield * spot * disc_q * _norm_cdf(-d1)
    return {
        "delta": delta,
        "theta_per_day": theta_year / 365.0,
        "d1": d1,
        "d2": d2,
    }


def _prob_beyond_breakeven(
    spot: float,
    breakeven: float,
    years: float,
    iv: float,
    option_type: str,
    rate: float = config.RISK_FREE_RATE,
    div_yield: float = config.DIVIDEND_YIELD,
) -> Optional[float]:
    """Lognormal probability the underlying finishes past breakeven."""
    if spot <= 0 or breakeven <= 0 or iv <= 0 or years <= 0:
        return None
    z = (
        math.log(spot / breakeven)
        + (rate - div_yield - 0.5 * iv * iv) * years
    ) / (iv * math.sqrt(years))
    return _norm_cdf(z) if option_type == "call" else _norm_cdf(-z)


# ----------------------------------------------------------------------
# contract evaluation
# ----------------------------------------------------------------------
def _premium(contract: Dict) -> tuple[Optional[float], Optional[str]]:
    """Best available premium: mid of bid/ask, else last trade."""
    bid = contract.get("bid")
    ask = contract.get("ask")
    if bid is not None and ask is not None and ask > 0 and bid >= 0 and ask >= bid:
        return (float(bid) + float(ask)) / 2.0, "mid"
    last = contract.get("lastPrice")
    if last is not None and float(last) > 0:
        return float(last), "last"
    return None, None


def _check(name: str, passed: Optional[bool], detail: str) -> Dict:
    return {"check": name, "passed": passed, "detail": detail}


def et_date(epoch: float):
    """Calendar date on the US exchange clock (America/New_York)."""
    from zoneinfo import ZoneInfo

    return datetime.fromtimestamp(float(epoch), tz=ZoneInfo("America/New_York")).date()


def days_to_expiry(expiration: float, as_of: float) -> int:
    """Calendar days from the ET trading date to the expiry date.

    Yahoo stamps an expiry at 00:00 UTC of the expiry date, so the
    expiry's date is read in UTC; "today" is read on the ET clock, so
    an evening run (after 00:00 UTC) is not pushed a day forward.
    """
    exp_dt = datetime.fromtimestamp(float(expiration), tz=timezone.utc).date()
    return (exp_dt - et_date(as_of)).days


def select_expiration(
    expirations: List[int],
    as_of: Optional[float] = None,
    min_dte: int = config.CARD_MIN_DTE,
    max_dte: int = config.CARD_MAX_DTE,
    hold_days: int = config.DEFAULT_HOLDING_DAYS,
) -> Optional[Dict]:
    """The expiry the agent should trade, or None.

    The front expiry is often same-day (SPY/QQQ list daily expiries),
    and a same-day contract always fails the not_expired gate. Inside
    the min-max DTE window the nearest expiry that outlives the holding
    window wins; else the longest one in the window; failing both, the
    nearest one at or beyond min_dte. None when nothing qualifies.
    """
    as_of = time.time() if as_of is None else float(as_of)
    dated = [(int(e), days_to_expiry(e, as_of)) for e in expirations or []]
    in_window = [d for d in dated if min_dte <= d[1] <= max_dte]
    if in_window:
        # The contract should outlive the holding window (Oct 22 live
        # run: daily expiries made every pick 1 DTE, and every judge
        # stood aside on 1-day theta for a 5-day thesis).
        covering = [d for d in in_window if d[1] >= hold_days]
        if covering:
            exp, dte = min(covering, key=lambda d: d[1])
            return {"expiration": exp, "dte": dte, "basis": "covers_holding_window"}
        exp, dte = max(in_window, key=lambda d: d[1])
        return {"expiration": exp, "dte": dte, "basis": "longest_in_dte_window"}
    later = [d for d in dated if d[1] >= min_dte]
    if later:
        exp, dte = min(later, key=lambda d: d[1])
        return {"expiration": exp, "dte": dte, "basis": "nearest_beyond_min_dte"}
    return None


def fetch_trade_chain(
    provider: MarketDataProvider,
    ticker: str,
    as_of: Optional[float] = None,
) -> Dict:
    """Option chain at the selected expiry, with how it was chosen.

    Falls back to the provider's front chain (basis says so) when the
    expiry list is unavailable or nothing qualifies.
    """
    selection: Optional[Dict] = None
    try:
        selection = select_expiration(provider.get_expirations(ticker), as_of)
    except Exception as exc:  # expiry list is a nicety, not a blocker
        selection = {"expiration": None, "dte": None,
                     "basis": f"front_chain (expirations unavailable: {exc})"}
    if selection is None:
        selection = {"expiration": None, "dte": None,
                     "basis": "front_chain (no expiry at or beyond min DTE)"}
    chain = provider.get_option_chain(ticker, expiration=selection["expiration"])
    chain = dict(chain)
    chain["selection"] = selection
    return chain


def evaluate_contract(
    contract: Dict,
    option_type: str,
    spot: float,
    as_of: Optional[float] = None,
    expiration: Optional[int] = None,
    rate: float = config.RISK_FREE_RATE,
    div_yield: float = config.DIVIDEND_YIELD,
) -> Dict:
    """Evaluate one chain contract against the guardrail gates.

    contract: one dict from get_option_chain ("calls" / "puts" entry).
    option_type: "call" or "put" (which side of the chain it came from).
    spot: current underlying price. as_of: epoch seconds (default now).
    expiration: epoch seconds; defaults to the contract's own field.
    """
    as_of = time.time() if as_of is None else as_of
    strike = contract.get("strike")
    iv = contract.get("impliedVolatility")
    iv_placeholder = iv is not None and float(iv) < config.MIN_VALID_IV
    if iv_placeholder:
        iv = None  # a placeholder is missing data, never a volatility
    exp = expiration if expiration is not None else contract.get("expiration")

    premium, premium_source = _premium(contract)
    bid = contract.get("bid")
    ask = contract.get("ask")
    spread_pct = None
    if bid is not None and ask is not None and premium:
        spread_pct = (float(ask) - float(bid)) / premium * 100.0

    if exp is not None:
        dte = days_to_expiry(exp, as_of)
    else:
        dte = None
    years = (dte / 365.0) if dte is not None else None

    time_ok = dte is not None and dte > 0
    bs = (
        black_scholes(spot, float(strike), years, float(iv), option_type, rate, div_yield)
        if (strike is not None and iv is not None and time_ok)
        else None
    )
    delta = bs["delta"] if bs else None

    breakeven = None
    breakeven_move_pct = None
    if premium is not None and strike is not None:
        breakeven = float(strike) + premium if option_type == "call" else float(strike) - premium
        if spot > 0:
            breakeven_move_pct = (breakeven - spot) / spot * 100.0

    pop = (
        _prob_beyond_breakeven(spot, breakeven, years, float(iv), option_type, rate, div_yield)
        if (breakeven is not None and iv is not None and time_ok)
        else None
    )
    theta_burn = None
    if bs is not None:
        # Per contract (x100 shares); burn is what the long holder loses
        # per day to time decay, stated as a positive dollar figure.
        theta_burn = -bs["theta_per_day"] * 100.0

    # --- gate checks: passed True / False / None (unknown) ---
    checks: List[Dict] = []
    if delta is None:
        checks.append(_check(
            "delta_floor", None,
            "unknown - delta unavailable (needs IV, strike and time to expiry)",
        ))
    else:
        checks.append(_check(
            "delta_floor",
            abs(delta) >= config.MIN_DELTA,
            f"delta {delta:+.2f}; |delta| >= {config.MIN_DELTA:.2f} required to rank",
        ))
    checks.append(_check(
        "premium_known",
        premium is not None,
        (
            f"premium ${premium:.2f} ({premium_source})"
            if premium is not None
            else "no usable bid/ask or last price on the contract"
        ),
    ))
    checks.append(_check(
        "iv_known",
        iv is not None and float(iv) > 0,
        (
            f"implied volatility {float(iv) * 100:.1f}%"
            if iv is not None and float(iv) > 0
            else (
                "unknown - the feed printed a placeholder IV "
                f"(below {config.MIN_VALID_IV * 100:.0f}%) for this contract"
                if iv_placeholder
                else "unknown - chain carries no implied volatility for this contract"
            )
        ),
    ))
    if dte is None:
        checks.append(_check("not_expired", None, "unknown - no expiration on the contract"))
    elif dte < 0:
        checks.append(_check("not_expired", False, f"expired {-dte} day(s) ago"))
    elif dte == 0:
        checks.append(_check("not_expired", False, "expires today - no time left to be right"))
    else:
        checks.append(_check("not_expired", True, f"{dte} day(s) to expiry"))
    if spread_pct is None:
        checks.append(_check("spread_within_limit", None, "unknown - no bid/ask to measure"))
    else:
        checks.append(_check(
            "spread_within_limit",
            spread_pct <= config.GUARD_MAX_SPREAD_PCT * 100.0,
            f"bid/ask spread {spread_pct:.0f}% of premium vs "
            f"{config.GUARD_MAX_SPREAD_PCT * 100:.0f}% limit",
        ))

    by_name = {c["check"]: c["passed"] for c in checks}
    rankable = bool(
        by_name.get("delta_floor") is True
        and by_name.get("premium_known") is True
        and by_name.get("not_expired") is True
    )
    return {
        "contract_symbol": contract.get("contractSymbol"),
        "option_type": option_type,
        "strike": float(strike) if strike is not None else None,
        "expiration": int(exp) if exp is not None else None,
        "days_to_expiry": dte,
        "metrics": {
            "premium": round(premium, 4) if premium is not None else None,
            "premium_source": premium_source,
            "spread_pct": round(spread_pct, 1) if spread_pct is not None else None,
            "breakeven": round(breakeven, 4) if breakeven is not None else None,
            "breakeven_move_pct": (
                round(breakeven_move_pct, 2) if breakeven_move_pct is not None else None
            ),
            "delta": round(delta, 4) if delta is not None else None,
            "probability_of_profit": round(pop, 4) if pop is not None else None,
            "theta_burn_usd_per_day": (
                round(theta_burn, 2) if theta_burn is not None else None
            ),
            "implied_volatility": float(iv) if iv is not None else None,
        },
        "checks": checks,
        "rankable": rankable,
    }


def evaluate_chain(
    chain: Dict,
    spot: float,
    as_of: Optional[float] = None,
    rate: float = config.RISK_FREE_RATE,
    div_yield: float = config.DIVIDEND_YIELD,
) -> Dict:
    """Evaluate a whole chain; rank only the contracts that pass.

    "ranked" holds rankable contracts only, cheapest premium first -
    the cheapest contracts that can actually win. Everything else is
    counted under "rejected" with its evaluation kept for the record.
    """
    expiration = chain.get("expiration")
    evaluated: List[Dict] = []
    for side, key in (("call", "calls"), ("put", "puts")):
        for contract in chain.get(key, []):
            evaluated.append(
                evaluate_contract(
                    contract, side, spot,
                    as_of=as_of, expiration=expiration,
                    rate=rate, div_yield=div_yield,
                )
            )
    ranked = [e for e in evaluated if e["rankable"]]
    ranked.sort(key=lambda e: e["metrics"]["premium"])
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return {
        "expiration": int(expiration) if expiration is not None else None,
        "spot": spot,
        "evaluated": evaluated,
        "ranked": ranked,
        "ranked_count": len(ranked),
        "rejected_count": len(evaluated) - len(ranked),
    }


def guard_provider_chain(
    ticker: str,
    provider: MarketDataProvider,
    expiration: Optional[int] = None,
    as_of: Optional[float] = None,
) -> Dict:
    """Fetch spot + chain for one ticker and run the guardrail."""
    quote = provider.get_quote(ticker)
    chain = provider.get_option_chain(ticker, expiration=expiration)
    result = evaluate_chain(chain, float(quote["price"]), as_of=as_of)
    result["ticker"] = ticker
    return result
