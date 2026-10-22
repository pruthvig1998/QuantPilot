"""Judges dashboard (Day 4 drop): one self-contained HTML page.

render_dashboard(run) turns one morning run's artifacts into a
single static HTML file - no external assets, inline CSS, dark
theme - that the demo video walks through:

- Market X-Ray snapshot (posture, breadth counts, sector table)
- the ranked liquidity board with all four component scores
- every trade card with its FULL checks list (passed / failed /
  unknown visibly distinct - the card shows its own working)
- one full debate run: the looped run when the run has one (both
  rounds, bull, bear, judge, the Evaluator's gap and the loop-back
  made visible), else the first debated symbol
- journal stats and the circuit-breaker state

Every interpolated value is HTML-escaped and formatted from the
artifacts - nothing is invented to fill the page. US markets only.
"""
from __future__ import annotations

import html
import os
from typing import Dict, List, Optional, Tuple

from .briefing import fmt_pct, fmt_price, fmt_price_tagged, fmt_signed, session_label

_CSS = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; background: #0b0f14; color: #dbe4ec;
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px; line-height: 1.45; }
.wrap { max-width: 1180px; margin: 0 auto; padding: 28px 22px 48px; }
header h1 { margin: 0 0 4px; font-size: 30px; letter-spacing: .5px; }
header .sub { color: #8fa3b8; margin-bottom: 6px; }
.panel { background: #12181f; border: 1px solid #22303c; border-radius: 10px;
  padding: 18px 20px; margin: 18px 0; }
.panel h2 { margin: 0 0 12px; font-size: 21px; color: #e8f1f8;
  border-bottom: 1px solid #22303c; padding-bottom: 8px; }
.panel h3 { margin: 16px 0 8px; font-size: 17px; color: #cfe0ee; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 4px; }
th, td { text-align: left; padding: 6px 9px; border-bottom: 1px solid #1d2833;
  font-size: 14.5px; vertical-align: top; }
th { color: #8fa3b8; font-weight: 600; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 700; letter-spacing: .4px; }
.pill.pass { background: #12351c; color: #3fb950; border: 1px solid #3fb950; }
.pill.fail { background: #3d1417; color: #f85149; border: 1px solid #f85149; }
.pill.unknown { background: #33270e; color: #d29922; border: 1px solid #d29922; }
.pill.trade { background: #12351c; color: #3fb950; border: 1px solid #3fb950; }
.pill.watch { background: #33270e; color: #d29922; border: 1px solid #d29922; }
.pill.skip { background: #262b31; color: #9aa7b1; border: 1px solid #57606a; }
.pill.posture { background: #0f2c44; color: #4cc2ff; border: 1px solid #4cc2ff; }
.grid { display: flex; flex-wrap: wrap; gap: 12px; }
.stat { background: #0d141b; border: 1px solid #22303c; border-radius: 8px;
  padding: 10px 14px; min-width: 130px; }
.stat .k { color: #8fa3b8; font-size: 12.5px; text-transform: uppercase;
  letter-spacing: .6px; }
.stat .v { font-size: 21px; font-weight: 650; margin-top: 2px; }
.muted { color: #8fa3b8; }
.why { background: #0d141b; border-left: 3px solid #4cc2ff; padding: 10px 14px;
  border-radius: 0 8px 8px 0; margin: 10px 0; }
.gapbox { background: #33270e33; border-left: 3px solid #d29922;
  padding: 10px 14px; border-radius: 0 8px 8px 0; margin: 10px 0; }
.casebox { background: #0d141b; border: 1px solid #22303c; border-radius: 8px;
  padding: 10px 14px; margin: 8px 0; }
.casebox .who { font-weight: 700; color: #4cc2ff; margin-bottom: 4px; }
.breaker-on { background: #3d1417; border: 1px solid #f85149; color: #ffb4ae;
  border-radius: 8px; padding: 12px 16px; font-weight: 650; margin-top: 12px; }
.breaker-off { color: #8fa3b8; margin-top: 12px; }
.redflag { color: #f85149; font-weight: 650; }
footer { color: #8fa3b8; margin-top: 26px; font-size: 14px; }
"""


def esc(value) -> str:
    """HTML-escape any artifact value (None becomes an empty cell)."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _pill(passed: Optional[bool]) -> str:
    if passed is True:
        return '<span class="pill pass">PASS</span>'
    if passed is False:
        return '<span class="pill fail">FAIL</span>'
    return '<span class="pill unknown">UNKNOWN</span>'


def _verdict_pill(verdict: Optional[str]) -> str:
    cls = {"TRADE": "trade", "WATCH": "watch", "SKIP": "skip"}.get(
        str(verdict or "").upper(), "skip"
    )
    return f'<span class="pill {cls}">{esc(verdict or "unknown")}</span>'


# ----------------------------------------------------------------------
# sections
# ----------------------------------------------------------------------
def _section_xray(run: Dict, session: str) -> str:
    xray = run.get("xray")
    if not xray:
        return '<section class="panel"><h2>Market X-Ray</h2>' \
            '<p class="muted">Unavailable in this run.</p></section>'
    read = xray.get("read") or {}
    counts = (xray.get("breadth") or {}).get("counts") or {}
    posture = str(read.get("posture") or "unknown").replace("_", " ").upper()
    stats = [
        ("Posture", posture),
        ("Bullish", counts.get("bullish", "?")),
        ("Neutral", counts.get("neutral", "?")),
        ("Bearish", counts.get("bearish", "?")),
        ("Above 200DMA", f"{read.get('pct_above_200dma', '?')}%"),
        ("RSI overbought", counts.get("rsi_overbought", "?")),
        ("RSI oversold", counts.get("rsi_oversold", "?")),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="k">{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div></div>'
        for k, v in stats
    )
    sectors = (xray.get("sectors") or {}).get("sectors") or []
    rows = "".join(
        "<tr>"
        f"<td>{esc(s.get('rank'))}</td><td>{esc(s.get('sector'))} "
        f"({esc(s.get('ticker'))})</td>"
        f"<td class='num'>{esc(fmt_price_tagged(s.get('price'), session))}</td>"
        f"<td class='num'>{esc(fmt_pct(s.get('ret_21d_pct')))}</td>"
        f"<td class='num'>{esc(fmt_signed(s.get('momentum_score')))}</td>"
        f"<td class='num'>{esc(fmt_pct(s.get('rs_21d_pct')))}</td>"
        f"<td>{esc(s.get('label'))}</td></tr>"
        for s in sectors
    )
    sector_table = (
        "<h3>Sector rotation</h3><table><tr><th>#</th><th>Sector</th>"
        "<th class='num'>Price</th><th class='num'>21d %</th>"
        "<th class='num'>Momentum</th><th class='num'>RS vs SPY</th>"
        "<th>Label</th></tr>" + rows + "</table>"
        if sectors else ""
    )
    leading = ", ".join(read.get("leading_sectors") or []) or "none recorded"
    lagging = ", ".join(read.get("lagging_sectors") or []) or "none recorded"
    return (
        '<section class="panel"><h2>Market X-Ray</h2>'
        f'<div class="grid">{stat_html}</div>'
        f'<p>Leading: {esc(leading)}<br>Lagging: {esc(lagging)}</p>'
        f"{sector_table}</section>"
    )


def _section_board(run: Dict, session: str) -> str:
    board = run.get("board") or {}
    rows_data = board.get("board") or []
    if not rows_data:
        return '<section class="panel"><h2>Liquidity Board</h2>' \
            '<p class="muted">Unavailable in this run.</p></section>'
    rows = ""
    for row in rows_data:
        comp = row.get("components") or {}
        inputs = row.get("inputs") or {}
        rows += (
            "<tr>"
            f"<td>{esc(row.get('rank'))}</td><td><b>{esc(row.get('ticker'))}</b></td>"
            f"<td class='num'>{esc(fmt_price_tagged(row.get('price'), session))}</td>"
            f"<td class='num'>{esc(fmt_pct(inputs.get('change_pct')))}</td>"
            f"<td class='num'><b>{esc(f'{float(row.get("score", 0.0)):.1f}')}</b></td>"
            f"<td>{esc(row.get('direction'))}</td>"
            f"<td class='num'>{esc(fmt_signed(comp.get('options_oi')))}</td>"
            f"<td class='num'>{esc(fmt_signed(comp.get('options_volume')))}</td>"
            f"<td class='num'>{esc(fmt_signed(comp.get('momentum')))}</td>"
            f"<td class='num'>{esc(fmt_signed(comp.get('relative_volume')))}</td>"
            f"<td class='num'>{esc(inputs.get('relative_volume', 'unknown'))}</td>"
            "</tr>"
        )
    errors = "".join(
        f'<p class="muted">No data: {esc(e.get("ticker"))} - '
        f'{esc(e.get("error"))}</p>'
        for e in board.get("errors") or []
    )
    return (
        '<section class="panel"><h2>Liquidity Board</h2>'
        "<table><tr><th>Rank</th><th>Ticker</th><th class='num'>Price</th>"
        "<th class='num'>Day %</th><th class='num'>Score</th><th>Direction</th>"
        "<th class='num'>OI</th><th class='num'>Opt vol</th>"
        "<th class='num'>Momentum</th><th class='num'>Relvol score</th>"
        "<th class='num'>Rel volume</th></tr>"
        f"{rows}</table>{errors}</section>"
    )


def _checks_table(checks: List[Dict]) -> str:
    if not checks:
        return '<p class="muted">No checks recorded on this card.</p>'
    rows = "".join(
        "<tr>"
        f"<td>{esc(c.get('check'))}</td><td>{esc(c.get('source'))}</td>"
        f"<td>{_pill(c.get('passed'))}</td><td>{esc(c.get('detail'))}</td>"
        "</tr>"
        for c in checks
    )
    return (
        "<table><tr><th>Check</th><th>Source</th><th>Status</th>"
        f"<th>Detail</th></tr>{rows}</table>"
    )


def _card_html(card: Dict, session: str) -> str:
    symbol = esc(card.get("symbol"))
    kind = card.get("kind")
    header = (
        f"<h3>{symbol} - {_verdict_pill(card.get('verdict'))} "
        f"{esc(card.get('direction'))} - conviction "
        f"{esc(card.get('conviction'))}/10 - {esc(kind)}</h3>"
    )
    bits = [header]
    if card.get("downgraded"):
        bits.append(
            f'<p class="redflag">DOWNGRADED: '
            f'{esc(card.get("downgrade_reason"))}</p>'
        )
    contract = card.get("contract")
    if contract:
        label = "Contract" if kind == "trade" else "Nearest candidate"
        bits.append(
            f"<p>{label}: <b>{esc(contract.get('contract_symbol'))}</b> "
            f"{esc(contract.get('option_type'))}, strike "
            f"{esc(fmt_price(contract.get('strike')))}, premium "
            f"{esc(fmt_price_tagged(contract.get('premium'), session))}, "
            f"{esc(contract.get('days_to_expiry'))} DTE</p>"
        )
    levels = card.get("levels") or {}
    bits.append(
        "<table><tr><th>Spot</th><th>Entry</th><th>Stop</th>"
        "<th>Target</th><th>Target source</th></tr><tr>"
        f"<td>{esc(fmt_price_tagged(levels.get('spot'), session))}</td>"
        f"<td>{esc(fmt_price(levels.get('entry')))}</td>"
        f"<td>{esc(fmt_price(levels.get('stop')))}</td>"
        f"<td>{esc(fmt_price(levels.get('target')))}</td>"
        f"<td>{esc(levels.get('target_source') or 'none in packet')}</td>"
        "</tr></table>"
    )
    sizing = card.get("sizing") or {}
    bits.append(
        f"<p>Sizing at {esc(float(sizing.get('risk_pct') or 0) * 100)}% risk: "
        f"{esc(sizing.get('contracts', 0))} contracts, premium outlay "
        f"{esc(fmt_price(sizing.get('premium_outlay_usd')))}, risk budget "
        f"{esc(fmt_price(sizing.get('risk_budget_usd')))}"
        + (
            f" - notes: {esc('; '.join(sizing.get('notes') or []))}"
            if sizing.get("notes") else ""
        )
        + "</p>"
    )
    greeks = (card.get("greeks_plain") or {}).get("line")
    if greeks:
        bits.append(f"<p>Greeks: {esc(greeks)}</p>")
    sector = (card.get("sector_context") or {}).get("line")
    if sector:
        bits.append(f'<p class="muted">Sector: {esc(sector)}</p>')
    review = card.get("risk_review") or {}
    if review.get("line"):
        css = "redflag" if review.get("downgraded") else "muted"
        bits.append(f'<p class="{css}"><b>RISK REVIEW</b> {esc(review["line"])}</p>')
    if card.get("why"):
        bits.append(f'<div class="why">{esc(card["why"])}</div>')
    rejection = card.get("rejection")
    if kind != "trade" and rejection:
        bits.append(
            f'<p class="muted">No-trade reason: '
            f'{esc(rejection.get("reason"))}</p>'
        )
    bits.append(_checks_table(card.get("checks") or []))
    return "".join(bits)


def _section_cards(run: Dict, session: str) -> str:
    cards = run.get("cards") or []
    if isinstance(cards, dict):
        cards = list(cards.values())
    if not cards:
        return '<section class="panel"><h2>Trade Cards</h2>' \
            '<p class="muted">No cards in this run.</p></section>'
    body = "".join(_card_html(card, session) for card in cards)
    return f'<section class="panel"><h2>Trade Cards</h2>{body}</section>'


def _normalize_debates(run: Dict) -> Dict[str, Dict]:
    debates = run.get("debates") or {}
    if isinstance(debates, list):
        return {d.get("symbol"): d for d in debates}
    return debates


def featured_debate(run: Dict) -> Tuple[Optional[str], Optional[Dict]]:
    """The debate the dashboard features: a looped run wins (it is
    the demo's collaboration proof), then a trade card's symbol,
    then the first debate available."""
    debates = _normalize_debates(run)
    if not debates:
        return None, None
    for symbol, debate in debates.items():
        if debate and debate.get("looped"):
            return symbol, debate
    cards = run.get("cards") or []
    if isinstance(cards, dict):
        cards = list(cards.values())
    for card in cards:
        symbol = card.get("symbol")
        if symbol in debates:
            return symbol, debates[symbol]
    symbol = next(iter(debates))
    return symbol, debates[symbol]


def _round_html(round_rec: Dict) -> str:
    round_no = round_rec.get("round")
    bits = [f"<h3>Round {esc(round_no)}"]
    if round_no and int(round_no) > 1:
        bits[0] += " - loop-back"
    bits[0] += "</h3>"
    if round_rec.get("gap_note_in"):
        bits.append(
            '<div class="gapbox"><b>Evaluator feedback carried into '
            f'this round:</b> {esc(round_rec["gap_note_in"])}</div>'
        )
    judge = round_rec.get("judge") or {}
    bits.append(
        '<div class="casebox"><div class="who">BULL</div>'
        f'{esc(round_rec.get("bull_case"))}</div>'
    )
    bits.append(
        '<div class="casebox"><div class="who">BEAR</div>'
        f'{esc(round_rec.get("bear_case"))}</div>'
    )
    verdict_line = (
        f'<div class="casebox"><div class="who">JUDGE</div>'
        f'{_verdict_pill(judge.get("verdict"))} conviction '
        f'{esc(judge.get("conviction"))}/10, direction '
        f'{esc(judge.get("direction"))}'
    )
    if judge.get("summary"):
        verdict_line += f'<br>{esc(judge["summary"])}'
    if judge.get("key_evidence"):
        items = "".join(
            f"<li>{esc(item)}</li>" for item in judge["key_evidence"]
        )
        verdict_line += f"<ul>{items}</ul>"
    if judge.get("biggest_risk"):
        verdict_line += (
            f'<br><span class="redflag">Biggest risk:</span> '
            f'{esc(judge["biggest_risk"])}'
        )
    if judge.get("loop_note"):
        verdict_line += f'<br><span class="muted">{esc(judge["loop_note"])}</span>'
    verdict_line += "</div>"
    bits.append(verdict_line)
    if round_rec.get("gap"):
        bits.append(
            '<div class="gapbox"><b>Evaluator gap (why the loop '
            f'fired):</b> {esc(round_rec["gap"])}</div>'
        )
    grounding = round_rec.get("grounding") or {}
    if grounding:
        rows = ""
        for who in ("bull", "bear", "judge"):
            rep = grounding.get(who) or {}
            bad = [
                f"[{c['path']} = {c['stated']}] {c['status']}"
                + (f" (packet: {c['actual']})" if c["status"] == "mismatch" else "")
                for c in (rep.get("mismatched") or []) + (rep.get("unresolved") or [])
            ]
            free = rep.get("unsupported_numbers") or []
            rows += (
                f"<tr><td>{who.upper()}</td><td class='num'>{esc(rep.get('cited', 0))}</td>"
                f"<td class='num'>{esc(rep.get('verified', 0))}</td>"
                f"<td>{esc('; '.join(bad) or 'none')}</td>"
                f"<td>{esc(', '.join(free) or 'none')}</td></tr>"
            )
        bits.append(
            "<p class='muted'>Grounding check (code-verified against the packet):</p>"
            "<table><tr><th>Voice</th><th>Citations</th><th>Verified</th>"
            "<th>Failed citations</th><th>Numbers not in packet</th></tr>"
            f"{rows}</table>"
        )
    return "".join(bits)


def _section_history(run: Dict) -> str:
    """Board migration across earlier dated runs (Part C addition 4)."""
    history = run.get("board_history") or {}
    dates = history.get("dates") or []
    if len(dates) < 2:
        return ""
    head = "".join(f"<th>{esc(d)}</th>" for d in dates)
    rows = ""
    for ticker, by_date in sorted((history.get("tickers") or {}).items()):
        cells = ""
        for d in dates:
            row = by_date.get(d)
            cells += (
                f"<td class='num'>#{esc(row['rank'])} {esc(f'{row['score']:.1f}')}</td>"
                if row else "<td class='num muted'>-</td>"
            )
        rows += f"<tr><td><b>{esc(ticker)}</b></td>{cells}</tr>"
    return (
        '<section class="panel"><h2>Board Migration</h2>'
        "<p class='muted'>Rank and score per dated run, from runs/&lt;date&gt;/artifacts.json.</p>"
        f"<table><tr><th>Ticker</th>{head}</tr>{rows}</table></section>"
    )


def _section_errors(run: Dict) -> str:
    errors = run.get("errors") or []
    if not errors:
        return ""
    items = "".join(
        f"<li><b>{esc(e.get('symbol') or '-')}</b> {esc(e.get('stage'))}: "
        f"{esc(e.get('error'))}</li>"
        for e in errors
    )
    return (
        '<section class="panel"><h2>Not Completed This Run</h2>'
        f'<ul class="muted">{items}</ul></section>'
    )


def _section_debate(run: Dict) -> str:
    symbol, debate = featured_debate(run)
    if not debate:
        return '<section class="panel"><h2>Debate</h2>' \
            '<p class="muted">No debate record in this run.</p></section>'
    bits = [f'<section class="panel"><h2>Debate - {esc(symbol)}</h2>']
    if debate.get("looped"):
        bits.append(
            '<p><span class="pill watch">LOOP-BACK</span> The judge '
            "returned INSUFFICIENT_EVIDENCE in round 1, named the gap, "
            "and the analysts re-argued with that feedback before the "
            "final verdict.</p>"
        )
    if debate.get("why"):
        bits.append(f'<div class="why">{esc(debate["why"])}</div>')
    rounds = debate.get("rounds") or []
    if rounds:
        bits += [_round_html(rec) for rec in rounds]
    else:
        bits.append(
            f'<div class="casebox"><div class="who">BULL</div>'
            f'{esc(debate.get("bull_case"))}</div>'
            f'<div class="casebox"><div class="who">BEAR</div>'
            f'{esc(debate.get("bear_case"))}</div>'
        )
    bits.append("</section>")
    return "".join(bits)


def _section_journal(run: Dict) -> str:
    stats = run.get("journal_stats")
    if not stats:
        return '<section class="panel"><h2>Journal</h2>' \
            '<p class="muted">No journal stats in this run.</p></section>'
    hit_rate = stats.get("hit_rate")
    stat_items = [
        ("Entries", stats.get("entries", 0)),
        ("Scored", stats.get("scored_entries", 0)),
        ("Hits", stats.get("hits", 0)),
        ("Losses", stats.get("losses", 0)),
        ("Hit rate", f"{hit_rate * 100:.1f}%" if hit_rate is not None else "unknown"),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="k">{esc(k)}</div>'
        f'<div class="v">{esc(v)}</div></div>'
        for k, v in stat_items
    )
    breaker = stats.get("breaker") or {}
    if breaker.get("tripped"):
        breaker_html = (
            f'<div class="breaker-on">{esc(breaker.get("line"))}</div>'
        )
    else:
        breaker_html = (
            f'<div class="breaker-off">{esc(breaker.get("line"))}</div>'
        )
    entries = run.get("journal_entries") or []
    entry_rows = ""
    if entries:
        rows = "".join(
            "<tr>"
            f"<td>{esc(e.get('ts'))}</td><td>{esc(e.get('symbol'))}</td>"
            f"<td>{_verdict_pill(e.get('verdict'))}</td>"
            f"<td>{esc(e.get('direction'))}</td>"
            f"<td class='num'>{esc(fmt_price(e.get('entry_price')))}</td>"
            "</tr>"
            for e in entries[-8:]
        )
        entry_rows = (
            "<h3>Journal entries (latest)</h3><table><tr><th>Time</th>"
            "<th>Symbol</th><th>Verdict</th><th>Direction</th>"
            f"<th class='num'>Entry price</th></tr>{rows}</table>"
        )
    return (
        '<section class="panel"><h2>Journal - the journal that '
        f'writes itself</h2><div class="grid">{stat_html}</div>'
        f"{breaker_html}{entry_rows}</section>"
    )


# ----------------------------------------------------------------------
# page
# ----------------------------------------------------------------------
def render_dashboard(run: Dict) -> str:
    """Render one run's artifacts as a single self-contained page."""
    run = run or {}
    session = session_label(run.get("as_of"), explicit=run.get("session"))
    date_label = run.get("date") or ""
    as_of = run.get("as_of") or ""
    subtitle = " - ".join(p for p in [str(date_label), str(as_of)] if p)
    posture = ((run.get("xray") or {}).get("read") or {}).get("posture")
    posture_badge = (
        f' <span class="pill posture">{esc(str(posture).replace("_", " ").upper())}</span>'
        if posture else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QuantPilot - Judges Dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>QuantPilot - Judges Dashboard{posture_badge}</h1>
<div class="sub">{esc(subtitle)} - session: {esc(session)}</div>
<div class="sub">Autonomous pre-market options research: liquidity board, bull/bear/judge debate, evidence-backed trade cards. Every number on this page comes from the run's own artifacts.</div>
</header>
{_section_xray(run, session)}
{_section_board(run, session)}
{_section_cards(run, session)}
{_section_debate(run)}
{_section_history(run)}
{_section_journal(run)}
{_section_errors(run)}
<footer>QuantPilot - Open Agent Hackathon 2026, Track 02 (The Agent That Can Explain Why). Educational only - not financial advice.</footer>
</div>
</body>
</html>
"""


def write_dashboard(run: Dict, path: str) -> str:
    """Render and write the dashboard; returns the path written."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(render_dashboard(run))
    return path
