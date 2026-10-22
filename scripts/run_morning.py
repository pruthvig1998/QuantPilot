#!/usr/bin/env python3
"""QuantPilot morning runner (Day 4 drop).

One command, one full morning run:

    build board -> X-Ray -> for the top N board names by |score|:
    assemble packet -> bull/bear/judge debate -> trade card ->
    journal entry -> score the journal's still-open entries from
    earlier runs -> render briefing (text + Markdown) and the
    judges dashboard into runs/<date>/.

Usage:
    .venv/bin/python scripts/run_morning.py [--top-n 3]
        [--output-dir runs/2026-10-23] [--journal-db PATH]
        [--account-size 10000] [--provider zetaris|yahoo]

    SAMPLE_MODE=true .venv/bin/python scripts/run_morning.py
    (or pass --sample-mode)

SAMPLE_MODE is the submission-guide fallback: the whole pipeline
runs against the recorded fixture bundle in samples/morning_run.json
(a real run of these same modules over synthetic provider data,
frozen to JSON). No network, no LLM key, deterministic outputs -
the demo and the judges can reproduce the run anywhere.

Live mode needs the data provider (config.DATA_PROVIDER) and the
LLM route from src/integrations/llm.py (NVIDIA direct via the .env
key, or Meterless when configured). Nothing here posts anywhere:
the runner writes files, and a human decides what to do with them.

US markets only. Research output - a human approves every order.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src import config  # noqa: E402
from src.agent.briefing import generate_briefing, session_label  # noqa: E402
from src.agent.cards import build_card  # noqa: E402
from src.agent.dashboard import render_dashboard  # noqa: E402
from src.agent.debate import _judge_text, run_debate  # noqa: E402
from src.agent.grounding import grounding_report  # noqa: E402
from src.agent.journal import Journal  # noqa: E402
from src.agent.memory import recall_calls, remember_call, remember_outcome  # noqa: E402
from src.agent.packet import assemble_packet  # noqa: E402
from src.agent.risk import apply_risk_review, review_card, sector_context  # noqa: E402
from src.data.cache import CachingProvider  # noqa: E402
from src.data.yahoo import get_provider  # noqa: E402
from src.integrations.llm import get_llm_provider  # noqa: E402
from src.integrations.meterless_engine import MeterlessEngine  # noqa: E402
from src.liquidity.board import build_board  # noqa: E402
from src.xray.xray import market_xray  # noqa: E402

FIXTURE_PATH = os.path.join(REPO_ROOT, "samples", "morning_run.json")


def _et_date(as_of: Optional[datetime] = None) -> str:
    from zoneinfo import ZoneInfo

    when = as_of or datetime.now(timezone.utc)
    return when.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _write_outputs(artifacts: Dict, output_dir: str) -> Dict[str, str]:
    """Render briefing + dashboard + the raw bundle into output_dir."""
    os.makedirs(output_dir, exist_ok=True)
    briefing = generate_briefing(
        xray=artifacts.get("xray"),
        board=artifacts.get("board"),
        cards=artifacts.get("cards"),
        packets=artifacts.get("packets"),
        journal_stats=artifacts.get("journal_stats"),
        as_of=artifacts.get("as_of"),
        session=artifacts.get("session"),
        run_errors=artifacts.get("errors"),
    )
    paths = {
        "briefing_text": os.path.join(output_dir, "briefing.txt"),
        "briefing_markdown": os.path.join(output_dir, "briefing.md"),
        "dashboard": os.path.join(output_dir, "dashboard.html"),
        "artifacts": os.path.join(output_dir, "artifacts.json"),
    }
    with open(paths["briefing_text"], "w") as fh:
        fh.write(briefing["text"])
    with open(paths["briefing_markdown"], "w") as fh:
        fh.write(briefing["markdown"])
    with open(paths["dashboard"], "w") as fh:
        fh.write(render_dashboard(artifacts))
    with open(paths["artifacts"], "w") as fh:
        json.dump(artifacts, fh, indent=1, sort_keys=True, default=str)
    return paths


def _top_symbols(board: Dict, top_n: int) -> List[str]:
    rows = sorted(
        board.get("board") or [],
        key=lambda r: abs(float(r.get("score", 0.0))),
        reverse=True,
    )
    return [r["ticker"] for r in rows[:top_n]]


class TimedClient:
    """Wraps the LLM client and records every call's wall-clock time,
    so the run carries its own latency evidence."""

    def __init__(self, client) -> None:
        self._client = client
        self.config = getattr(client, "config", None)
        self.calls: List[Dict] = []

    def chat_text(self, prompt, model=None, max_tokens=4096):
        start = time.time()
        ok = False
        try:
            text = self._client.chat_text(prompt, model=model, max_tokens=max_tokens)
            ok = bool(text)
            return text
        finally:
            self.calls.append({"seconds": round(time.time() - start, 2),
                               "prompt_chars": len(prompt), "ok": ok})


def board_history(runs_dir: str, today: str, board: Optional[Dict]) -> Dict:
    """Rank/score per ticker across dated runs/<date>/artifacts.json,
    plus today's board (Part C addition 4). Live runs only: sample
    replays are excluded so fixtures never pose as history."""
    tickers: Dict[str, Dict[str, Dict]] = {}
    dates: List[str] = []
    for path in sorted(glob.glob(os.path.join(runs_dir, "*", "artifacts.json"))):
        try:
            with open(path) as fh:
                past = json.load(fh)
        except (OSError, ValueError):
            continue
        day = past.get("date")
        if past.get("mode") != "live" or not day or day >= today:
            continue
        for row in (past.get("board") or {}).get("board") or []:
            tickers.setdefault(row["ticker"], {})[day] = {
                "rank": row.get("rank"), "score": row.get("score")}
        dates.append(day)
    for row in (board or {}).get("board") or []:
        tickers.setdefault(row["ticker"], {})[today] = {
            "rank": row.get("rank"), "score": row.get("score")}
    return {"dates": sorted(set(dates)) + [today], "tickers": tickers}


def get_memory_engine():
    """The Meterless H-Mem engine, or None when it cannot be built."""
    try:
        return MeterlessEngine.from_env()
    except Exception:
        return None


def run_live(args: argparse.Namespace) -> Dict:
    """The real morning run: provider data + live LLM debates.

    Failure isolation: a stage that fails for one symbol is recorded
    in artifacts["errors"] and the run continues; nothing is filled in
    for the failed piece. Only a run with no board at all stops early,
    and it still writes its outputs saying so.
    """
    provider = CachingProvider(get_provider(args.provider or config.DATA_PROVIDER))
    client = TimedClient(get_llm_provider())
    timings: Dict[str, float] = {}
    errors: List[Dict] = []
    now = datetime.now(timezone.utc)
    today = _et_date(now)

    t0 = time.time()
    board = build_board(provider)
    timings["board_s"] = round(time.time() - t0, 1)
    for err in board.get("errors") or []:
        errors.append({"symbol": err.get("ticker"), "stage": "board",
                       "error": err.get("error")})
    t0 = time.time()
    try:
        xray = market_xray(provider)
    except Exception as exc:
        xray = None
        errors.append({"symbol": None, "stage": "xray", "error": str(exc)})
    timings["xray_s"] = round(time.time() - t0, 1)
    symbols = _top_symbols(board, args.top_n)

    memory = get_memory_engine()
    if memory is None:
        errors.append({"symbol": None, "stage": "memory",
                       "error": "Meterless H-Mem engine unavailable"})
    journal = Journal(args.journal_db) if args.journal_db else Journal()
    try:
        open_before = journal.open_entries()

        packets: Dict[str, Dict] = {}
        debates: Dict[str, Dict] = {}
        cards: List[Dict] = []
        per_symbol: Dict[str, Dict] = {}
        for symbol in symbols:
            stage = "packet"
            t_sym = time.time()
            try:
                history = journal.iv_history(symbol, before_day=today)
                packet = assemble_packet(symbol, provider, iv_history=history)
                t_packet = time.time() - t_sym
                if memory is not None:
                    # The agent's own past calls on this name, from H-Mem,
                    # as citable packet evidence.
                    packet["memory"] = recall_calls(memory, symbol, before_day=today)
                    if packet["memory"]["error"]:
                        errors.append({"symbol": symbol, "stage": "memory-recall",
                                       "error": packet["memory"]["error"]})
                iv_now = ((packet.get("events") or {}).get("iv") or {}).get("current")
                journal.record_iv_snapshot(
                    symbol, today, iv_now,
                    (packet.get("guardrails") or {}).get("expiration"),
                )
                stage = "debate"
                t1 = time.time()
                debate = run_debate(packet, client=client)
                t_debate = time.time() - t1
                stage = "card"
                card = build_card(packet, debate, account_size=args.account_size)
                card = apply_risk_review(card, review_card(packet, debate, card))
                card["sector_context"] = sector_context(symbol, xray)
            except Exception as exc:
                errors.append({"symbol": symbol, "stage": stage,
                               "error": f"{type(exc).__name__}: {exc}"})
                continue
            packets[symbol] = packet
            debates[symbol] = debate
            cards.append(card)
            per_symbol[symbol] = {"packet_s": round(t_packet, 1),
                                  "debate_s": round(t_debate, 1),
                                  "llm_calls": len(debate.get("rounds") or []) * 3}

        # Score entries left open by earlier runs against live
        # quotes BEFORE today's entries land, so a fresh entry is
        # never scored against its own entry price.
        scored = 0
        for entry in open_before:
            try:
                quote = provider.get_quote(entry["symbol"])
                outcome = journal.record_outcome(
                    entry["id"], float(quote["price"]),
                    note="morning-run score",
                )
                scored += 1
                if memory is not None:
                    remember_outcome(memory, entry, outcome)
            except Exception as exc:  # one bad symbol must not sink the run
                errors.append({"symbol": entry["symbol"], "stage": "journal-score",
                               "error": str(exc)})
        remembered = 0
        for symbol in packets:
            journal.record_entry(
                debates[symbol], _card_for(cards, symbol), packet=packets[symbol]
            )
            if memory is not None:
                try:
                    remember_call(memory, debates[symbol], _card_for(cards, symbol),
                                  packets[symbol], today)
                    remembered += 1
                except Exception as exc:
                    errors.append({"symbol": symbol, "stage": "memory-remember",
                                   "error": f"{type(exc).__name__}: {exc}"})

        call_secs = [c["seconds"] for c in client.calls]
        timings["per_symbol"] = per_symbol
        timings["llm"] = {
            "model": getattr(client.config, "model", None),
            "calls": len(call_secs),
            "empty_replies": sum(1 for c in client.calls if not c["ok"]),
            "total_s": round(sum(call_secs), 1),
            "mean_s": round(sum(call_secs) / len(call_secs), 1) if call_secs else None,
            "max_s": max(call_secs) if call_secs else None,
        }
        timings["total_s"] = round(time.time() - now.timestamp(), 1)
        end = datetime.now(timezone.utc)
        artifacts = {
            "date": today,
            "as_of": end.isoformat(),
            "started_at": now.isoformat(),
            "session": session_label(end),
            "mode": "live",
            "provider": type(provider.inner).__name__,
            "provider_cache": provider.stats(),
            "board": board,
            "xray": xray,
            "packets": packets,
            "debates": debates,
            "cards": cards,
            "journal_stats": journal.stats(),
            "journal_entries": journal.list_entries(),
            "scored_open_entries": scored,
            "memory": {"engine": "meterless h-mem" if memory is not None else None,
                       "calls_remembered": remembered},
            "errors": errors,
            "timings": timings,
            "board_history": board_history(
                os.path.join(REPO_ROOT, "runs"), today, board
            ),
        }
    finally:
        journal.close()
    output_dir = args.output_dir or os.path.join(
        REPO_ROOT, "runs", artifacts["date"]
    )
    paths = _write_outputs(artifacts, output_dir)
    return {"artifacts": artifacts, "paths": paths, "output_dir": output_dir}


def _card_for(cards: List[Dict], symbol: str) -> Dict:
    for card in cards:
        if card.get("symbol") == symbol:
            return card
    raise KeyError(f"no card for {symbol}")


def load_fixture(path: str = FIXTURE_PATH) -> Dict:
    with open(path) as fh:
        return json.load(fh)


def run_sample(args: argparse.Namespace) -> Dict:
    """SAMPLE_MODE: replay the recorded fixture bundle end to end.

    The journal is a real Journal on a fresh SQLite file inside the
    output dir: fixture seed entries + outcomes land first, then the
    fixture debates/cards are recorded as today's entries, so the
    rendered stats come from the same code path as a live run.
    """
    fixture = load_fixture(args.fixture or FIXTURE_PATH)
    output_dir = args.output_dir or os.path.join(
        REPO_ROOT, "runs", fixture.get("date") or _et_date()
    )
    os.makedirs(output_dir, exist_ok=True)
    db_path = os.path.join(output_dir, "journal.db")
    if os.path.exists(db_path):
        os.remove(db_path)  # sample runs are deterministic replays
    journal = Journal(db_path)
    try:
        for seed in fixture.get("journal_seed") or []:
            entry_id = journal.record_entry(
                seed["debate"],
                seed["card"],
                entry_price=seed.get("entry_price"),
                ts=seed.get("ts"),
            )
            outcome = seed.get("outcome")
            if outcome:
                journal.record_outcome(
                    entry_id,
                    float(outcome["spot"]),
                    ts=outcome.get("ts"),
                    note=outcome.get("note", "sample outcome"),
                )
        packets = fixture.get("packets") or {}
        debates = fixture.get("debates") or {}
        # The fixture was frozen before the grounding verifier and the
        # risk review existed; both are pure, so the replay runs them
        # over the recorded packets / debates / cards - the same code
        # a live run uses, applied to recorded inputs.
        for symbol, debate in debates.items():
            for rnd in debate.get("rounds") or []:
                if "grounding" not in rnd:
                    rnd["grounding"] = {
                        "bull": grounding_report(rnd.get("bull_case") or "", packets.get(symbol) or {}),
                        "bear": grounding_report(rnd.get("bear_case") or "", packets.get(symbol) or {}),
                        "judge": grounding_report(_judge_text(rnd.get("judge") or {}), packets.get(symbol) or {}),
                    }
        cards = []
        for card in fixture.get("cards") or []:
            symbol = card.get("symbol")
            if "risk_review" not in card:
                card = apply_risk_review(
                    card, review_card(packets.get(symbol) or {}, debates.get(symbol) or {}, card)
                )
                card["sector_context"] = sector_context(symbol, fixture.get("xray"))
            cards.append(card)
        for symbol, debate in debates.items():
            journal.record_entry(
                debate, _card_for(cards, symbol), packet=packets.get(symbol)
            )
        artifacts = {
            "date": fixture.get("date"),
            "as_of": fixture.get("as_of"),
            "session": fixture.get("session"),
            "mode": "sample",
            "board": fixture.get("board"),
            "xray": fixture.get("xray"),
            "packets": packets,
            "debates": fixture.get("debates"),
            "cards": cards,
            "journal_stats": journal.stats(),
            "journal_entries": journal.list_entries(),
        }
    finally:
        journal.close()
    paths = _write_outputs(artifacts, output_dir)
    return {"artifacts": artifacts, "paths": paths, "output_dir": output_dir}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="QuantPilot morning runner")
    parser.add_argument("--top-n", type=int, default=config.RUNNER_TOP_N)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--journal-db", default=None)
    parser.add_argument("--account-size", type=float, default=config.ACCOUNT_SIZE_USD)
    parser.add_argument("--provider", default=None,
                        help="override config.DATA_PROVIDER (zetaris|yahoo)")
    parser.add_argument("--fixture", default=None,
                        help="sample fixture path (default samples/morning_run.json)")
    parser.add_argument("--sample-mode", action="store_true",
                        help="replay samples/morning_run.json (no network)")
    args = parser.parse_args(argv)

    sample = args.sample_mode or os.environ.get(
        "SAMPLE_MODE", ""
    ).strip().lower() == "true"
    result = run_sample(args) if sample else run_live(args)
    artifacts = result["artifacts"]
    print(f"mode: {artifacts.get('mode')}")
    print(f"output: {result['output_dir']}")
    for card in artifacts.get("cards") or []:
        print(
            f"card: {card.get('symbol')} {card.get('verdict')} "
            f"({card.get('kind')}) conviction {card.get('conviction')}"
        )
    stats = artifacts.get("journal_stats") or {}
    print(
        f"journal: {stats.get('entries', 0)} entries, "
        f"hit rate {stats.get('hit_rate')}"
    )
    for err in artifacts.get("errors") or []:
        print(f"not completed: {err.get('symbol')} {err.get('stage')} - {err.get('error')}")
    llm = (artifacts.get("timings") or {}).get("llm")
    if llm:
        print(f"llm: {llm['calls']} calls, mean {llm['mean_s']}s, max {llm['max_s']}s, "
              f"total {llm['total_s']}s ({llm['model']})")
    for name, path in result["paths"].items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
