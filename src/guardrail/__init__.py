"""Guardrails: probability gate (module 5) + IV/event-risk gate (module 6).

probability: breakeven move, delta-implied probability of profit and
theta burn per contract, with the |delta| >= 0.30 ranking rule.
events: IV rank vs its 52-week range and event proximity inside the
holding window, red-flagging elevated IV into an event.

Both emit an explicit checks list of {check, passed, detail} (passed
True / False / None for unknown) - Cluse's conviction-checks pattern:
every gate states its verdict and its evidence, so the trade card can
show WHY a contract passed or failed. All pure functions over
provider data; anything unknowable is null/unknown, never invented.
"""
from .events import (
    assess_from_provider,
    assess_risk,
    events_in_window,
    iv_rank,
    nearest_money_iv,
)
from .probability import (
    black_scholes,
    evaluate_chain,
    evaluate_contract,
    guard_provider_chain,
)

__all__ = [
    "assess_from_provider",
    "assess_risk",
    "black_scholes",
    "evaluate_chain",
    "evaluate_contract",
    "events_in_window",
    "guard_provider_chain",
    "iv_rank",
    "nearest_money_iv",
]
