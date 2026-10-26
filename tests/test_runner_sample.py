"""Tests for the morning runner in SAMPLE_MODE (Day 4 drop).

The runner module is loaded from scripts/ by path (it is a script,
not a package). Sample runs replay samples/morning_run.json with
no network and no LLM key, and must be deterministic: running
twice into the same output dir yields the same journal state.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = REPO_ROOT / "scripts" / "run_morning.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_morning", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sample_mode_writes_all_outputs(tmp_path):
    runner = _load_runner()
    out_dir = tmp_path / "run"
    rc = runner.main(["--sample-mode", "--output-dir", str(out_dir)])
    assert rc == 0
    for name in ("briefing.txt", "briefing.md", "dashboard.html",
                 "artifacts.json", "journal.db"):
        assert (out_dir / name).exists(), name
    briefing = (out_dir / "briefing.txt").read_text()
    assert "TSLA - TRADE call" in briefing
    assert briefing.count("Educational only - not financial advice.") == 1
    dashboard = (out_dir / "dashboard.html").read_text()
    assert "Round 2" in dashboard  # the looped debate is on the page
    artifacts = json.loads((out_dir / "artifacts.json").read_text())
    assert artifacts["mode"] == "sample"
    # 3 seed entries + today's TSLA and NVDA entries.
    assert artifacts["journal_stats"]["entries"] == 5
    assert artifacts["journal_stats"]["hit_rate"] == 0.5


def test_sample_mode_via_env_var(tmp_path, monkeypatch):
    runner = _load_runner()
    monkeypatch.setenv("SAMPLE_MODE", "true")
    out_dir = tmp_path / "run_env"
    rc = runner.main(["--output-dir", str(out_dir)])
    assert rc == 0
    assert (out_dir / "briefing.txt").exists()


def test_sample_mode_is_deterministic(tmp_path):
    runner = _load_runner()
    out_dir = tmp_path / "run_twice"
    runner.main(["--sample-mode", "--output-dir", str(out_dir)])
    first = (out_dir / "briefing.txt").read_text()
    runner.main(["--sample-mode", "--output-dir", str(out_dir)])
    second = (out_dir / "briefing.txt").read_text()
    assert first == second  # journal rebuilt, never double-recorded
    artifacts = json.loads((out_dir / "artifacts.json").read_text())
    assert artifacts["journal_stats"]["entries"] == 5


# ----------------------------------------------------------------------
# live path failure isolation (audit repair, Oct 22) - fakes only
# ----------------------------------------------------------------------
def test_live_run_isolates_failures_and_still_writes(tmp_path, monkeypatch):
    """One symbol's quote fails, one symbol's LLM call fails, the X-Ray
    fails: the run must still finish, debate the healthy symbol, write
    all outputs, and name every failure instead of filling it in."""
    import json as _json

    from tests.test_agent_packet import FakeProvider

    runner = _load_runner()

    class Provider(FakeProvider):
        def get_quote(self, ticker):
            if ticker == "BAD":
                raise ValueError("quote feed down")
            return super().get_quote(ticker)

    class LLM:
        config = None

        def chat_text(self, prompt, model=None, max_tokens=4096):
            if "LLMX" in prompt:
                raise TimeoutError("NVIDIA read timeout")
            if "JUDGE" in prompt:
                return _json.dumps({
                    "verdict": "WATCH", "conviction": 3, "direction": "none",
                    "gap": None, "key_evidence": ["spot = 102.2"],
                    "biggest_risk": "x", "summary": "y"})
            return "case [spot = 102.2]"

    board = {"board": [{"ticker": t, "score": s, "rank": i + 1, "price": 102.2}
                       for i, (t, s) in enumerate([("TST", 50.0), ("BAD", 40.0),
                                                   ("LLMX", 30.0)])],
             "errors": [], "count": 3}

    def no_xray(provider):
        raise RuntimeError("sector ETFs unavailable")

    monkeypatch.setattr(runner, "get_provider", lambda name=None: Provider())
    monkeypatch.setattr(runner, "get_llm_provider", lambda: LLM())
    monkeypatch.setattr(runner, "build_board", lambda provider: board)
    monkeypatch.setattr(runner, "market_xray", no_xray)
    from tests.test_agent_memory import FakeEngine

    memory = FakeEngine()
    monkeypatch.setattr(runner, "get_memory_engine", lambda: memory)

    out_dir = tmp_path / "live"
    rc = runner.main(["--top-n", "3", "--output-dir", str(out_dir),
                      "--journal-db", str(tmp_path / "j.db")])
    assert rc == 0
    artifacts = _json.loads((out_dir / "artifacts.json").read_text())
    assert artifacts["mode"] == "live"
    assert [c["symbol"] for c in artifacts["cards"]] == ["TST"]
    stages = {(e["symbol"], e["stage"]) for e in artifacts["errors"]}
    assert stages == {(None, "xray"), ("BAD", "packet"), ("LLMX", "debate")}
    assert artifacts["timings"]["llm"]["calls"] == 4  # 3 for TST + 1 failed
    assert artifacts["cards"][0]["risk_review"]["applies"] is False
    # H-Mem: TST recalled (nothing yet) into its packet, then remembered.
    assert artifacts["packets"]["TST"]["memory"]["calls"] == []
    assert list(memory.live) == [f"call:{artifacts['date']}:TST"]
    # IV snapshots cover every board name the chain serves, debated or
    # not (TST, BAD-quote names still have a chain; LLMX too) - not just
    # the cards: 3 board rows, the fake chain has a 0.30 ATM IV.
    assert artifacts["iv_snapshots_written"] == 3
    briefing = (out_dir / "briefing.txt").read_text()
    assert "NOT COMPLETED THIS RUN" in briefing
    assert "LLMX: debate failed" in briefing
    assert "Not Completed This Run" in (out_dir / "dashboard.html").read_text()
