"""Structured trade cards (build plan module 7, agent core).

A card is built from a debate result plus the packet that fed it.
For a TRADE verdict the card picks a contract from the packet's
guardrail-surviving candidates using the signals bot's filter
values (delta band around 0.35, spread <= 20%, options volume
>= 50, OI >= 100, 1-7 DTE), sets entry / stop / target off the
order blocks and liquidity pools, and sizes the position at 1%
account risk: contracts = risk$ / (stop distance x 100).

Honesty rules, inherited from the guardrails:
- A TRADE verdict whose side has NO contract passing every filter
  is downgraded on the card to a no-trade skeleton naming the
  failed checks. The card never shows a trade the filters rejected.
- WATCH / SKIP verdicts produce the same skeleton: why no trade,
  with the same checks (events always; the nearest candidate's
  guardrail + selection checks when one exists).
- Levels that are not in the packet come back null, and the
  sizing that depends on them comes back 0 contracts with the
  reason stated. Nothing is invented to complete the card.

Every gate on the card is a {check, passed, detail} entry tagged
with its "source" (guardrail / selection / events) - the Cluse
conviction-checks pattern: the card shows its own working.

Pure functions over the packet and the debate result: no I/O,
no LLM. JSON-serializable throughout. US markets only; research
output - a human approves every order.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from .. import config


# ----------------------------------------------------------------------
# selection checks (signals-bot filter values, as checks)
# ----------------------------------------------------------------------
def _check(name: str, passed: Optional[bool], detail: str, source: str) -> Dict:
    return {"check": name, "passed": passed, "detail": detail, "source": source}


def selection_checks(candidate: Dict) -> List[Dict]:
    """The signals-bot contract filters, run on one packet candidate."""
    ev = candidate["evaluation"]
    metrics = ev["metrics"]
    raw = candidate.get("raw") or {}
    delta = metrics.get("delta")
    spread = metrics.get("spread_pct")
    dte = ev.get("days_to_expiry")
    volume = raw.get("volume")
    oi = raw.get("openInterest")
    lo = config.CARD_TARGET_DELTA - config.CARD_DELTA_TOLERANCE
    hi = config.CARD_TARGET_DELTA + config.CARD_DELTA_TOLERANCE

    checks: List[Dict] = []
    if delta is None:
        checks.append(_check(
            "delta_band", None,
            "unknown - no delta on the guardrail evaluation",
            "selection",
        ))
    else:
        checks.append(_check(
            "delta_band",
            lo <= abs(delta) <= hi,
            f"|delta| {abs(delta):.2f} vs target band {lo:.2f}-{hi:.2f} "
            f"around {config.CARD_TARGET_DELTA:.2f}",
            "selection",
        ))
    if spread is None:
        checks.append(_check(
            "spread_limit", None,
            "unknown - no bid/ask spread on the evaluation",
            "selection",
        ))
    else:
        checks.append(_check(
            "spread_limit",
            spread <= config.CARD_MAX_SPREAD_PCT,
            f"spread {spread:.0f}% of premium vs "
            f"{config.CARD_MAX_SPREAD_PCT:.0f}% limit",
            "selection",
        ))
    if volume is None:
        checks.append(_check(
            "option_volume", None,
            "unknown - no volume printed for this contract",
            "selection",
        ))
    else:
        checks.append(_check(
            "option_volume",
            float(volume) >= config.CARD_MIN_OPTION_VOLUME,
            f"contract volume {float(volume):.0f} vs "
            f"{config.CARD_MIN_OPTION_VOLUME} minimum",
            "selection",
        ))
    if oi is None:
        checks.append(_check(
            "open_interest", None,
            "unknown - the feed printed no open interest for this chain",
            "selection",
        ))
    else:
        checks.append(_check(
            "open_interest",
            float(oi) >= config.CARD_MIN_OPEN_INTEREST,
            f"open interest {float(oi):.0f} vs "
            f"{config.CARD_MIN_OPEN_INTEREST} minimum",
            "selection",
        ))
    if dte is None:
        checks.append(_check(
            "dte_window", None,
            "unknown - no days-to-expiry on the evaluation",
            "selection",
        ))
    else:
        checks.append(_check(
            "dte_window",
            config.CARD_MIN_DTE <= dte <= config.CARD_MAX_DTE,
            f"{dte} day(s) to expiry vs the "
            f"{config.CARD_MIN_DTE}-{config.CARD_MAX_DTE} DTE window",
            "selection",
        ))
    return checks


def _tagged(checks: List[Dict], source: str) -> List[Dict]:
    return [{**c, "source": source} for c in checks]


def _candidate_checks(candidate: Dict) -> List[Dict]:
    """Guardrail checks + selection checks for one candidate."""
    return (
        _tagged(candidate["evaluation"]["checks"], "guardrail")
        + selection_checks(candidate)
    )


def _is_eligible(candidate: Dict) -> bool:
    """Rankable by the guardrail AND every selection check passed."""
    if not candidate["evaluation"].get("rankable"):
        return False
    return all(c["passed"] is True for c in selection_checks(candidate))


def _band_distance(candidate: Dict) -> float:
    delta = candidate["evaluation"]["metrics"].get("delta")
    if delta is None:
        return float("inf")
    return abs(abs(delta) - config.CARD_TARGET_DELTA)


def choose_candidate(
    candidates: List[Dict],
    direction: str,
) -> Optional[Dict]:
    """Best eligible contract on the verdict's side, or None.

    Closest to the 0.35 delta target wins; premium breaks ties.
    """
    side = {"call": "call", "put": "put"}.get(direction)
    if side is None:
        return None
    eligible = [
        c
        for c in candidates
        if c["option_type"] == side and _is_eligible(c)
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda c: (
            _band_distance(c),
            c["evaluation"]["metrics"].get("premium") or float("inf"),
        )
    )
    return eligible[0]


def _failed_check_names(candidate: Dict) -> List[str]:
    names = []
    for check in _candidate_checks(candidate):
        if check["passed"] is not True:
            names.append(check["check"])
    if not candidate["evaluation"].get("rankable"):
        names.append("guardrail_rankable")
    return names


# ----------------------------------------------------------------------
# levels from order blocks + pools
# ----------------------------------------------------------------------
def _entry_zone(packet: Dict, direction: str) -> Optional[Dict]:
    """The order block the entry is referenced to, or None.

    Calls: an unmitigated bullish block below spot (a demand zone to
    buy a retest of). Puts mirror with bearish blocks above spot.
    Falls back to any same-direction block, then any block on the
    entry side - the fallback used is named in the zone's "basis".
    """
    ob = packet.get("order_blocks") or {}
    if direction == "call":
        side_blocks, want = ob.get("below") or [], "bullish"
    else:
        side_blocks, want = ob.get("above") or [], "bearish"
    for basis, pool in (
        ("unmitigated_same_direction",
         [b for b in side_blocks if b["type"] == want and not b.get("mitigated")]),
        ("same_direction",
         [b for b in side_blocks if b["type"] == want]),
        ("any_block_on_entry_side", list(side_blocks)),
    ):
        if pool:
            return {**pool[0], "basis": basis}
    return None


def _target_level(packet: Dict, direction: str, entry: float) -> Dict:
    """Nearest liquidity pool beyond the entry, else S/R, else null."""
    ob = packet.get("order_blocks") or {}
    want_pool = "equal_highs" if direction == "call" else "equal_lows"
    beyond = [
        p
        for p in ob.get("nearest_pools") or []
        if p["type"] == want_pool
        and ((direction == "call" and p["level"] > entry)
             or (direction == "put" and p["level"] < entry))
    ]
    if beyond:
        pool = min(beyond, key=lambda p: abs(p["level"] - entry))
        return {"target": float(pool["level"]), "target_source": "liquidity_pool"}
    analysis = ob.get("analysis") or {}
    sr = analysis.get("support_resistance") or {}
    levels = sr.get("resistance") if direction == "call" else sr.get("support")
    levels = [
        float(x) for x in (levels or [])
        if (direction == "call" and float(x) > entry)
        or (direction == "put" and float(x) < entry)
    ]
    if levels:
        level = min(levels, key=lambda x: abs(x - entry))
        return {"target": level, "target_source": "support_resistance"}
    return {"target": None, "target_source": None}


# ----------------------------------------------------------------------
# the card
# ----------------------------------------------------------------------
def _greeks_plain(evaluation: Optional[Dict]) -> Dict:
    """Module 7's plain-English Greeks, built only from known values."""
    if evaluation is None:
        return {
            "breakeven": None,
            "breakeven_move_pct": None,
            "probability_of_profit": None,
            "theta_burn_usd_per_day": None,
            "line": "no contract evaluated - Greeks unknown",
        }
    m = evaluation["metrics"]
    bits: List[str] = []
    if m.get("breakeven_move_pct") is not None:
        if evaluation.get("expiration"):
            from datetime import datetime, timezone

            when = "by " + datetime.fromtimestamp(
                evaluation["expiration"], tz=timezone.utc
            ).date().isoformat()
        else:
            when = "by expiry"
        bits.append(
            f"needs {m['breakeven_move_pct']:+.1f}% {when} to break even"
        )
    if m.get("probability_of_profit") is not None:
        bits.append(
            f"model probability of profit {m['probability_of_profit'] * 100:.0f}%"
        )
    if m.get("theta_burn_usd_per_day") is not None:
        bits.append(
            f"bleeds ${abs(m['theta_burn_usd_per_day']):.2f}/day in theta per contract"
        )
    return {
        "breakeven": m.get("breakeven"),
        "breakeven_move_pct": m.get("breakeven_move_pct"),
        "probability_of_profit": m.get("probability_of_profit"),
        "theta_burn_usd_per_day": m.get("theta_burn_usd_per_day"),
        "line": "; ".join(bits) if bits else "Greeks unknown for this contract",
    }


def _sizing(
    entry: Optional[float],
    stop: Optional[float],
    premium: Optional[float],
    account_size: float,
    delta: Optional[float] = None,
) -> Dict:
    """1% account-risk sizing (module 7). Zero contracts, with the
    reason, whenever the packet cannot support the math.

    Per-contract risk is the option's first-order loss if the stop is
    hit: |delta| x stop distance x 100, capped at the whole premium
    (a long option cannot lose more). With no delta it falls back to
    stop distance x 100 (the delta-1 bound, the conservative side).
    Decided Oct 22: the delta-1 rule sized cards ~1/delta too small;
    the CARD_MAX_PREMIUM_PCT cap still bounds the gap-through-stop
    worst case."""
    risk_budget = round(account_size * config.AGENT_RISK_PCT, 2)
    base = {
        "account_size_usd": account_size,
        "risk_pct": config.AGENT_RISK_PCT,
        "risk_budget_usd": risk_budget,
        "stop_distance": None,
        "per_contract_risk_usd": None,
        "contracts": 0,
        "premium_per_contract_usd": (
            round(premium * 100.0, 2) if premium is not None else None
        ),
        "premium_outlay_usd": None,
        "risk_basis": None,
        "executable": False,
        "notes": [],
    }
    if entry is None or stop is None:
        base["notes"].append(
            "no stop level in the packet - position cannot be sized"
        )
        return base
    distance = abs(entry - stop)
    base["stop_distance"] = round(distance, 4)
    if distance <= 0:
        base["notes"].append("stop distance is zero - cannot size")
        return base
    if delta is not None and abs(delta) > 0:
        per_contract_risk = abs(delta) * distance * 100.0
        base["risk_basis"] = f"|delta| {abs(delta):.2f} x stop distance x 100"
        if premium is not None and premium > 0 and premium * 100.0 < per_contract_risk:
            per_contract_risk = premium * 100.0
            base["risk_basis"] = "whole premium (below the delta-adjusted stop loss)"
    else:
        per_contract_risk = distance * 100.0
        base["risk_basis"] = "stop distance x 100 (no delta: delta-1 bound)"
    base["per_contract_risk_usd"] = round(per_contract_risk, 2)
    by_risk = math.floor(risk_budget / per_contract_risk)
    contracts = by_risk
    if premium is not None and premium > 0:
        cap_usd = account_size * config.CARD_MAX_PREMIUM_PCT
        by_capital = math.floor(cap_usd / (premium * 100.0))
        if by_capital < contracts:
            contracts = by_capital
            base["notes"].append(
                f"contract count capped: total premium limited to "
                f"{config.CARD_MAX_PREMIUM_PCT * 100:.0f}% of the account "
                f"(${cap_usd:,.0f}) - a long option can lose all of it"
            )
    base["contracts"] = int(contracts)
    base["premium_outlay_usd"] = (
        round(contracts * premium * 100.0, 2) if premium is not None else None
    )
    base["executable"] = contracts >= 1
    if contracts < 1:
        base["notes"].append(
            "1% risk budget buys less than one contract at this stop distance"
        )
    return base


def build_card(
    packet: Dict,
    debate_result: Dict,
    account_size: Optional[float] = None,
) -> Dict:
    """Build the structured trade card for one debated symbol."""
    account_size = (
        float(account_size) if account_size is not None else config.ACCOUNT_SIZE_USD
    )
    symbol = packet.get("symbol")
    verdict = debate_result.get("verdict")
    direction = debate_result.get("direction") or "none"
    judge = debate_result.get("judge") or {}
    candidates = (packet.get("guardrails") or {}).get("candidates") or []
    event_checks = _tagged(
        (packet.get("events") or {}).get("checks") or [], "events"
    )
    spot = packet.get("spot")

    card: Dict = {
        "symbol": symbol,
        "kind": "no_trade",
        "verdict": verdict,
        "conviction": debate_result.get("conviction"),
        "direction": direction,
        "why": debate_result.get("why"),
        "downgraded": False,
        "downgrade_reason": None,
        "generated_from": {
            "packet_hash": debate_result.get("packet_hash"),
            "as_of": packet.get("as_of"),
        },
        "contract": None,
        "levels": {
            "spot": spot,
            "entry_zone": None,
            "entry": None,
            "stop": None,
            "target": None,
            "target_source": None,
        },
        "greeks_plain": _greeks_plain(None),
        "sizing": _sizing(None, None, None, account_size),
        "checks": list(event_checks),
        "rejection": None,
    }

    if verdict != "TRADE":
        # Skeleton: same checks, nearest candidate shown for the record.
        reason_bits = [f"judge verdict {verdict}"]
        if judge.get("summary"):
            reason_bits.append(judge["summary"])
        if verdict == "INSUFFICIENT_EVIDENCE":
            reason_bits.append(
                "the debate loop should have resolved this to a final "
                "verdict - treated as no-trade defensively"
            )
        nearest = candidates[0] if candidates else None
        if nearest is not None:
            card["checks"] += _candidate_checks(nearest)
            card["contract"] = _contract_block(nearest)
            card["greeks_plain"] = _greeks_plain(nearest["evaluation"])
        card["rejection"] = {
            "reason": ". ".join(reason_bits),
            "failed_checks": [],
            "candidates_considered": len(candidates),
            "nearest_candidate": (
                nearest["contract_symbol"] if nearest else None
            ),
        }
        return card

    # TRADE: a contract must survive every filter on the verdict side.
    chosen = choose_candidate(candidates, direction)
    if chosen is None:
        side_pool = [
            c for c in candidates if c["option_type"] == direction
        ]
        best = (
            min(side_pool, key=_band_distance) if side_pool else None
        )
        failed = _failed_check_names(best) if best else []
        card["downgraded"] = True
        card["downgrade_reason"] = (
            f"judge said TRADE ({direction}) but no contract on that "
            "side passed the guardrail + selection filters"
        )
        if best is not None:
            card["checks"] += _candidate_checks(best)
            card["contract"] = _contract_block(best)
            card["greeks_plain"] = _greeks_plain(best["evaluation"])
        card["rejection"] = {
            "reason": card["downgrade_reason"],
            "failed_checks": failed,
            "candidates_considered": len(candidates),
            "nearest_candidate": (
                best["contract_symbol"] if best else None
            ),
        }
        return card

    # TRADE with a surviving contract: levels + sizing off the packet.
    ev = chosen["evaluation"]
    zone = _entry_zone(packet, direction)
    entry = float(zone["midpoint"]) if zone else spot
    stop: Optional[float] = None
    if zone is not None:
        width = float(zone["top"]) - float(zone["bottom"])
        buffer = config.CARD_STOP_BUFFER_FRACTION * width
        stop = (
            float(zone["bottom"]) - buffer
            if direction == "call"
            else float(zone["top"]) + buffer
        )
    target_block = (
        _target_level(packet, direction, entry)
        if entry is not None
        else {"target": None, "target_source": None}
    )
    premium = ev["metrics"].get("premium")

    card["kind"] = "trade"
    card["contract"] = _contract_block(chosen)
    card["levels"] = {
        "spot": spot,
        "entry_zone": (
            {
                "type": zone["type"],
                "top": zone["top"],
                "bottom": zone["bottom"],
                "midpoint": zone["midpoint"],
                "mitigated": zone.get("mitigated"),
                "basis": zone.get("basis"),
            }
            if zone
            else None
        ),
        "entry": round(float(entry), 4) if entry is not None else None,
        "stop": round(float(stop), 4) if stop is not None else None,
        "target": target_block["target"],
        "target_source": target_block["target_source"],
    }
    card["greeks_plain"] = _greeks_plain(ev)
    card["sizing"] = _sizing(
        float(entry) if entry is not None else None,
        stop,
        premium,
        account_size,
        delta=ev["metrics"].get("delta"),
    )
    card["checks"] += _candidate_checks(chosen)
    return card


def _contract_block(candidate: Dict) -> Dict:
    ev = candidate["evaluation"]
    return {
        "contract_symbol": ev["contract_symbol"],
        "option_type": ev["option_type"],
        "strike": ev["strike"],
        "expiration": ev["expiration"],
        "days_to_expiry": ev["days_to_expiry"],
        "premium": ev["metrics"].get("premium"),
        "premium_source": ev["metrics"].get("premium_source"),
    }
