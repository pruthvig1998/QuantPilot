"""Liquidity Board (build plan module 1).

Every watchlist name gets one score in [-100, +100]:

    score = 100 x (0.30 x options OI bias
                 + 0.25 x options volume bias
                 + 0.25 x price momentum
                 + 0.20 x relative volume, signed by momentum)

Positive components lean bullish, negative bearish. A name with no
directional options positioning, no price move and no volume expansion
lands near zero and reads "choppy" - exactly the names to ignore.

The board is rebuilt from scratch on every call, so the morning loop can
call build_board() once a minute during market hours (9:30 AM - 4:00 PM
ET) and always see the current ranking. All output is JSON-serializable,
and the raw components ride along in every row so the trade card can
explain WHY a name ranks where it does (Track 02: the agent that can
explain why).

US markets only. Works against any MarketDataProvider.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

from .. import config
from ..data.provider import MarketDataProvider
from ..guardrail.probability import fetch_trade_chain
from ..indicators import relative_volume
from ..indicators.engine import intraday_relative_volume


# ----------------------------------------------------------------------
# options positioning
# ----------------------------------------------------------------------
def chain_bias(
    chain: Dict,
    price: float,
    band: float = config.LIQ_CHAIN_BAND,
) -> Dict[str, float]:
    """Call-vs-put bias from one option chain, near the money only.

    Only strikes within +/-band (fraction) of spot count: far-OTM lottery
    tickets and deep hedges would swamp the signal. Returns bias ratios
    in [-1, +1] plus the raw totals they came from. A bias is None
    (unknown) when the band holds no data for that field at all - a
    feed that prints zero open interest everywhere is missing data,
    not a perfectly balanced book.
    """
    lo = price * (1 - band)
    hi = price * (1 + band)

    def _sum(contracts: List[dict], field: str) -> float:
        return float(
            sum(
                c.get(field) or 0
                for c in contracts
                if c.get("strike") is not None and lo <= c["strike"] <= hi
            )
        )

    call_oi = _sum(chain.get("calls", []), "openInterest")
    put_oi = _sum(chain.get("puts", []), "openInterest")
    call_vol = _sum(chain.get("calls", []), "volume")
    put_vol = _sum(chain.get("puts", []), "volume")

    def _bias(calls: float, puts: float) -> Optional[float]:
        total = calls + puts
        return (calls - puts) / total if total > 0 else None

    return {
        "oi_bias": _bias(call_oi, put_oi),  # None = no OI printed in band
        "volume_bias": _bias(call_vol, put_vol),
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_volume": call_vol,
        "put_volume": put_vol,
    }


# ----------------------------------------------------------------------
# scoring
# ----------------------------------------------------------------------
def _direction_label(score: float) -> str:
    if score >= config.LIQ_BULLISH_THRESHOLD:
        return "bullish"
    if score <= config.LIQ_BEARISH_THRESHOLD:
        return "bearish"
    return "choppy"


def blend_components(components: Dict[str, Optional[float]]) -> Dict:
    """Weighted blend over the KNOWN components only.

    Unknown (None) components drop out and the remaining weights are
    renormalized, so a missing input never enters the score as a
    neutral 0.0. weight_coverage says how much of the full weight the
    score actually rests on (1.0 = every component known).
    """
    weights = {
        "options_oi": config.LIQ_WEIGHT_OI,
        "options_volume": config.LIQ_WEIGHT_OPT_VOL,
        "momentum": config.LIQ_WEIGHT_MOMENTUM,
        "relative_volume": config.LIQ_WEIGHT_RELVOL,
    }
    known = {k: v for k, v in components.items() if v is not None}
    covered = sum(weights[k] for k in known)
    if covered <= 0:
        return {"score": None, "weight_coverage": 0.0,
                "unknown_components": sorted(components)}
    blend = sum(weights[k] * v for k, v in known.items()) / covered
    return {
        "score": round(100.0 * blend, 2),
        "weight_coverage": round(covered / sum(weights.values()), 4),
        "unknown_components": sorted(k for k, v in components.items() if v is None),
    }


def score_symbol(ticker: str, provider: MarketDataProvider) -> Dict:
    """Score one symbol against the provider. Returns one board row."""
    quote = provider.get_quote(ticker)
    price = float(quote["price"])
    # 2y (not 6mo): every input below is windowed (5-day return, 20-day
    # relative volume), so the result is identical, and the same bars
    # serve the X-Ray and the packet from the run cache.
    daily = provider.get_bars(ticker, interval="1d", period="2y")
    chain = fetch_trade_chain(provider, ticker)

    # Price momentum: blend of today's move and the 5-day drift, squashed
    # with tanh so a monster day saturates instead of dominating forever.
    # An unknown day change drops out of the blend instead of reading 0.
    closes = daily["close"]
    change_pct = quote.get("change_pct")
    ret_1d = float(change_pct) / 100.0 if change_pct is not None else None
    ret_5d = (
        float(closes.iloc[-1] / closes.iloc[-6] - 1) if len(closes) >= 6 else None
    )
    if ret_5d is not None and ret_1d is not None:
        mom_raw: Optional[float] = 0.6 * ret_5d + 0.4 * ret_1d
    else:
        mom_raw = ret_5d if ret_5d is not None else ret_1d
    momentum = (
        math.tanh(mom_raw / config.LIQ_MOMENTUM_SCALE) if mom_raw is not None else None
    )

    # Relative volume is a magnitude; momentum gives it a direction.
    # In session: today-so-far vs the same time on prior sessions (5m
    # bars). Otherwise, or when intraday bars are unavailable, the last
    # completed daily bar vs its 20-day average.
    intraday = None
    try:
        intraday = intraday_relative_volume(
            provider.get_bars(ticker, interval="5m", period="5d")
        )
    except Exception:
        intraday = None
    if intraday is not None:
        rv = float(intraday["relative_volume"])
        rv_basis = intraday["basis"]
    else:
        rv = float(relative_volume(daily)["relative_volume"])
        rv_basis = "daily bar vs 20-day average"
    intensity = min(max((rv - 1.0) / (config.LIQ_RELVOL_SATURATION - 1.0), 0.0), 1.0)
    if mom_raw is None:
        relvol_score: Optional[float] = None  # no direction to sign it with
    else:
        direction = 1.0 if mom_raw > 0 else (-1.0 if mom_raw < 0 else 0.0)
        relvol_score = direction * intensity

    bias = chain_bias(chain, price)
    components = {
        "options_oi": bias["oi_bias"],
        "options_volume": bias["volume_bias"],
        "momentum": momentum,
        "relative_volume": relvol_score,
    }
    blended = blend_components(components)
    score = blended["score"]
    if score is None:
        raise ValueError(f"no scoreable component for {ticker}")
    return {
        "ticker": ticker,
        "price": price,
        "score": score,
        "direction": _direction_label(score),
        "components": {
            k: (round(v, 4) if v is not None else None) for k, v in components.items()
        },
        "unknown_components": blended["unknown_components"],
        "weight_coverage": blended["weight_coverage"],
        "inputs": {
            "call_oi": bias["call_oi"],
            "put_oi": bias["put_oi"],
            "call_volume": bias["call_volume"],
            "put_volume": bias["put_volume"],
            "change_pct": round(ret_1d * 100, 2) if ret_1d is not None else None,
            "ret_5d_pct": round(ret_5d * 100, 2) if ret_5d is not None else None,
            "relative_volume": round(rv, 2),
            "relative_volume_basis": rv_basis,
        },
        "expiration": chain.get("expiration"),
        "chain_selection": chain.get("selection"),
    }


def build_board(
    provider: MarketDataProvider,
    tickers: Optional[Sequence[str]] = None,
) -> Dict:
    """Score the whole watchlist and rank it, bullish on top.

    A symbol whose data fetch fails (for example options tables not yet
    registered in Zetaris) lands in "errors" instead of sinking the whole
    board; the rest still rank.
    """
    rows: List[Dict] = []
    errors: List[Dict] = []
    for ticker in tickers or config.WATCHLIST:
        try:
            rows.append(score_symbol(ticker, provider))
        except Exception as exc:  # one bad name must not sink the board
            errors.append({"ticker": ticker, "error": str(exc)})
    rows.sort(key=lambda r: r["score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"board": rows, "errors": errors, "count": len(rows)}
