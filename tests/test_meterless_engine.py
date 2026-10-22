"""Round-trip tests for the Meterless H-MEM engine wrapper.

Runs the vendored H-MEM reference through Node in a temporary state
directory. No network and no API keys. Skipped when Node is missing.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest

from src.integrations.meterless_engine import MeterlessEngine

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node not installed")


@pytest.fixture
def mem(tmp_path):
    return MeterlessEngine(persist_dir=str(tmp_path / "hmem"))


def test_round_trip_remember_then_recall(mem):
    value = {"ticker": "SPY", "bias": "bullish", "entry": 766.48, "stop": 760.0}
    mem.remember("call:2026-10-20:SPY", value)
    items = mem.recall("call:2026-10-20:SPY")
    assert items, "recall returned nothing"
    assert items[0]["key"] == "call:2026-10-20:SPY"
    assert items[0]["value"] == value


def test_state_persists_across_instances(tmp_path):
    a = MeterlessEngine(persist_dir=str(tmp_path / "hmem"))
    a.remember("hit_rate:week-42", {"calls": 12, "hits": 8})
    b = MeterlessEngine(persist_dir=str(tmp_path / "hmem"))
    assert b.recall("hit_rate:week-42")[0]["value"] == {"calls": 12, "hits": 8}
    # H-MEM writes its own state file and append-only trust ledger
    assert os.path.exists(tmp_path / "hmem" / "state.json")
    ledger = (tmp_path / "hmem" / "ledger.jsonl").read_text().splitlines()
    assert any(json.loads(line)["action"] == "create" for line in ledger)


def test_rewrite_supersedes_older_value(mem):
    mem.remember("outcome:2026-10-20:NVDA", "pending")
    mem.remember("outcome:2026-10-20:NVDA", "hit")
    items = mem.recall("outcome:2026-10-20:NVDA")
    assert [i["value"] for i in items if i["key"] == "outcome:2026-10-20:NVDA"] == ["hit"]
    assert mem.count() == 1


def test_recall_ranks_the_relevant_memory_first(mem):
    mem.remember("call:2026-10-20:AAPL", "bearish below 340 support")
    mem.remember("call:2026-10-20:TSLA", "bullish breakout above 52-week high")
    items = mem.recall("TSLA breakout bullish", threshold=0.0)
    assert items[0]["key"] == "call:2026-10-20:TSLA"


def test_rejects_unknown_engine_and_bad_input(tmp_path):
    with pytest.raises(ValueError):
        MeterlessEngine(persist_dir=str(tmp_path), engine="world-model")
    mem = MeterlessEngine(persist_dir=str(tmp_path / "hmem"))
    with pytest.raises(ValueError):
        mem.remember("", "x")
    with pytest.raises(TypeError):
        mem.remember("k", object())
