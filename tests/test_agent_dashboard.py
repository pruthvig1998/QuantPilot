"""Tests for the judges dashboard (Day 4 drop).

The page is the demo surface: it must contain every section, show
BOTH debate rounds of the featured (looped) run, keep check states
visibly distinct, stay fully self-contained, and escape artifact
text instead of trusting it.
"""
from __future__ import annotations

from src.agent.dashboard import featured_debate, render_dashboard
from tests.test_agent_briefing import load_artifacts


def test_dashboard_has_every_section(tmp_path):
    artifacts = load_artifacts(tmp_path)
    page = render_dashboard(artifacts)
    for needle in (
        "QuantPilot - Judges Dashboard",
        "Market X-Ray",
        "Sector rotation",
        "Liquidity Board",
        "Trade Cards",
        "Debate - NVDA",  # the looped run is the featured one
        "Journal",
        "Educational only - not financial advice.",
    ):
        assert needle in page, needle


def test_dashboard_shows_both_rounds_and_the_gap(tmp_path):
    artifacts = load_artifacts(tmp_path)
    symbol, debate = featured_debate(artifacts)
    assert symbol == "NVDA"
    assert debate["looped"] is True
    page = render_dashboard(artifacts)
    assert "Round 1" in page and "Round 2" in page
    assert "loop-back" in page
    assert "LOOP-BACK" in page
    # The Evaluator's round-1 gap is visible, verbatim from the record.
    assert "crush-risk check cannot be scored" in page
    # Both analysts and the judge appear per round.
    assert page.count('class="who">BULL') == 2
    assert page.count('class="who">BEAR') == 2
    assert page.count('class="who">JUDGE') == 2
    assert "CONCEDED" in page  # round 2 carries the concession


def test_dashboard_check_states_are_distinct(tmp_path):
    artifacts = load_artifacts(tmp_path)
    page = render_dashboard(artifacts)
    assert 'class="pill pass"' in page
    assert 'class="pill fail"' in page
    assert 'class="pill unknown"' in page
    # The one failed check on the TSLA card is the FOMC window check.
    assert "market_event_in_window" in page


def test_dashboard_is_self_contained(tmp_path):
    artifacts = load_artifacts(tmp_path)
    page = render_dashboard(artifacts)
    assert "http://" not in page
    assert "https://" not in page
    assert "<link" not in page
    assert "src=" not in page
    assert "<style>" in page  # inline CSS carries the theme


def test_dashboard_board_components_and_journal(tmp_path):
    artifacts = load_artifacts(tmp_path)
    page = render_dashboard(artifacts)
    assert "49.1" in page  # TSLA score in the board table
    assert "+0.57" in page  # its OI component rides along
    assert "50.0%" in page  # journal hit rate
    assert "Circuit breaker" in page or "consecutive losing" in page


def test_dashboard_escapes_artifact_text():
    run = {
        "date": "2026-10-23",
        "cards": [
            {
                "symbol": "X<script>alert(1)</script>",
                "kind": "no_trade",
                "verdict": "SKIP",
                "direction": "none",
                "conviction": 0,
                "checks": [],
            }
        ],
    }
    page = render_dashboard(run)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_dashboard_degrades_without_artifacts():
    page = render_dashboard({})
    assert "Unavailable in this run." in page
    assert "No cards in this run." in page
    assert "No debate record in this run." in page
