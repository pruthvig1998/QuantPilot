#!/usr/bin/env python3
"""Ask QuantPilot about one run (terminal transport for src/agent/ask.py).

Usage:
    .venv/bin/python scripts/ask.py runs/2026-10-22 "Why is NFLX ranked first?"
    .venv/bin/python scripts/ask.py runs/2026-10-22 --llm "What could make the card fail?"
    .venv/bin/python scripts/ask.py samples/example-run "What is NVDA's IV rank?"

The first argument is a run directory (or its artifacts.json). Without
--llm the answer is the deterministic extractive path; with --llm the
Nemotron route composes it, and any number or citation that does not
trace to the run's artifacts sends it back to the extractive answer
(the output says so). Nothing is written anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.agent.ask import answer_question  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ask QuantPilot about a run")
    parser.add_argument("run", help="run directory or artifacts.json")
    parser.add_argument("question")
    parser.add_argument("--llm", action="store_true",
                        help="compose with the configured LLM (grounding-checked)")
    args = parser.parse_args(argv)

    path = args.run
    if os.path.isdir(path):
        path = os.path.join(path, "artifacts.json")
    with open(path) as fh:
        artifacts = json.load(fh)
    client = None
    if args.llm:
        from src.integrations.llm import get_llm_provider

        client = get_llm_provider()
    result = answer_question(args.question, artifacts, llm_client=client)
    print(f"Q: {result['question']}")
    print(f"A: {result['answer']}")
    tags = [f"mode {result['mode']}"]
    if result["refused"]:
        tags.append("refused (out of scope)")
    if result["unknown"]:
        tags.append("unknown in the artifacts")
    if result["sources"]:
        tags.append("sources " + ", ".join(result["sources"]))
    print("   [" + "; ".join(tags) + "]")
    if result.get("llm_rejected"):
        print(f"   [LLM answer rejected: {result['llm_rejected']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
