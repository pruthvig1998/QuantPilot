"""Tests for the self-scoring journal (module 8) + breaker (9).

SQLite in a tmp dir per test. Entries and outcomes are literals -
the journal's job is storage and scoring, not generating them.
"""
from __future__ import annotations

import json

from src.agent.journal import Journal
from src.data.provider import MarketDataProvider


def make_debate(symbol="TST", verdict="TRADE", direction="call",
                conviction=7, rounds=1):
    record = {
        "symbol": symbol,
        "verdict": verdict,
        "conviction": conviction,
        "direction": direction,
        "why": "test why",
        "packet_hash": f"hash-{symbol}",
        "looped": rounds == 2,
        "rounds": [{"round": 1, "verdict": verdict, "gap": None}],
    }
    if rounds == 2:
        record["rounds"] = [
            {
                "round": 1,
                "verdict": "INSUFFICIENT_EVIDENCE",
                "gap": "pools missing",
                "gap_note_in": None,
            },
            {
                "round": 2,
                "verdict": verdict,
                "gap": None,
                "gap_note_in": "pools missing",
            },
        ]
    return record


class QuoteProvider(MarketDataProvider):
    """Quotes from a fixed price map; unknown symbols raise."""

    def __init__(self, prices):
        self._prices = prices

    def get_quote(self, ticker):
        if ticker not in self._prices:
            raise ValueError(f"no quote for {ticker}")
        return {"ticker": ticker, "price": self._prices[ticker]}

    def get_bars(self, ticker, interval="1d", period="2y"):
        raise ValueError("bars not used by the journal")

    def get_expirations(self, ticker):
        return []

    def get_option_chain(self, ticker, expiration=None):
        return {"expiration": None, "calls": [], "puts": []}


def open_tmp(tmp_path) -> Journal:
    return Journal(str(tmp_path / "journal.db"))


# ----------------------------------------------------------------------
# entries
# ----------------------------------------------------------------------
def test_record_and_read_back_entry(tmp_path):
    journal = open_tmp(tmp_path)
    entry_id = journal.record_entry(
        make_debate(rounds=2),
        {"kind": "trade", "verdict": "TRADE"},
        packet={"symbol": "TST", "spot": 100.0},
    )
    entry = journal.get_entry(entry_id)
    assert entry["symbol"] == "TST"
    assert entry["entry_price"] == 100.0
    assert entry["packet_hash"] == "hash-TST"
    assert entry["card"]["kind"] == "trade"
    # The full run record - both rounds - is in the entry.
    assert len(entry["debate"]["rounds"]) == 2
    assert entry["debate"]["rounds"][0]["gap"] == "pools missing"
    journal.close()


def test_outcomes_are_append_only(tmp_path):
    journal = open_tmp(tmp_path)
    entry_id = journal.record_entry(
        make_debate(), {"kind": "trade"}, entry_price=100.0
    )
    card_before = journal.get_entry(entry_id)["card"]
    journal.record_outcome(entry_id, 101.0, note="day 1")
    journal.record_outcome(entry_id, 103.0, note="day 2")
    outcomes = journal.list_outcomes(entry_id)
    assert len(outcomes) == 2
    # The entry itself was never rewritten.
    assert journal.get_entry(entry_id)["card"] == card_before
    # Stats read the LATEST outcome: +3% on a call = hit.
    stats = journal.stats()
    assert stats["scored_entries"] == 1
    assert stats["hits"] == 1
    journal.close()


# ----------------------------------------------------------------------
# scoring
# ----------------------------------------------------------------------
def test_hit_logic_follows_direction(tmp_path):
    journal = open_tmp(tmp_path)
    call_win = journal.record_entry(
        make_debate(symbol="A"), {}, entry_price=100.0
    )
    call_loss = journal.record_entry(
        make_debate(symbol="B"), {}, entry_price=100.0
    )
    put_win = journal.record_entry(
        make_debate(symbol="C", direction="put"), {}, entry_price=100.0
    )
    assert journal.record_outcome(call_win, 103.0)["hit"] == 1
    assert journal.record_outcome(call_loss, 97.0)["hit"] == 0
    assert journal.record_outcome(put_win, 97.0)["hit"] == 1
    outcome = journal.record_outcome(put_win, 99.0)
    assert outcome["move_pct"] == -1.0
    journal.close()


def test_watch_outcomes_are_recorded_not_scored(tmp_path):
    journal = open_tmp(tmp_path)
    entry_id = journal.record_entry(
        make_debate(verdict="WATCH", direction="none"), {}, entry_price=100.0
    )
    outcome = journal.record_outcome(entry_id, 110.0)
    assert outcome["hit"] is None
    stats = journal.stats()
    assert stats["entries"] == 1
    assert stats["scored_entries"] == 0
    assert stats["hit_rate"] is None
    journal.close()


def test_score_with_provider_marks_open_entries(tmp_path):
    journal = open_tmp(tmp_path)
    journal.record_entry(
        make_debate(symbol="AAA"), {}, packet={"symbol": "AAA", "spot": 100.0}
    )
    journal.record_entry(
        make_debate(symbol="BBB", direction="put"),
        {},
        packet={"symbol": "BBB", "spot": 50.0},
    )
    journal.record_entry(
        make_debate(symbol="CCC"), {}, packet={"symbol": "CCC", "spot": 10.0}
    )
    result = journal.score_with_provider(
        QuoteProvider({"AAA": 104.0, "BBB": 52.0})
    )
    assert len(result["scored"]) == 2  # AAA up (call hit), BBB up (put loss)
    assert [s["symbol"] for s in result["skipped"]] == ["CCC"]
    assert result["stats"]["hit_rate"] == 0.5
    # CCC is still owed a score.
    assert [e["symbol"] for e in journal.open_entries()] == ["CCC"]
    json.dumps(result["stats"])
    journal.close()


# ----------------------------------------------------------------------
# circuit breaker (module 9)
# ----------------------------------------------------------------------
def test_breaker_trips_on_two_consecutive_losses_then_resets(tmp_path):
    journal = open_tmp(tmp_path)
    for symbol, outcome_price in (("A", 97.0), ("B", 96.0)):
        entry_id = journal.record_entry(
            make_debate(symbol=symbol), {}, entry_price=100.0
        )
        journal.record_outcome(entry_id, outcome_price)
    breaker = journal.breaker_state()
    assert breaker["tripped"] is True
    assert breaker["consecutive_losses"] == 2
    assert "CIRCUIT BREAKER" in breaker["line"]
    # A win breaks the streak.
    entry_id = journal.record_entry(
        make_debate(symbol="C"), {}, entry_price=100.0
    )
    journal.record_outcome(entry_id, 105.0)
    breaker = journal.breaker_state()
    assert breaker["tripped"] is False
    assert breaker["consecutive_losses"] == 0
    journal.close()


def test_journal_persists_across_reopen(tmp_path):
    path = str(tmp_path / "journal.db")
    journal = Journal(path)
    journal.record_entry(make_debate(), {"kind": "trade"}, entry_price=100.0)
    journal.close()
    reopened = Journal(path)
    assert len(reopened.list_entries()) == 1
    assert reopened.get_entry(1)["verdict"] == "TRADE"
    reopened.close()


def test_downgraded_trade_card_is_stored_as_watch_and_never_scored(tmp_path):
    """Judge said TRADE, the card downgraded it (no contract survived):
    the agent proposed no trade, so the journal must not score one."""
    journal = open_tmp(tmp_path)
    entry_id = journal.record_entry(
        make_debate(), {"kind": "no_trade", "downgraded": True},
        entry_price=100.0,
    )
    assert journal.record_outcome(entry_id, 90.0)["hit"] is None
    entry = journal.list_entries()[0]
    assert entry["verdict"] == "WATCH"
    assert entry["debate"]["verdict"] == "TRADE"  # judge's call kept on record
    assert journal.stats()["hit_rate"] is None
    journal.close()


def test_sizing_caps_total_premium_at_five_percent():
    """Reference: $10,000 account, stop distance 0.05 -> $5 risk per
    contract -> 20 contracts by the 1% rule. At $2.50 premium that is
    $5,000 of premium (half the account). The 5% cap ($500) allows
    floor(500 / 250) = 2 contracts, $500 outlay."""
    from src.agent.cards import _sizing

    sizing = _sizing(entry=100.0, stop=99.95, premium=2.50, account_size=10000.0)
    assert sizing["per_contract_risk_usd"] == 5.0
    assert sizing["contracts"] == 2
    assert sizing["premium_outlay_usd"] == 500.0
    assert "5% of the account" in sizing["notes"][0]


def test_iv_snapshots_rank_only_after_enough_days(tmp_path):
    """Reference: 20 days of ATM IV from 0.20 to 0.39 (step 0.01).
    Today's 0.35 ranks (0.35 - 0.20) / (0.39 - 0.20) = 78.9 on the
    snapshot range; with 19 days the range is withheld (None)."""
    from src.guardrail.events import iv_rank

    journal = open_tmp(tmp_path)
    for i in range(19):
        assert journal.record_iv_snapshot("TST", f"2026-09-{i + 1:02d}", 0.20 + 0.01 * i)
    assert journal.iv_history("TST")["low"] is None
    assert journal.iv_history("TST")["days"] == 19
    journal.record_iv_snapshot("TST", "2026-09-20", 0.39)
    # Same day again: first snapshot wins, nothing rewritten.
    assert journal.record_iv_snapshot("TST", "2026-09-20", 0.99) is False
    assert journal.record_iv_snapshot("TST", "2026-09-21", None) is False
    hist = journal.iv_history("TST", before_day="2026-10-23")
    assert hist["days"] == 20
    assert hist["low"] == 0.20 and round(hist["high"], 2) == 0.39
    assert hist["basis"] == "snapshot-based 20-day"
    assert iv_rank(0.35, hist["low"], hist["high"]) == 78.9
    journal.close()


def test_sizing_premium_floor_and_no_delta_fallback():
    """Delta-adjusted risk is capped at the whole premium; with no delta
    the delta-1 bound applies. References by hand:
    |0.80| x 2.0 x 100 = $160 > premium $1.20 x 100 = $120 -> $120;
    no delta: 0.50 x 100 = $50."""
    from src.agent.cards import _sizing

    capped = _sizing(entry=100.0, stop=98.0, premium=1.20, account_size=10000.0, delta=0.80)
    assert capped["per_contract_risk_usd"] == 120.0
    assert capped["risk_basis"].startswith("whole premium")
    bare = _sizing(entry=100.0, stop=99.5, premium=1.20, account_size=10000.0)
    assert bare["per_contract_risk_usd"] == 50.0
    assert "delta-1" in bare["risk_basis"]
