"""Agent memory over H-Mem: fake engine, no Node needed."""
from __future__ import annotations

from src.agent.memory import call_key, recall_calls, remember_call, remember_outcome


class FakeEngine:
    """remember/recall with H-Mem's supersede semantics (latest per key)."""

    def __init__(self):
        self.live = {}
        self.history = []

    def remember(self, key, value, tags=None, confidence=0.9):
        self.history.append((key, value))
        self.live[key] = value
        return f"mem-{len(self.history)}"

    def recall(self, query, top_n=5, threshold=None):
        return [{"key": k, "value": v} for k, v in self.live.items()][:top_n]


def test_remember_then_recall_filters_symbol_and_day():
    eng = FakeEngine()
    debate = {"symbol": "NFLX", "verdict": "SKIP", "direction": "none", "conviction": 8}
    remember_call(eng, debate, {"kind": "no_trade"}, {"spot": 65.04}, "2026-10-21")
    remember_call(eng, {"symbol": "TSLA", "verdict": "TRADE", "direction": "call",
                        "conviction": 7}, {"kind": "trade"}, {"spot": 240.0}, "2026-10-21")
    remember_call(eng, debate, {"kind": "no_trade"}, {"spot": 64.0}, "2026-10-22")
    got = recall_calls(eng, "NFLX", before_day="2026-10-22")
    assert [c["date"] for c in got["calls"]] == ["2026-10-21"]  # today excluded
    assert got["calls"][0]["entry_spot"] == 65.04
    assert got["calls"][0]["judge_verdict"] == "SKIP"


def test_outcome_supersedes_the_same_key():
    eng = FakeEngine()
    remember_call(eng, {"symbol": "TSLA", "verdict": "TRADE", "direction": "call",
                        "conviction": 7}, {"kind": "trade"}, {"spot": 240.0}, "2026-10-21")
    entry = {"symbol": "TSLA", "ts": "2026-10-21T14:05:00+00:00", "direction": "call",
             "conviction": 7, "entry_price": 240.0, "card": {"kind": "trade"},
             "debate": {"verdict": "TRADE"}}
    remember_outcome(eng, entry, {"spot": 244.8, "move_pct": 2.0, "hit": 1})
    assert len(eng.history) == 2
    live = eng.live[call_key("2026-10-21", "TSLA")]
    assert live["outcome"] == {"spot": 244.8, "move_pct": 2.0, "hit": 1}


def test_engine_failure_is_unknown_not_empty():
    class Down:
        def recall(self, *a, **k):
            raise RuntimeError("node not found")

    got = recall_calls(Down(), "NFLX")
    assert got["calls"] is None and "node not found" in got["error"]
