"""Data packet assembler (agent core, Day 3 drop).

One symbol in, one JSON-serializable packet out. The packet is the
ONLY evidence the debate loop (src/agent/debate.py) is allowed to
use: quote, the indicator engine's playbook snapshot, the liquidity
board row, the nearest order blocks and liquidity pools, guardrail
evaluations for the best candidate contracts, the IV/event
assessment, and - when the file exists - insider-pattern context
from the Oct 20 EDGAR Form 4 scan (a second fragmented source, the
Track 02 story).

Data honesty, same contract as the guardrails: any piece that
cannot be fetched comes back None (with the error kept alongside),
never estimated and never invented. data_quality lists exactly
which pieces are missing so the judge can name the gap - that is
what the debate loop's INSUFFICIENT_EVIDENCE verdict reads.

Pure assembly over the MarketDataProvider interface plus the
existing module functions: no LLM, no Discord, no writes except
reading the optional insider JSON.

US markets only.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .. import config
from ..data.provider import MarketDataProvider
from ..guardrail.events import assess_risk, nearest_money_iv
from ..guardrail.probability import et_date, evaluate_chain, fetch_trade_chain
from ..indicators import analyze_symbol
from ..liquidity.board import score_symbol
from ..orderblocks import detector


def packet_fingerprint(packet: Dict) -> str:
    """Stable sha256 of the packet's canonical JSON (journal key)."""
    blob = json.dumps(packet, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_insider_context(
    symbol: str,
    path: Optional[str] = None,
) -> Optional[Dict]:
    """One symbol's insider-pattern entry, or None.

    None when the file does not exist (the Mac has no scan output),
    when it cannot be parsed, or when the symbol is not in it. The
    absence is information for the packet, not an error.
    """
    path = path or config.INSIDER_PATTERNS_PATH
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    entry = data.get(symbol)
    return entry if isinstance(entry, dict) else None


def _nearest_blocks(analysis: Optional[Dict], spot: float) -> Dict:
    """Unmitigated-first order blocks nearest spot, split by side."""
    if not analysis:
        return {"below": [], "above": []}
    blocks = analysis.get("order_blocks", [])

    def _key(block: Dict):
        # unmitigated first, then closest midpoint to spot
        return (bool(block.get("mitigated")), abs(block["midpoint"] - spot))

    below = sorted(
        (b for b in blocks if b["midpoint"] <= spot), key=_key
    )
    above = sorted(
        (b for b in blocks if b["midpoint"] > spot), key=_key
    )
    return {"below": below[:3], "above": above[:3]}


def _nearest_pools(analysis: Optional[Dict], spot: float) -> List[Dict]:
    """Liquidity pools nearest spot, each with its distance in %."""
    if not analysis:
        return []
    pools = []
    for pool in analysis.get("liquidity_pools", []):
        level = float(pool["level"])
        pools.append(
            {
                **pool,
                "distance_pct": (
                    round((level - spot) / spot * 100.0, 2) if spot else None
                ),
            }
        )
    pools.sort(key=lambda p: abs(p["distance_pct"] or 0.0))
    return pools[:5]


def _candidates(
    chain: Optional[Dict],
    spot: float,
    as_of: float,
    limit: int,
) -> Dict:
    """Guardrail-ranked candidate contracts with their raw chain rows.

    The card builder needs the raw volume / open interest for its
    selection checks, which the guardrail evaluation does not carry -
    so each surviving evaluation is wrapped with the chain contract
    it came from.
    """
    if chain is None:
        return {
            "expiration": None,
            "selection": None,
            "ranked_count": 0,
            "rejected_count": 0,
            "candidates": [],
        }
    evaluated = evaluate_chain(chain, spot, as_of=as_of)
    # A chain where NO contract prints open interest is a feed gap
    # (Yahoo premarket / stale), not a market with zero OI: the
    # candidates then carry OI as unknown so no check claims a fail.
    all_contracts = list(chain.get("calls", [])) + list(chain.get("puts", []))
    oi_feed_blank = bool(all_contracts) and not any(
        (c.get("openInterest") or 0) > 0 for c in all_contracts
    )
    raw_by_symbol = {}
    for side in ("calls", "puts"):
        for contract in chain.get(side, []):
            raw_by_symbol[contract.get("contractSymbol")] = contract
    # Up to `limit` per side: a call verdict needs call candidates even
    # when the cheapest rankable contracts are all puts (and vice versa).
    picked = [
        ev
        for side in ("call", "put")
        for ev in [e for e in evaluated["ranked"] if e["option_type"] == side][:limit]
    ]
    candidates = []
    for ev in picked:
        raw = raw_by_symbol.get(ev["contract_symbol"], {})
        candidates.append(
            {
                "contract_symbol": ev["contract_symbol"],
                "option_type": ev["option_type"],
                "evaluation": ev,
                "raw": {
                    "contractSymbol": raw.get("contractSymbol"),
                    "strike": raw.get("strike"),
                    "bid": raw.get("bid"),
                    "ask": raw.get("ask"),
                    "lastPrice": raw.get("lastPrice"),
                    "volume": raw.get("volume"),
                    "openInterest": (
                        None if oi_feed_blank else raw.get("openInterest")
                    ),
                    "impliedVolatility": raw.get("impliedVolatility"),
                },
            }
        )
    return {
        "expiration": evaluated["expiration"],
        "selection": chain.get("selection"),
        "oi_feed_blank": oi_feed_blank,
        "ranked_count": evaluated["ranked_count"],
        "rejected_count": evaluated["rejected_count"],
        "candidates": candidates,
    }


def assemble_packet(
    symbol: str,
    provider: MarketDataProvider,
    as_of: Optional[float] = None,
    insider_path: Optional[str] = None,
    holding_days: int = config.DEFAULT_HOLDING_DAYS,
    max_candidates: int = config.CARD_CANDIDATES_PER_PACKET,
    iv_history: Optional[Dict] = None,
) -> Dict:
    """Assemble the full evidence packet for one symbol.

    as_of: epoch seconds (default now). iv_history: optional
    {"low", "high", "basis", "days"} IV range for the IV-rank check
    (the runner passes the journal's own ATM-IV snapshot range once
    enough days exist). Pieces that fail to fetch
    are None with their error string kept next to them; the quote
    itself is load-bearing (everything prices off spot) and its
    failure raises, like a failed fetch in the board scan.
    """
    as_of = time.time() if as_of is None else float(as_of)
    as_of_date = et_date(as_of)

    quote = provider.get_quote(symbol)
    spot = float(quote["price"])

    # Indicator snapshot (playbook) - weekly RSI is a bonus, not a blocker.
    indicators: Optional[Dict] = None
    indicators_error: Optional[str] = None
    try:
        daily = provider.get_bars(symbol, interval="1d", period="2y")
        try:
            weekly = provider.get_bars(symbol, interval="1wk", period="5y")
        except Exception:
            weekly = None
        indicators = analyze_symbol(symbol, daily, weekly)
    except Exception as exc:
        indicators_error = str(exc)

    # Liquidity board row for this symbol.
    liquidity: Optional[Dict] = None
    liquidity_error: Optional[str] = None
    try:
        liquidity = score_symbol(symbol, provider)
    except Exception as exc:
        liquidity_error = str(exc)

    # Intraday order blocks + liquidity pools.
    ob_analysis: Optional[Dict] = None
    ob_error: Optional[str] = None
    try:
        intraday = provider.get_bars(symbol, interval="5m", period="5d")
        ob_analysis = detector.analyze(intraday)
    except Exception as exc:
        ob_error = str(exc)

    # Option chain once: guardrail candidates + IV/event assessment
    # both price off it.
    chain: Optional[Dict] = None
    chain_error: Optional[str] = None
    try:
        chain = fetch_trade_chain(provider, symbol, as_of=as_of)
    except Exception as exc:
        chain_error = str(exc)

    # Earnings date (providers that publish one); None stays unknown.
    earnings: Optional[Dict] = None
    earnings_error: Optional[str] = None
    getter = getattr(provider, "get_earnings_date", None)
    if getter is not None and symbol not in config.INDEX_ETFS:
        try:
            earnings = getter(symbol)
        except Exception as exc:
            earnings_error = str(exc)

    guardrails = _candidates(chain, spot, as_of, max_candidates)

    events: Optional[Dict] = None
    if chain is not None:
        current_iv = nearest_money_iv(chain, spot)
        events = assess_risk(
            symbol,
            as_of=as_of_date,
            holding_days=holding_days,
            current_iv=current_iv,
            iv_low_52w=(iv_history or {}).get("low"),
            iv_high_52w=(iv_history or {}).get("high"),
            iv_basis=(iv_history or {}).get("basis"),
            earnings_date=(earnings or {}).get("date"),
            earnings_not_applicable=symbol in config.INDEX_ETFS,
        )
        events["spot"] = spot
        events["earnings_source"] = (earnings or {}).get("source")
        events["earnings_estimate"] = (earnings or {}).get("estimate")
        events["earnings_error"] = earnings_error

    insider = load_insider_context(symbol, path=insider_path)

    missing: List[str] = []
    if indicators is None:
        missing.append("indicators")
    if liquidity is None:
        missing.append("liquidity")
    if ob_analysis is None:
        missing.append("order_blocks")
    if chain is None:
        missing.append("option_chain")
    if events is None:
        missing.append("events")
    if insider is None:
        missing.append("insider")

    return {
        "symbol": symbol,
        "as_of": datetime.fromtimestamp(as_of, tz=timezone.utc).isoformat(),
        "as_of_epoch": as_of,
        "spot": spot,
        "quote": quote,
        "indicators": indicators,
        "indicators_error": indicators_error,
        "liquidity": liquidity,
        "liquidity_error": liquidity_error,
        "order_blocks": {
            "analysis": ob_analysis,
            "error": ob_error,
            "below": _nearest_blocks(ob_analysis, spot)["below"],
            "above": _nearest_blocks(ob_analysis, spot)["above"],
            "nearest_pools": _nearest_pools(ob_analysis, spot),
        },
        "guardrails": guardrails,
        "guardrails_error": chain_error,
        "events": events,
        "events_error": chain_error,
        "insider": insider,
        "insider_source": (
            insider_path or config.INSIDER_PATTERNS_PATH
            if insider is not None
            else None
        ),
        "data_quality": {"complete": not missing, "missing": missing},
    }
