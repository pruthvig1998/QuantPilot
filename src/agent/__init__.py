"""Agent core (Day 3 drop): packet, debate loop, trade cards, journal.

packet: assembles one symbol's full evidence packet from the
provider and the existing modules (quote, indicators, liquidity
row, order blocks, guardrail candidates, IV/event assessment,
optional insider context). Missing pieces are null, never invented.

debate: the desk's bull -> bear -> judge pattern on the packet,
plus the Evaluator feedback loop from the HackOS Demo Video
Guide - an INSUFFICIENT_EVIDENCE verdict names its gap and sends
the analysts back once; the second verdict must land on
TRADE / WATCH / SKIP (WATCH if the gap persists). Prompts force
packet-only grounding with citations.

cards: structured trade cards (module 7) from a verdict + packet,
with the signals-bot filter values as explicit checks and 1%
account-risk sizing. A TRADE no contract survives is downgraded
to a no-trade skeleton on the card itself.

journal: self-scoring, append-only SQLite journal on the ledger
model (module 8) - entries never rewritten, outcomes appended,
hit-rate computed, and the full debate run record (both rounds)
stored inside each entry. Also the 2-loss circuit breaker
(module 9).

Day 4 outputs (this drop):
briefing: the morning briefing composed from one run's artifacts
(X-Ray, board, cards, risk flags, journal) in plain text + Markdown,
in the standing Discord style (session-tagged prices, no emojis,
one educational-only footer). Pure composition, no I/O.
ask: the Ask-QuantPilot why layer - a pure brain over the same
artifacts (transport/brain split), deterministic scope gate,
LLM composition under the debate grounding rules, extractive
fallback. It explains the run; it never advises.
dashboard: one self-contained dark HTML page for the judges -
X-Ray, board with components, cards with full checks lists, one
full debate run (both rounds), journal stats + breaker state.
"""
from .ask import answer_question
from .briefing import briefing_from_artifacts, generate_briefing, session_label
from .cards import build_card, choose_candidate, selection_checks
from .dashboard import featured_debate, render_dashboard, write_dashboard
from .debate import (
    build_bear_prompt,
    build_bull_prompt,
    build_judge_prompt,
    parse_judge,
    run_debate,
)
from .journal import Journal, open_journal
from .packet import assemble_packet, load_insider_context, packet_fingerprint

__all__ = [
    "Journal",
    "answer_question",
    "assemble_packet",
    "briefing_from_artifacts",
    "build_bear_prompt",
    "build_bull_prompt",
    "build_card",
    "build_judge_prompt",
    "choose_candidate",
    "featured_debate",
    "generate_briefing",
    "load_insider_context",
    "open_journal",
    "packet_fingerprint",
    "parse_judge",
    "render_dashboard",
    "run_debate",
    "selection_checks",
    "session_label",
    "write_dashboard",
]
