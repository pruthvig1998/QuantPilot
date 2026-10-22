"""Risk review pass (Part C addition 1, Oct 22).

The fourth voice on the desk, after the judge and before the card
ships - the risk-management round from TradingAgents, rebuilt for
options and kept deterministic: it argues ONLY from the guardrail /
event checks and the card's own levels and sizing, never from model
text, so it cannot be talked out of a veto.

It can do exactly one thing to the verdict: downgrade a TRADE card to
a no-trade, naming every reason. It never upgrades anything. Unknown
values are not reasons to veto (the card's filters already refuse to
let an unknown confirm a trade); they are listed as cautions so the
reader sees what the review could not score.

Veto rules (any one is enough):
- event_crush_risk failed: IV rank above the red-flag line with an
  event inside the holding window
- earnings_in_window failed: earnings land inside the holding window
- sizing not executable: the 1% risk budget buys less than one contract
- no target level: reward cannot be measured
- reward:risk below RISK_MIN_REWARD_RISK (target vs stop distance)

Pure functions over the packet, debate result and card. No I/O, no
LLM. US markets only; research output - a human approves every order.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import config


def _checks_by_name(checks: List[Dict]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for check in checks or []:
        out.setdefault(check.get("check"), check)
    return out


def reward_risk(levels: Dict) -> Optional[float]:
    """|target - entry| / |entry - stop|, or None when a level is missing."""
    entry, stop, target = levels.get("entry"), levels.get("stop"), levels.get("target")
    if entry is None or stop is None or target is None:
        return None
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return None
    return round(abs(float(target) - float(entry)) / risk, 2)


def review_card(packet: Dict, debate_result: Dict, card: Dict) -> Dict:
    """Run the risk review over one card. Returns the review record."""
    review: Dict = {
        "agent": "risk_review",
        "verdict_in": card.get("verdict"),
        "verdict_out": card.get("verdict"),
        "applies": card.get("kind") == "trade",
        "downgraded": False,
        "reasons": [],
        "cautions": [],
        "reward_risk": None,
        "line": "",
    }
    events = (packet or {}).get("events") or {}
    checks = _checks_by_name(card.get("checks") or [])

    for check in card.get("checks") or []:
        if check.get("passed") is None:
            review["cautions"].append(
                f"{check.get('check')} unscored ({check.get('detail')})"
            )
    market = checks.get("market_event_in_window")
    if market is not None and market.get("passed") is False:
        review["cautions"].append(market.get("detail"))

    if not review["applies"]:
        review["line"] = (
            f"Risk review: not applicable - the card is a "
            f"{card.get('kind')} ({card.get('verdict')})."
        )
        return review

    reasons: List[str] = review["reasons"]
    crush = checks.get("event_crush_risk")
    if events.get("red_flag") or (crush is not None and crush.get("passed") is False):
        reasons.append(
            "IV crush risk: "
            + ((crush or {}).get("detail") or events.get("one_liner") or "red flag set")
        )
    earnings = checks.get("earnings_in_window")
    if earnings is not None and earnings.get("passed") is False:
        reasons.append(f"earnings inside the holding window: {earnings.get('detail')}")
    sizing = card.get("sizing") or {}
    if not sizing.get("executable"):
        notes = "; ".join(sizing.get("notes") or []) or "zero contracts"
        reasons.append(f"position cannot be sized: {notes}")
    levels = card.get("levels") or {}
    if levels.get("target") is None:
        reasons.append("no target level in the packet - reward cannot be measured")
    else:
        rr = reward_risk(levels)
        review["reward_risk"] = rr
        if rr is not None and rr < config.RISK_MIN_REWARD_RISK:
            reasons.append(
                f"reward:risk {rr:.2f} is below the "
                f"{config.RISK_MIN_REWARD_RISK:.1f} minimum (target "
                f"{levels.get('target')} vs stop {levels.get('stop')} from entry "
                f"{levels.get('entry')})"
            )

    if reasons:
        review["downgraded"] = True
        review["verdict_out"] = "WATCH"
        review["line"] = "Risk review: VETO - " + "; ".join(reasons) + "."
    else:
        rr_text = (
            f"reward:risk {review['reward_risk']:.2f}"
            if review["reward_risk"] is not None
            else "reward:risk unknown"
        )
        review["line"] = (
            f"Risk review: cleared - no failed crush/earnings check, sized at "
            f"{sizing.get('contracts')} contract(s), {rr_text}."
        )
    return review


def apply_risk_review(card: Dict, review: Dict) -> Dict:
    """Return the card with the review attached (and the veto applied)."""
    card = dict(card)
    card["risk_review"] = review
    if review.get("downgraded"):
        reason = "risk review vetoed the trade: " + "; ".join(review["reasons"])
        card["kind"] = "no_trade"
        card["downgraded"] = True
        card["downgrade_reason"] = reason
        card["sizing"] = {**(card.get("sizing") or {}), "contracts": 0,
                          "executable": False}
        card["rejection"] = {
            "reason": reason,
            "failed_checks": [r.split(":")[0] for r in review["reasons"]],
            "candidates_considered": None,
            "nearest_candidate": (card.get("contract") or {}).get("contract_symbol"),
        }
    return card


def sector_context(symbol: str, xray: Optional[Dict]) -> Dict:
    """Part C addition 5: place a name in its sector's X-Ray standing.

    Built only from the run's X-Ray. Index ETFs and names without a
    mapped sector ETF say so instead of borrowing one.
    """
    etf = config.SECTOR_OF.get(symbol)
    read = (xray or {}).get("read") or {}
    posture = read.get("posture")
    if etf is None:
        return {"sector_etf": None, "line": (
            f"{symbol}: index ETF - no single sector; market posture "
            f"{posture or 'unknown'}.")}
    sectors = ((xray or {}).get("sectors") or {}).get("sectors") or []
    row = next((r for r in sectors if r.get("ticker") == etf), None)
    if row is None:
        return {"sector_etf": etf, "line": (
            f"{symbol}: sector {etf} not ranked in this run's X-Ray; market "
            f"posture {posture or 'unknown'}.")}
    standing = row.get("label") or row.get("status") or "middle"
    return {
        "sector_etf": etf,
        "sector_rank": row.get("rank"),
        "sector_count": len(sectors),
        "sector_label": standing,
        "posture": posture,
        "line": (
            f"{symbol}: sector {etf} ranks #{row.get('rank')} of {len(sectors)} "
            f"({standing}), market posture {posture or 'unknown'}."
        ),
    }
