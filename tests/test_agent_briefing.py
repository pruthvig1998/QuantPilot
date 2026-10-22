"""Tests for the morning briefing generator (Day 4 drop).

Inputs are the recorded fixture bundle (samples/morning_run.json -
real module outputs over synthetic data) with journal stats replayed
through a real Journal, exactly like the morning runner builds them.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.agent.briefing import generate_briefing, session_label
from src.agent.journal import Journal

FIXTURE = (
    Path(__file__).resolve().parent.parent / "samples" / "morning_run.json"
)
FOOTER = "Educational only - not financial advice."


def load_artifacts(tmp_path) -> dict:
    """Fixture bundle + journal stats/entries from a real Journal."""
    fixture = json.loads(FIXTURE.read_text())
    journal = Journal(str(tmp_path / "journal.db"))
    for seed in fixture["journal_seed"]:
        entry_id = journal.record_entry(
            seed["debate"],
            seed["card"],
            entry_price=seed.get("entry_price"),
            ts=seed.get("ts"),
        )
        outcome = seed.get("outcome")
        if outcome:
            journal.record_outcome(
                entry_id, float(outcome["spot"]),
                ts=outcome.get("ts"), note=outcome.get("note", ""),
            )
    cards = {c["symbol"]: c for c in fixture["cards"]}
    for symbol, debate in fixture["debates"].items():
        journal.record_entry(
            debate, cards[symbol], packet=fixture["packets"][symbol]
        )
    artifacts = dict(fixture)
    artifacts["journal_stats"] = journal.stats()
    artifacts["journal_entries"] = journal.list_entries()
    journal.close()
    return artifacts


# ----------------------------------------------------------------------
# sessions
# ----------------------------------------------------------------------
def test_session_label_by_et_clock():
    # Fri Oct 23, 2026: 12:30 UTC = 8:30 AM ET, 14:00 = 10 AM,
    # 21:30 = 5:30 PM. Sat Oct 24 is the close.
    assert session_label("2026-10-23T12:30:00+00:00") == "premarket"
    assert session_label("2026-10-23T14:00:00+00:00") == "live"
    assert session_label("2026-10-23T21:30:00+00:00") == "after-hours"
    assert session_label("2026-10-24T15:00:00+00:00") == "close"
    assert session_label("2026-10-23T03:00:00+00:00") == "close"


def test_session_explicit_label_wins():
    assert session_label("2026-10-23T14:00:00+00:00", explicit="close") == "close"


# ----------------------------------------------------------------------
# composition over the fixture run
# ----------------------------------------------------------------------
def test_briefing_sections_in_order_with_one_footer(tmp_path):
    artifacts = load_artifacts(tmp_path)
    out = generate_briefing(
        xray=artifacts["xray"], board=artifacts["board"],
        cards=artifacts["cards"], packets=artifacts["packets"],
        journal_stats=artifacts["journal_stats"],
        as_of=artifacts["as_of"], session=artifacts["session"],
    )
    text = out["text"]
    order = [
        text.index("MARKET X-RAY"), text.index("LIQUIDITY BOARD"),
        text.index("TRADE CARDS"), text.index("RISK FLAGS"),
        text.index("JOURNAL"),
    ]
    assert order == sorted(order)
    assert text.count(FOOTER) == 1
    assert out["markdown"].count(FOOTER) == 1
    assert text.rstrip().endswith(FOOTER)
    assert out["session"] == "premarket"


def test_briefing_style_rules(tmp_path):
    artifacts = load_artifacts(tmp_path)
    out = generate_briefing(
        xray=artifacts["xray"], board=artifacts["board"],
        cards=artifacts["cards"], packets=artifacts["packets"],
        journal_stats=artifacts["journal_stats"],
        as_of=artifacts["as_of"], session=artifacts["session"],
    )
    for blob in (out["text"], out["markdown"]):
        assert "—" not in blob  # no em dash, ever
        assert "–" not in blob  # no en dash either
        assert "(premarket)" in blob  # prices carry session tags
    assert "↑" in out["text"] and "↓" in out["text"]  # arrows, not emoji
    assert "$248.30 (premarket)" in out["text"]


def test_briefing_card_blocks_carry_the_working(tmp_path):
    artifacts = load_artifacts(tmp_path)
    out = generate_briefing(
        board=artifacts["board"], cards=artifacts["cards"],
        packets=artifacts["packets"],
        journal_stats=artifacts["journal_stats"],
        as_of=artifacts["as_of"], session=artifacts["session"],
    )
    text = out["text"]
    assert "TSLA - TRADE call | conviction 7/10" in text
    assert "Size: 1 contract |" in text  # pluralization is handled
    assert "Checks: 10 passed / 1 failed / 4 unknown of 15" in text
    assert "failed: market_event_in_window" in text
    assert "NVDA - WATCH (no trade)" in text
    assert "Market events inside the holding window: FOMC 2026-10-28" in text


def test_briefing_journal_and_breaker(tmp_path):
    artifacts = load_artifacts(tmp_path)
    stats = artifacts["journal_stats"]
    assert stats["hit_rate"] == 0.5 and stats["breaker"]["tripped"] is False
    out = generate_briefing(journal_stats=stats, as_of=artifacts["as_of"])
    assert "hit rate 50.0%" in out["text"]
    assert "CIRCUIT BREAKER" not in out["text"]  # calm state stays out

    tripped = dict(stats)
    tripped["breaker"] = {
        "tripped": True,
        "consecutive_losses": 2,
        "threshold": 2,
        "line": "CIRCUIT BREAKER: 2 consecutive losing scored entries - "
                "the 2-loss rule says stand down.",
    }
    out2 = generate_briefing(journal_stats=tripped, as_of=artifacts["as_of"])
    assert "CIRCUIT BREAKER: 2 consecutive losing scored entries" in out2["text"]


def test_briefing_degrades_honestly_with_no_inputs():
    out = generate_briefing(as_of="2026-10-23T12:30:00+00:00")
    text = out["text"]
    assert "X-Ray unavailable" in text
    assert "Board unavailable" in text
    assert "No trade cards in this run." in text
    assert "Risk flags unavailable" in text
    assert "Journal stats unavailable" in text
    assert text.count(FOOTER) == 1


def test_briefing_markdown_shape(tmp_path):
    artifacts = load_artifacts(tmp_path)
    out = generate_briefing(
        xray=artifacts["xray"], board=artifacts["board"],
        cards=artifacts["cards"], packets=artifacts["packets"],
        journal_stats=artifacts["journal_stats"],
        as_of=artifacts["as_of"], session=artifacts["session"],
    )
    md = out["markdown"]
    assert md.startswith("# QuantPilot Morning Briefing - Fri Oct 23, 2026")
    assert "| Rank | Ticker | Price |" in md  # board renders as a table
    assert "## Trade Cards" in md
    assert "### TSLA - TRADE call" in md
    json.dumps(out)
