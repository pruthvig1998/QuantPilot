"""Morning briefing generator (build plan module 4, output side).

Composes the full morning briefing from one run's module outputs:
the Market X-Ray read, the ranked liquidity board, the day's trade
cards (built from the debate verdicts), the IV/event one-liners
from the packets, and the journal stats with the 2-loss circuit
breaker line when it has tripped.

Pure composition: every input is an artifact produced elsewhere
(xray.market_xray, board.build_board, cards.build_card output,
packet dicts, journal.stats). No provider calls, no LLM calls -
what is not in the inputs is reported as unavailable, never
invented.

Format contract (the user's standing Discord style, non-negotiable):
- plain text, short scannable sections, short labels
- NO emojis; direction glyphs are the arrows only
- every price carries its session tag: (premarket) / (live) /
  (after-hours) / (close). The session is computed from the run's
  as_of on the America/New_York clock unless an artifact or the
  caller states one explicitly.
- exactly one footer line: "Educational only - not financial advice."

The same sections also render as Markdown (repo samples / README):
generate_briefing returns {"text", "markdown", "as_of", "session"}.

US markets only.
"""
from __future__ import annotations

import textwrap
from datetime import datetime, time, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

FOOTER = "Educational only - not financial advice."

SESSION_PREMARKET = "premarket"
SESSION_LIVE = "live"
SESSION_AFTER_HOURS = "after-hours"
SESSION_CLOSE = "close"


# ----------------------------------------------------------------------
# formatting helpers (shared with the dashboard)
# ----------------------------------------------------------------------
def as_datetime(value) -> datetime:
    """Normalize epoch / ISO string / datetime to an aware UTC datetime."""
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def session_label(as_of=None, explicit: Optional[str] = None) -> str:
    """Market session for a timestamp, on the ET clock.

    premarket 04:00-09:30, live 09:30-16:00, after-hours
    16:00-20:00 on weekdays; everything else (overnight, weekends)
    is the close - the last price printed is a closing price.
    An explicit label (from an artifact or the caller) always wins.
    """
    if explicit:
        return str(explicit)
    local = as_datetime(as_of).astimezone(ET)
    if local.weekday() >= 5:
        return SESSION_CLOSE
    t = local.time()
    if time(4, 0) <= t < time(9, 30):
        return SESSION_PREMARKET
    if time(9, 30) <= t < time(16, 0):
        return SESSION_LIVE
    if time(16, 0) <= t < time(20, 0):
        return SESSION_AFTER_HOURS
    return SESSION_CLOSE


def fmt_price(value) -> str:
    """$248.30 - or "unknown" for a missing value (never invented)."""
    if value is None:
        return "unknown"
    return f"${float(value):,.2f}"


def fmt_price_tagged(value, session: str) -> str:
    """A price with its session tag: $248.30 (premarket)."""
    if value is None:
        return "unknown"
    return f"{fmt_price(value)} ({session})"


def fmt_pct(value, signed: bool = True) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):+.2f}%" if signed else f"{float(value):.2f}%"


def fmt_signed(value, digits: int = 2) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):+.{digits}f}"


def arrow_for(change_pct) -> str:
    """The only direction glyphs allowed: up, down, flat arrows."""
    if change_pct is None:
        return "→"
    value = float(change_pct)
    if value > 0:
        return "↑"
    if value < 0:
        return "↓"
    return "→"


def _truncate(text: str, limit: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _date_title(as_of) -> str:
    local = as_datetime(as_of).astimezone(ET)
    return local.strftime("%a %b %d, %Y")


def _time_title(as_of) -> str:
    local = as_datetime(as_of).astimezone(ET)
    return local.strftime("%I:%M %p ET").lstrip("0")


def _expiry_label(contract: Dict) -> str:
    """Contract expiry as a date + DTE, from the card's own fields."""
    exp = contract.get("expiration")
    dte = contract.get("days_to_expiry")
    if exp is None:
        return "expiry unknown"
    day = as_datetime(exp).date().isoformat()
    if dte is None:
        return f"exp {day}"
    return f"exp {day} ({dte} DTE)"


# ----------------------------------------------------------------------
# section builders: each returns (title, text lines, markdown lines)
# ----------------------------------------------------------------------
def _section_xray(xray: Optional[Dict], session: str) -> Tuple[str, List[str], List[str]]:
    title = "MARKET X-RAY"
    if not xray:
        lines = ["X-Ray unavailable in this run's artifacts."]
        return title, lines, list(lines)
    read = xray.get("read") or {}
    counts = (xray.get("breadth") or {}).get("counts") or {}
    posture = str(read.get("posture") or "unknown").replace("_", " ").upper()
    text = [
        f"Posture: {posture} - breadth {read.get('bullish_share_pct', 'unknown')}% "
        f"bullish / {read.get('bearish_share_pct', 'unknown')}% bearish; "
        f"{read.get('pct_above_200dma', 'unknown')}% of the watchlist above the 200DMA",
        f"Breadth: {counts.get('bullish', '?')} bullish / "
        f"{counts.get('neutral', '?')} neutral / {counts.get('bearish', '?')} "
        f"bearish of {counts.get('total', '?')} "
        f"(stacks {counts.get('bullish_stack', '?')} up / "
        f"{counts.get('bearish_stack', '?')} down; RSI "
        f"{counts.get('rsi_overbought', '?')} overbought / "
        f"{counts.get('rsi_oversold', '?')} oversold)",
    ]
    leading = read.get("leading_sectors") or []
    lagging = read.get("lagging_sectors") or []
    if leading:
        text.append("Leading sectors: " + ", ".join(leading))
    if lagging:
        text.append("Lagging sectors: " + ", ".join(lagging))
    sectors = (xray.get("sectors") or {}).get("sectors") or []
    if sectors:
        top = sectors[0]
        text.append(
            f"Top sector: {top.get('sector')} ({top.get('ticker')}) "
            f"{fmt_price_tagged(top.get('price'), session)} - momentum "
            f"{fmt_signed(top.get('momentum_score'))}, RS vs SPY "
            f"{fmt_pct(top.get('rs_21d_pct'))}"
        )
        bottom = sectors[-1]
        if bottom is not top:
            text.append(
                f"Weakest sector: {bottom.get('sector')} ({bottom.get('ticker')}) "
                f"{fmt_price_tagged(bottom.get('price'), session)} - momentum "
                f"{fmt_signed(bottom.get('momentum_score'))}, RS vs SPY "
                f"{fmt_pct(bottom.get('rs_21d_pct'))}"
            )
    errors = (xray.get("breadth") or {}).get("errors") or []
    for err in errors:
        text.append(f"No breadth data: {err.get('ticker')} ({_truncate(err.get('error', ''), 60)})")
    md = [f"- {line}" for line in text]
    return title, text, md


def _board_row_text(row: Dict, session: str) -> str:
    comp = row.get("components") or {}
    inputs = row.get("inputs") or {}
    return (
        f"{row.get('rank', '?')}. {row.get('ticker')} "
        f"{fmt_price_tagged(row.get('price'), session)} "
        f"{arrow_for(inputs.get('change_pct'))} {fmt_pct(inputs.get('change_pct'))} day "
        f"| score {float(row.get('score', 0.0)):.1f} {row.get('direction')} "
        f"| OI {fmt_signed(comp.get('options_oi'))}, "
        f"opt vol {fmt_signed(comp.get('options_volume'))}, "
        f"mom {fmt_signed(comp.get('momentum'))}, "
        f"relvol {fmt_signed(comp.get('relative_volume'))} "
        f"| RV {inputs.get('relative_volume', 'unknown')}"
    )


def _section_board(board: Optional[Dict], session: str) -> Tuple[str, List[str], List[str]]:
    title = "LIQUIDITY BOARD"
    if not board or not board.get("board"):
        lines = ["Board unavailable in this run's artifacts."]
        if board and board.get("errors"):
            lines += [
                f"No data: {e.get('ticker')} ({_truncate(e.get('error', ''), 60)})"
                for e in board["errors"]
            ]
        return title, lines, list(lines)
    rows = board["board"]
    bullish = [r for r in rows if r.get("direction") == "bullish"]
    bearish = [r for r in rows if r.get("direction") == "bearish"]
    choppy = [r for r in rows if r.get("direction") not in ("bullish", "bearish")]

    text: List[str] = []
    if bullish:
        text.append("Top bullish:")
        text += [_board_row_text(r, session) for r in bullish]
    if bearish:
        text.append("Bearish:")
        text += [_board_row_text(r, session) for r in bearish]
    if choppy:
        names = ", ".join(
            f"{r.get('ticker')} (score {float(r.get('score', 0.0)):.1f})"
            for r in choppy
        )
        text.append(f"Choppy / no read: {names}")
    if not bullish and not bearish:
        text.append("No bullish or bearish reads on the board today.")
    for err in board.get("errors") or []:
        text.append(f"No data: {err.get('ticker')} ({_truncate(err.get('error', ''), 60)})")

    md = [
        "| Rank | Ticker | Price | Day % | Score | Direction | OI | Opt vol | Mom | Relvol |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        comp = row.get("components") or {}
        inputs = row.get("inputs") or {}
        md.append(
            f"| {row.get('rank', '?')} | {row.get('ticker')} | "
            f"{fmt_price_tagged(row.get('price'), session)} | "
            f"{fmt_pct(inputs.get('change_pct'))} | "
            f"{float(row.get('score', 0.0)):.1f} | {row.get('direction')} | "
            f"{fmt_signed(comp.get('options_oi'))} | "
            f"{fmt_signed(comp.get('options_volume'))} | "
            f"{fmt_signed(comp.get('momentum'))} | "
            f"{fmt_signed(comp.get('relative_volume'))} |"
        )
    md += [line for line in text if line.startswith(("Choppy", "No data", "No bullish"))]
    return title, text, md


def _checks_summary_lines(card: Dict) -> List[str]:
    checks = card.get("checks") or []
    if not checks:
        return ["Checks: none recorded on this card."]
    passed = [c for c in checks if c.get("passed") is True]
    failed = [c for c in checks if c.get("passed") is False]
    unknown = [c for c in checks if c.get("passed") is None]
    lines = [
        f"Checks: {len(passed)} passed / {len(failed)} failed / "
        f"{len(unknown)} unknown of {len(checks)}"
    ]
    for check in failed[:3]:
        lines.append(
            f"  failed: {check.get('check')} ({check.get('source')}) - "
            f"{_truncate(check.get('detail', ''))}"
        )
    for check in unknown[:2]:
        lines.append(
            f"  unknown: {check.get('check')} ({check.get('source')}) - "
            f"{_truncate(check.get('detail', ''))}"
        )
    return lines


def _card_block(card: Dict, session: str, wrap: int = 0) -> List[str]:
    symbol = card.get("symbol")
    verdict = card.get("verdict")
    kind = card.get("kind")
    lines: List[str] = []
    if kind == "trade":
        lines.append(
            f"{symbol} - TRADE {card.get('direction')} | conviction "
            f"{card.get('conviction')}/10"
        )
    else:
        lines.append(f"{symbol} - {verdict} (no trade)")
    if card.get("downgraded"):
        lines.append(f"DOWNGRADED: {_truncate(card.get('downgrade_reason') or '', 160)}")
    contract = card.get("contract")
    if contract:
        label = "Contract" if kind == "trade" else "Nearest candidate"
        lines.append(
            f"{label}: {contract.get('contract_symbol')} "
            f"{contract.get('option_type')}, strike "
            f"{fmt_price(contract.get('strike'))}, "
            f"{_expiry_label(contract)}, premium "
            f"{fmt_price_tagged(contract.get('premium'), session)}"
        )
    levels = card.get("levels") or {}
    lines.append(
        f"Levels: spot {fmt_price_tagged(levels.get('spot'), session)} | "
        f"entry {fmt_price(levels.get('entry'))} | "
        f"stop {fmt_price(levels.get('stop'))} | "
        f"target {fmt_price(levels.get('target'))} "
        f"({levels.get('target_source') or 'no target in packet'})"
    )
    sizing = card.get("sizing") or {}
    if kind == "trade":
        contracts = sizing.get("contracts", 0)
        noun = "contract" if contracts == 1 else "contracts"
        lines.append(
            f"Size: {contracts} {noun} | premium outlay "
            f"{fmt_price(sizing.get('premium_outlay_usd'))} | risk budget "
            f"{fmt_price(sizing.get('risk_budget_usd'))} "
            f"({float(sizing.get('risk_pct') or 0) * 100:.0f}% of "
            f"{fmt_price(sizing.get('account_size_usd'))})"
        )
    greeks = (card.get("greeks_plain") or {}).get("line")
    if greeks:
        lines.append(f"Greeks: {greeks}")
    sector = (card.get("sector_context") or {}).get("line")
    if sector:
        lines.append(f"Sector: {sector}")
    review = (card.get("risk_review") or {}).get("line")
    if review:
        lines.append(_truncate(review, 240))
    if card.get("why"):
        why = " ".join(str(card["why"]).split())
        if wrap:
            why = "\n".join(
                textwrap.wrap(why, width=wrap, initial_indent="Why: ",
                              subsequent_indent="  ")
            )
            lines.append(why)
        else:
            lines.append(f"Why: {why}")
    rejection = card.get("rejection")
    if kind != "trade" and rejection:
        lines.append(f"Reason: {_truncate(rejection.get('reason') or '', 220)}")
    lines += _checks_summary_lines(card)
    return lines


def _section_cards(
    cards: Optional[List[Dict]], session: str
) -> Tuple[str, List[str], List[str]]:
    title = "TRADE CARDS"
    if not cards:
        lines = ["No trade cards in this run."]
        return title, lines, list(lines)
    text: List[str] = []
    md: List[str] = []
    for index, card in enumerate(cards):
        if index:
            text.append("")
            md.append("")
        block = _card_block(card, session, wrap=100)
        text += block
        md_block = _card_block(card, session, wrap=0)
        md.append(f"### {md_block[0]}")
        md += [f"- {line}" for line in md_block[1:]]
    return title, text, md


def _section_events(
    packets: Optional[Dict[str, Dict]]
) -> Tuple[str, List[str], List[str]]:
    title = "RISK FLAGS"
    if not packets:
        lines = ["Risk flags unavailable - no packets in this run."]
        return title, lines, list(lines)
    red: List[str] = []
    plain: List[str] = []
    market_events: Dict[Tuple[str, str], Dict] = {}
    for symbol in sorted(packets):
        packet = packets[symbol] or {}
        events = packet.get("events")
        if not events:
            continue
        one_liner = events.get("one_liner")
        if one_liner:
            if events.get("red_flag"):
                red.append(f"RED FLAG: {one_liner}")
            else:
                plain.append(one_liner)
        for event in events.get("market_events_in_window") or []:
            market_events.setdefault((event.get("type"), event.get("date")), event)
    lines = red + plain
    if market_events:
        ordered = sorted(
            market_events.values(), key=lambda e: e.get("days_away", 0)
        )
        summary = ", ".join(
            f"{e.get('type')} {e.get('date')} (in {e.get('days_away')}d)"
            for e in ordered
        )
        lines.append(f"Market events inside the holding window: {summary}")
    if not lines:
        lines = ["No event flags in this run's packets."]
    return title, lines, [f"- {line}" for line in lines]


def _section_journal(
    stats: Optional[Dict]
) -> Tuple[str, List[str], List[str]]:
    title = "JOURNAL"
    if not stats:
        lines = ["Journal stats unavailable in this run."]
        return title, lines, list(lines)
    hit_rate = stats.get("hit_rate")
    hit_line = (
        f"hit rate {hit_rate * 100:.1f}%" if hit_rate is not None
        else "hit rate unknown (nothing scored yet)"
    )
    lines = [
        f"Entries: {stats.get('entries', 0)} | scored: "
        f"{stats.get('scored_entries', 0)} | hits {stats.get('hits', 0)} / "
        f"losses {stats.get('losses', 0)} | {hit_line}"
    ]
    for verdict in sorted(stats.get("by_verdict") or {}):
        bucket = stats["by_verdict"][verdict]
        rate = bucket.get("hit_rate")
        rate_text = f"{rate * 100:.1f}%" if rate is not None else "unknown"
        lines.append(
            f"{verdict}: {bucket.get('scored', 0)} scored, "
            f"{bucket.get('hits', 0)} hits, hit rate {rate_text}"
        )
    breaker = stats.get("breaker") or {}
    if breaker.get("tripped"):
        lines.append(breaker.get("line") or "CIRCUIT BREAKER: tripped.")
    return title, lines, [f"- {line}" for line in lines]


# ----------------------------------------------------------------------
# composition
# ----------------------------------------------------------------------
def _normalize_packets(packets) -> Dict[str, Dict]:
    if not packets:
        return {}
    if isinstance(packets, dict):
        return packets
    return {p.get("symbol"): p for p in packets if isinstance(p, dict)}


def generate_briefing(
    xray: Optional[Dict] = None,
    board: Optional[Dict] = None,
    cards: Optional[List[Dict]] = None,
    packets=None,
    journal_stats: Optional[Dict] = None,
    as_of=None,
    session: Optional[str] = None,
    run_errors: Optional[List[Dict]] = None,
) -> Dict:
    """Compose the morning briefing from one run's module outputs.

    Returns {"text", "markdown", "as_of", "session"}. Sections
    whose inputs were not supplied say so instead of guessing.
    """
    when = as_datetime(as_of)
    session_name = session_label(when, explicit=session)
    packet_map = _normalize_packets(packets)

    sections = [
        _section_xray(xray, session_name),
        _section_board(board, session_name),
        _section_cards(cards, session_name),
        _section_events(packet_map),
        _section_journal(journal_stats),
    ]
    if run_errors:
        err_lines = [
            f"{e.get('symbol') or e.get('stage')}: {e.get('stage')} failed - "
            f"{_truncate(str(e.get('error')), 160)}"
            for e in run_errors
        ]
        sections.append(("NOT COMPLETED THIS RUN", err_lines, [f"- {l}" for l in err_lines]))

    text_parts = [
        "QUANTPILOT MORNING BRIEFING",
        f"{_date_title(when)} - as of {_time_title(when)} ({session_name})",
    ]
    for title, text_lines, _ in sections:
        text_parts.append("")
        text_parts.append(title)
        text_parts += text_lines
    text_parts.append("")
    text_parts.append(FOOTER)
    text = "\n".join(text_parts) + "\n"

    md_parts = [
        f"# QuantPilot Morning Briefing - {_date_title(when)}",
        f"As of {_time_title(when)} ({session_name})",
    ]
    for title, _, md_lines in sections:
        md_parts.append("")
        md_parts.append(f"## {title.title()}")
        md_parts += md_lines
    md_parts.append("")
    md_parts.append(FOOTER)
    markdown = "\n".join(md_parts) + "\n"

    return {
        "text": text,
        "markdown": markdown,
        "as_of": when.isoformat(),
        "session": session_name,
    }


def briefing_from_artifacts(artifacts: Dict) -> Dict:
    """generate_briefing over a runner-style artifacts bundle."""
    return generate_briefing(
        xray=artifacts.get("xray"),
        board=artifacts.get("board"),
        cards=artifacts.get("cards"),
        packets=artifacts.get("packets"),
        journal_stats=artifacts.get("journal_stats"),
        as_of=artifacts.get("as_of"),
        session=artifacts.get("session"),
    )
