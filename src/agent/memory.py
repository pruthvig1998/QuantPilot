"""Agent memory over the Meterless H-Mem engine (audit repair, Oct 22).

The engine (src/integrations/meterless_engine.py, the vendored
official H-Mem reference) existed but nothing in the agent loop called
it. This module is the loop's use of it:

- recall_calls(symbol): before a debate, the agent's own past calls
  on this name (verdict, direction, conviction, entry, and the scored
  outcome once one exists) go into the packet as "memory", so the
  bull, bear and judge can cite them like any other packet value.
- remember_call(...): after a run, each new call is remembered under
  call:<ET date>:<symbol>; scoring it later rewrites the same key with
  the outcome added, which H-Mem records as a superseding memory (the
  old record is kept in its trust ledger, never deleted).

The journal stays the system of record for scoring; H-Mem is the
agent's recall layer. Memory is optional evidence: if Node or the
engine is unavailable, recall returns None with the error and the run
continues - nothing is invented in its place.

The engine is injectable (anything with remember / recall), so tests
run on a fake. US markets only.
"""
from __future__ import annotations

from typing import Dict, List, Optional

KEY_PREFIX = "call:"


def call_key(day: str, symbol: str) -> str:
    return f"{KEY_PREFIX}{day}:{symbol}"


def call_record(debate: Dict, card: Dict, packet: Optional[Dict], day: str) -> Dict:
    """The compact, JSON-safe memory of one call."""
    return {
        "symbol": (debate or {}).get("symbol") or (card or {}).get("symbol"),
        "date": day,
        "judge_verdict": (debate or {}).get("verdict"),
        "card_kind": (card or {}).get("kind"),
        "direction": (debate or {}).get("direction"),
        "conviction": (debate or {}).get("conviction"),
        "entry_spot": (packet or {}).get("spot"),
        "outcome": None,
    }


def remember_call(engine, debate: Dict, card: Dict, packet: Optional[Dict], day: str) -> str:
    symbol = (debate or {}).get("symbol") or (card or {}).get("symbol")
    record = call_record(debate, card, packet, day)
    return engine.remember(call_key(day, symbol), record, tags=["call", symbol])


def remember_outcome(engine, entry: Dict, outcome: Dict) -> Optional[str]:
    """Supersede a remembered call with its scored outcome."""
    symbol = entry.get("symbol")
    day = str(entry.get("ts") or "")[:10]
    if not symbol or not day:
        return None
    debate = entry.get("debate") or {}
    record = {
        "symbol": symbol,
        "date": day,
        "judge_verdict": debate.get("verdict"),
        "card_kind": (entry.get("card") or {}).get("kind"),
        "direction": entry.get("direction"),
        "conviction": entry.get("conviction"),
        "entry_spot": entry.get("entry_price"),
        "outcome": {
            "spot": outcome.get("spot"),
            "move_pct": outcome.get("move_pct"),
            "hit": outcome.get("hit"),
        },
    }
    return engine.remember(call_key(day, symbol), record, tags=["call", symbol, "scored"])


def recall_calls(engine, symbol: str, before_day: Optional[str] = None,
                 limit: int = 5) -> Dict:
    """Past calls on one symbol from H-Mem, newest first.

    Returns {"source", "calls", "error"}: calls is [] when the agent has
    no memory of the name yet, and None with the error when the engine
    could not be reached (unknown, not empty).
    """
    out: Dict = {"source": "meterless h-mem", "calls": None, "error": None}
    try:
        items = engine.recall(f"{symbol} call verdict outcome", top_n=25)
    except Exception as exc:  # optional evidence: never sinks a run
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    calls: List[Dict] = []
    for item in items or []:
        key = str(item.get("key") or "")
        value = item.get("value") or {}
        if not key.startswith(KEY_PREFIX) or value.get("symbol") != symbol:
            continue
        if before_day is not None and str(value.get("date") or "") >= before_day:
            continue
        calls.append(value)
    calls.sort(key=lambda v: str(v.get("date") or ""), reverse=True)
    out["calls"] = calls[:limit]
    return out
