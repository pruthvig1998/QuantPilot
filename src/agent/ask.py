"""Ask-QuantPilot "why" layer (Day 4 drop).

The Track 02 demo surface: a judge (or the user) asks a question
about the latest run - "why is TSLA ranked first?", "what could
make the NVDA card fail?", "what is our hit rate?" - and gets an
answer grounded ONLY in that run's artifacts: the liquidity board,
the trade cards, the debate records, the packets, the journal
stats.

Architecture (the adopted Cluse transport/brain split): this module
is the pure brain - answer_question(question, artifacts) - and any
transport (a dashboard box, a Discord command, a CLI) can call it
and get the same answer.

Two composition paths over ONE deterministic scope gate:
- Scope gate (always deterministic): personal-finance-advice
  questions and tickers outside the run are refused honestly;
  a watched ticker with no artifacts in this run is an "unknown",
  never a guess. The LLM never gets to override the gate.
- LLM path: with a client (src/integrations/llm.py), the model
  composes a natural answer from a trimmed evidence bundle under
  the debate loop's GROUNDING RULES. An empty or failed LLM reply
  falls back to the extractive path rather than shipping nothing.
- Fallback path: deterministic extraction - the answer is assembled
  from the artifact values themselves, citing them as it goes.

Every number in either path comes from the artifacts. US markets
only; research output - the layer explains, it never advises.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from .. import config
from .debate import GROUNDING_RULES
from .grounding import grounding_report, is_verified

# Capitalized words that look like tickers but are desk vocabulary.
_NOT_TICKERS = {
    "AI", "AM", "ATM", "ATR", "BEST", "CALL", "CEO", "CPI", "DMA", "DTE",
    "EMA", "ET", "ETF", "FAIL", "FOMC", "GDP", "HOW", "ITM", "IV", "LLM",
    "NFP", "OI", "OTM", "PM", "POP", "PUT", "RISK", "RSI", "SMA", "THE",
    "TOP", "USA", "USD", "VWAP", "WHAT", "WHEN", "WHY",
}

_ADVICE_PATTERNS = (
    "should i", "should we", "my money", "my portfolio", "my savings",
    "invest my", "retirement", "tax advice", "financial advice",
    "buy now", "sell now", "i buy", "i sell",
)

_HIT_RATE_WORDS = (
    "hit rate", "win rate", "how accurate", "track record",
    "performance", "how are we doing", "how did we do", "journal",
)


# ----------------------------------------------------------------------
# artifact access
# ----------------------------------------------------------------------
class _Artifacts:
    """Normalized read view over a runner-style artifacts bundle."""

    def __init__(self, artifacts: Optional[Dict]) -> None:
        artifacts = artifacts or {}
        board = artifacts.get("board") or {}
        self.board_rows: Dict[str, Dict] = {
            row.get("ticker"): row for row in board.get("board") or []
        }
        self.board_count = board.get("count", len(self.board_rows))
        self.board_errors = board.get("errors") or []
        self.xray = artifacts.get("xray")
        cards = artifacts.get("cards") or []
        if isinstance(cards, dict):
            cards = list(cards.values())
        self.cards: Dict[str, Dict] = {c.get("symbol"): c for c in cards}
        packets = artifacts.get("packets") or {}
        if isinstance(packets, list):
            packets = {p.get("symbol"): p for p in packets}
        self.packets: Dict[str, Dict] = packets
        debates = artifacts.get("debates") or {}
        if isinstance(debates, list):
            debates = {d.get("symbol"): d for d in debates}
        self.debates: Dict[str, Dict] = debates
        self.stats = artifacts.get("journal_stats")

    def symbols(self) -> List[str]:
        seen: List[str] = []
        for source in (self.board_rows, self.cards, self.packets, self.debates):
            for symbol in source:
                if symbol and symbol not in seen:
                    seen.append(symbol)
        return seen

    def has(self, symbol: str) -> bool:
        return symbol in self.symbols()


def _extract_symbols(question: str, art: _Artifacts) -> Tuple[Optional[str], Optional[str]]:
    """(symbol in artifacts, foreign/watched-but-absent symbol)."""
    known = set(art.symbols())
    for token in re.findall(r"\b[A-Za-z]{1,5}\b", question):
        upper = token.upper()
        if upper in known:
            return upper, None
    for token in re.findall(r"\b[A-Za-z]{1,5}\b", question):
        upper = token.upper()
        if upper in config.WATCHLIST:
            return None, upper
    for token in re.findall(r"\b[A-Z]{2,5}\b", question):
        if token not in _NOT_TICKERS:
            return None, token
    return None, None


# ----------------------------------------------------------------------
# extractive answers (fallback path + the facts the LLM must match)
# ----------------------------------------------------------------------
def _signed_or_unknown(value) -> str:
    """+0.42 for a number, "unknown" for anything else (never raises)."""
    try:
        return f"{float(value):+.2f}"
    except (TypeError, ValueError):
        return "unknown"


def _board_why(symbol: str, art: _Artifacts) -> Tuple[str, List[str]]:
    row = art.board_rows.get(symbol)
    if row is None:
        return (
            f"Unknown in the artifacts: {symbol} has no liquidity board "
            "row in this run, so its ranking cannot be explained.",
            [],
        )
    comp = row.get("components") or {}
    inputs = row.get("inputs") or {}
    top = min(art.board_rows.values(), key=lambda r: r.get("rank", 99))
    lead = ""
    if top.get("ticker") != symbol:
        lead = (
            f"{symbol} is not ranked first - it is #{row.get('rank')} of "
            f"{art.board_count}; {top.get('ticker')} leads with a score of "
            f"{float(top.get('score', 0.0)):.2f}. "
        )
    text = (
        f"{lead}{symbol} ranks #{row.get('rank')} of {art.board_count} on "
        f"the liquidity board with a score of {float(row.get('score', 0.0)):.2f} "
        f"({row.get('direction')}). The score blends four components: "
        f"options OI {_signed_or_unknown(comp.get('options_oi'))} "
        f"(weight 0.30), options volume {_signed_or_unknown(comp.get('options_volume'))} "
        f"(0.25), momentum {_signed_or_unknown(comp.get('momentum'))} (0.25), "
        f"relative volume {_signed_or_unknown(comp.get('relative_volume'))} (0.20). "
        f"Inputs: call OI {inputs.get('call_oi', 'unknown')} vs put OI "
        f"{inputs.get('put_oi', 'unknown')}, call volume "
        f"{inputs.get('call_volume', 'unknown')} vs put volume "
        f"{inputs.get('put_volume', 'unknown')}, day change "
        f"{inputs.get('change_pct', 'unknown')}%, 5-day return "
        f"{inputs.get('ret_5d_pct', 'unknown')}%, relative volume "
        f"{inputs.get('relative_volume', 'unknown')}."
    )
    unknown = row.get("unknown_components") or []
    if unknown:
        coverage = row.get("weight_coverage")
        text += (
            f" Unknown this run: {', '.join(unknown)} - the score is "
            "renormalized over the known components"
            + (f" ({float(coverage) * 100:.0f}% of the full weight)." if coverage is not None else ".")
        )
    return text, [f"board:{symbol}"]


def _card_fail(symbol: str, art: _Artifacts) -> Tuple[str, List[str]]:
    card = art.cards.get(symbol)
    if card is None:
        return (
            f"Unknown in the artifacts: there is no trade card for "
            f"{symbol} in this run.",
            [],
        )
    sources = [f"card:{symbol}"]
    bits: List[str] = []
    if card.get("kind") != "trade":
        rejection = card.get("rejection") or {}
        bits.append(
            f"The {symbol} card is a no-trade (verdict "
            f"{card.get('verdict')}): {rejection.get('reason') or 'no reason recorded'}."
        )
    else:
        levels = card.get("levels") or {}
        bits.append(
            f"The {symbol} card is a live {card.get('direction')} idea "
            f"(conviction {card.get('conviction')}/10): entry "
            f"{levels.get('entry')}, stop {levels.get('stop')}, target "
            f"{levels.get('target')}. A move through the stop is what "
            "invalidates the entry thesis on the card's own levels."
        )
    debate = art.debates.get(symbol)
    if debate and (debate.get("judge") or {}).get("biggest_risk"):
        bits.append(f"Judge's biggest risk: {debate['judge']['biggest_risk']}")
        sources.append(f"debate:{symbol}")
    failed = [c for c in card.get("checks") or [] if c.get("passed") is False]
    if failed:
        named = "; ".join(
            f"{c.get('check')} - {c.get('detail')}" for c in failed[:3]
        )
        bits.append(f"Failed checks on the card: {named}.")
    unknown = [c for c in card.get("checks") or [] if c.get("passed") is None]
    if unknown:
        named = ", ".join(c.get("check") for c in unknown[:4])
        bits.append(f"Checks the packet could not score: {named}.")
    return " ".join(bits), sources


def _card_summary(symbol: str, art: _Artifacts) -> Tuple[str, List[str]]:
    card = art.cards.get(symbol)
    if card is None:
        return (
            f"Unknown in the artifacts: there is no trade card for "
            f"{symbol} in this run.",
            [],
        )
    bits = [
        f"{symbol} card: {card.get('kind')}, verdict {card.get('verdict')}, "
        f"direction {card.get('direction')}, conviction "
        f"{card.get('conviction')}/10."
    ]
    contract = card.get("contract")
    if contract:
        bits.append(
            f"Contract {contract.get('contract_symbol')}, strike "
            f"{contract.get('strike')}, premium {contract.get('premium')}."
        )
    if card.get("why"):
        bits.append(f"Why: {card['why']}")
    return " ".join(bits), [f"card:{symbol}"]


def _hit_rate(art: _Artifacts) -> Tuple[str, List[str]]:
    stats = art.stats
    if not stats:
        return (
            "Unknown in the artifacts: this run carries no journal stats.",
            [],
        )
    if stats.get("hit_rate") is None:
        return (
            f"The journal holds {stats.get('entries', 0)} entries and none "
            "are scored yet, so the hit rate is unknown - not zero.",
            ["journal_stats"],
        )
    hits = stats.get("hits", 0)
    losses = stats.get("losses", 0)
    return (
        f"The journal holds {stats.get('entries', 0)} entries; "
        f"{stats.get('scored_entries', 0)} are scored with a latest "
        f"outcome: {hits} {'hit' if hits == 1 else 'hits'} and "
        f"{losses} {'loss' if losses == 1 else 'losses'}, a hit rate of "
        f"{stats['hit_rate'] * 100:.1f}%.",
        ["journal_stats"],
    )


def _iv_rank(symbol: str, art: _Artifacts) -> Tuple[str, List[str]]:
    packet = art.packets.get(symbol)
    events = (packet or {}).get("events")
    if not events:
        return (
            f"Unknown in the artifacts: no packet events section for "
            f"{symbol} in this run.",
            [],
        )
    rank = (events.get("iv") or {}).get("rank_pct")
    if rank is None:
        return (
            f"Unknown in the artifacts: {symbol}'s IV rank is not "
            f"available - the packet reports no 52-week IV range. "
            f"Packet one-liner: {events.get('one_liner')}",
            [f"packet:{symbol}"],
        )
    return (
        f"{symbol}'s IV rank is {rank} in the packet "
        f"(red flag: {events.get('red_flag')}). "
        f"One-liner: {events.get('one_liner')}",
        [f"packet:{symbol}"],
    )


def _board_summary(art: _Artifacts) -> Tuple[str, List[str]]:
    if not art.board_rows:
        return ("Unknown in the artifacts: this run has no board.", [])
    rows = sorted(art.board_rows.values(), key=lambda r: r.get("rank", 99))
    top = ", ".join(
        f"{r.get('ticker')} #{r.get('rank')} at {float(r.get('score', 0.0)):.2f} "
        f"({r.get('direction')})"
        for r in rows[:3]
    )
    bottom = rows[-1]
    return (
        f"The board ranks {art.board_count} names. Top of the board: "
        f"{top}. Bottom: {bottom.get('ticker')} at "
        f"{float(bottom.get('score', 0.0)):.2f} ({bottom.get('direction')}).",
        ["board"],
    )


def _xray_summary(art: _Artifacts) -> Tuple[str, List[str]]:
    if not art.xray:
        return ("Unknown in the artifacts: this run has no X-Ray.", [])
    read = art.xray.get("read") or {}
    counts = (art.xray.get("breadth") or {}).get("counts") or {}
    return (
        f"Market posture is {read.get('posture')}: breadth "
        f"{counts.get('bullish', '?')} bullish / {counts.get('neutral', '?')} "
        f"neutral / {counts.get('bearish', '?')} bearish, with "
        f"{read.get('pct_above_200dma', 'unknown')}% of the watchlist above "
        f"the 200DMA. Leading sectors: "
        f"{', '.join(read.get('leading_sectors') or []) or 'none recorded'}. "
        f"Lagging: {', '.join(read.get('lagging_sectors') or []) or 'none recorded'}.",
        ["xray"],
    )


def _digest(symbol: str, art: _Artifacts) -> Tuple[str, List[str]]:
    bits: List[str] = []
    sources: List[str] = []
    if symbol in art.board_rows:
        text, src = _board_why(symbol, art)
        bits.append(text)
        sources += src
    if symbol in art.cards:
        text, src = _card_summary(symbol, art)
        bits.append(text)
        sources += src
    if not bits:
        return (
            f"Unknown in the artifacts: {symbol} appears in this run's "
            "watchlist context but carries no board row or card here.",
            [],
        )
    return " ".join(bits), sources


def _fallback_answer(
    question: str, art: _Artifacts, symbol: Optional[str]
) -> Tuple[str, List[str], bool]:
    """Deterministic extraction. Returns (answer, sources, unknown)."""
    lower = question.lower()
    if any(word in lower for word in _HIT_RATE_WORDS):
        text, sources = _hit_rate(art)
        return text, sources, not sources
    if "iv rank" in lower or "implied vol" in lower:
        if symbol:
            text, sources = _iv_rank(symbol, art)
            events = (art.packets.get(symbol) or {}).get("events") or {}
            rank = (events.get("iv") or {}).get("rank_pct")
            # The packet is the source either way; the VALUE is the
            # unknown when no rank was computed.
            return text, sources, rank is None
    if symbol and any(w in lower for w in ("fail", "invalidate", "go wrong", "risk")):
        text, sources = _card_fail(symbol, art)
        return text, sources, not sources
    if symbol and ("rank" in lower or "first" in lower or "top" in lower):
        text, sources = _board_why(symbol, art)
        return text, sources, not sources
    if symbol and "why" in lower:
        debate = art.debates.get(symbol)
        if debate and debate.get("why"):
            return (
                f"{debate['why']}",
                [f"debate:{symbol}"] + ([f"board:{symbol}"] if symbol in art.board_rows else []),
                False,
            )
        text, sources = _board_why(symbol, art)
        return text, sources, not sources
    if symbol and ("card" in lower or "trade" in lower):
        text, sources = _card_summary(symbol, art)
        return text, sources, not sources
    if any(w in lower for w in ("posture", "breadth", "sector", "market", "risk on", "risk off")):
        text, sources = _xray_summary(art)
        return text, sources, not sources
    if any(w in lower for w in ("board", "ranking", "ranked", "bullish", "bearish")):
        text, sources = _board_summary(art)
        return text, sources, not sources
    if symbol:
        text, sources = _digest(symbol, art)
        return text, sources, not sources
    cards = list(art.cards.values())
    trades = sum(1 for c in cards if c.get("kind") == "trade")
    return (
        f"This run's artifacts hold a {art.board_count}-name liquidity "
        f"board, {len(cards)} trade cards ({trades} trade / "
        f"{len(cards) - trades} no-trade) and journal stats over "
        f"{(art.stats or {}).get('entries', 0)} entries. Ask about a "
        "symbol's ranking, a card's risk, the market posture, or the "
        "journal's hit rate.",
        ["board", "cards"],
        False,
    )


# ----------------------------------------------------------------------
# LLM composition path
# ----------------------------------------------------------------------
def _evidence_bundle(art: _Artifacts) -> Dict:
    """Trimmed artifacts JSON for the LLM prompt (no raw bar dumps)."""
    bundle: Dict = {}
    if art.board_rows:
        bundle["board"] = [
            art.board_rows[t] for t in sorted(
                art.board_rows, key=lambda t: art.board_rows[t].get("rank", 99)
            )
        ]
    if art.xray:
        bundle["xray_read"] = art.xray.get("read")
        bundle["xray_counts"] = (art.xray.get("breadth") or {}).get("counts")
        sectors = (art.xray.get("sectors") or {}).get("sectors") or []
        bundle["sectors_top3"] = sectors[:3]
        bundle["sectors_bottom3"] = sectors[-3:]
    if art.cards:
        bundle["cards"] = list(art.cards.values())
    if art.stats:
        bundle["journal"] = art.stats
    packets: Dict[str, Dict] = {}
    for symbol, packet in art.packets.items():
        liquidity = packet.get("liquidity") or {}
        indicators = packet.get("indicators") or {}
        packets[symbol] = {
            "spot": packet.get("spot"),
            "as_of": packet.get("as_of"),
            "liquidity_score": liquidity.get("score"),
            "liquidity_direction": liquidity.get("direction"),
            "liquidity_components": liquidity.get("components"),
            "regime": indicators.get("regime"),
            "long_filter": indicators.get("long_filter"),
            "events": packet.get("events"),
            "data_quality": packet.get("data_quality"),
        }
    if packets:
        bundle["packets"] = packets
    debates: Dict[str, Dict] = {}
    for symbol, debate in art.debates.items():
        debates[symbol] = {
            "verdict": debate.get("verdict"),
            "conviction": debate.get("conviction"),
            "direction": debate.get("direction"),
            "why": debate.get("why"),
            "judge": debate.get("judge"),
            "looped": debate.get("looped"),
            "gap_history": debate.get("gap_history"),
        }
    if debates:
        bundle["debates"] = debates
    return bundle


def _llm_answer(
    question: str,
    art: _Artifacts,
    client,
    model: Optional[str],
    max_tokens: int,
) -> Tuple[Optional[str], Optional[str]]:
    """(answer, rejection reason). The answer is None when the model
    failed, replied empty, or wrote a number or citation that does not
    trace to the evidence bundle - the extractive path answers then."""
    bundle = _evidence_bundle(art)
    prompt = f"""You are Ask QuantPilot, the explanation layer of an options research agent. Answer the user's question using ONLY the evidence bundle below - it plays the role of the evidence packet in the grounding rules.

{GROUNDING_RULES}

Answer in 2-5 plain sentences. Cite the evidence value behind every number. If the evidence does not contain the answer, say "unknown in the artifacts" and name what is missing. Never give personal financial advice and never recommend a trade to the user - you explain the agent's own artifacts.

QUESTION: {question}

EVIDENCE (JSON):
{json.dumps(bundle, indent=1, sort_keys=True, default=str)}"""
    try:
        text = client.chat_text(prompt, model=model, max_tokens=max_tokens)
    except Exception as exc:
        return None, f"llm call failed: {type(exc).__name__}"
    text = (text or "").strip()
    if not text:
        return None, "llm reply was empty"
    # Numbers the user typed are fair to repeat; everything else must
    # trace to the bundle.
    report = grounding_report(text, bundle, allow=_question_numbers(question))
    bad = [c for c in report["citations"] if not is_verified(c)]
    if report["unsupported_numbers"] or bad:
        reasons = []
        if report["unsupported_numbers"]:
            reasons.append(
                "numbers not in the artifacts: "
                + ", ".join(report["unsupported_numbers"][:5])
            )
        if bad:
            reasons.append(
                "citations that do not verify: "
                + ", ".join(f"[{c['path']} = {c['stated']}]" for c in bad[:3])
            )
        return None, "llm answer rejected - " + "; ".join(reasons)
    return text, None


def _question_numbers(question: str) -> List[float]:
    out = []
    for token in re.findall(r"\d+(?:\.\d+)?", question or ""):
        try:
            out.append(float(token))
        except ValueError:
            continue
    return out


# ----------------------------------------------------------------------
# the brain
# ----------------------------------------------------------------------
ADVICE_REFUSAL = (
    "That is personal financial advice, which is out of scope for this "
    "layer. I explain QuantPilot's own run artifacts - board rankings, "
    "trade cards, debate verdicts, journal stats - and I do not "
    "recommend trades for anyone's money."
)


def answer_question(
    question: str,
    artifacts: Optional[Dict],
    llm_client=None,
    model: Optional[str] = None,
    max_tokens: int = 2048,
) -> Dict:
    """Answer one question from one run's artifacts.

    Returns {"question", "answer", "mode", "refused", "unknown",
    "sources", "llm_rejected"}: mode is "llm" or "fallback"; an LLM
    answer that does not verify against the artifacts is replaced by
    the extractive answer and llm_rejected says why; refused marks the
    deterministic scope gate; unknown marks an honest "not in the
    artifacts" answer. The scope gate runs BEFORE any LLM call and
    the LLM path never overrides it.
    """
    art = _Artifacts(artifacts)
    question = (question or "").strip()
    result: Dict = {
        "question": question,
        "answer": "",
        "mode": "fallback",
        "refused": False,
        "unknown": False,
        "sources": [],
        "llm_rejected": None,
    }
    lower = question.lower()
    if any(pattern in lower for pattern in _ADVICE_PATTERNS):
        result["answer"] = ADVICE_REFUSAL
        result["refused"] = True
        return result

    symbol, absent = _extract_symbols(question, art)
    if absent is not None:
        if absent in config.WATCHLIST:
            result["answer"] = (
                f"Unknown in the artifacts: {absent} is on the watchlist "
                "but has no board row, card, packet or debate in this "
                "run, so there is no evidence to answer from."
            )
        else:
            result["answer"] = (
                f"{absent} is outside QuantPilot's watchlist and this "
                "run's artifacts, so I have no evidence to answer from."
            )
            result["refused"] = absent not in config.WATCHLIST
        result["unknown"] = True
        return result

    fallback_text, sources, unknown = _fallback_answer(question, art, symbol)
    if llm_client is not None and not unknown:
        composed, rejected = _llm_answer(
            question, art, llm_client, model, max_tokens
        )
        result["llm_rejected"] = rejected
        if composed:
            result.update(
                answer=composed, mode="llm", sources=sources, unknown=False
            )
            return result
    result.update(answer=fallback_text, sources=sources, unknown=unknown)
    return result
