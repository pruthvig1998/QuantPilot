"""Meterless Engine integration: H-MEM (hierarchical memory).

QuantPilot's self-scoring journal needs memory across briefings (past calls,
outcomes, hit rate). This wraps the Meterless H-MEM engine with two calls:

    mem = MeterlessEngine.from_env()
    mem.remember("call:2026-10-20:SPY", {"bias": "bullish", "entry": 766.48})
    mem.recall("SPY call 2026-10-20")   # ranked [{key, value, relevance, ...}]

How it runs:
  - The engine is the official H-MEM reference implementation from
    github.com/Meterless/Meterless (engines/hmem/reference), vendored
    unmodified in vendor/meterless-hmem (Apache-2.0, commit in SOURCE.txt).
  - H-MEM ships no Python package, so each call starts
    src/integrations/hmem_bridge.ts under Node (23.6+ runs TypeScript with
    --experimental-transform-types; no npm install needed).
  - Retrieval is H-MEM's hybrid ranking (semantic, keyword, tag, domain,
    entity, layer, recency, superseded penalty) times record confidence.
  - Writing a key again supersedes the older record (kept, never deleted,
    per the H-MEM spec); recall returns only the live record per key.
  - State and the append-only trust ledger live in METERLESS_HMEM_DIR
    (default ~/.quantpilot/hmem): state.json + ledger.jsonl.

.env settings:
  METERLESS_ENGINE=hmem
  METERLESS_HMEM_DIR=~/.quantpilot/hmem   (optional)
  METERLESS_NODE=node                     (optional, path to Node 23.6+)

Wired into the agent loop by src/agent/memory.py (recall into each packet,
remember after each run, outcomes supersede).
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BRIDGE = os.path.join(_ROOT, "src", "integrations", "hmem_bridge.ts")

SUPPORTED_ENGINES = ("hmem",)


class MeterlessEngineError(RuntimeError):
    """The H-MEM bridge failed or returned an error."""


class MeterlessEngine:
    """remember()/recall() over the Meterless H-MEM engine."""

    def __init__(
        self,
        persist_dir: str = "~/.quantpilot/hmem",
        engine: str = "hmem",
        node: str = "node",
        timeout: int = 30,
    ) -> None:
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(f"unsupported Meterless engine: {engine!r} (supported: {SUPPORTED_ENGINES})")
        self.engine = engine
        self.persist_dir = os.path.expanduser(persist_dir)
        self.node = node
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "MeterlessEngine":
        """Build from .env / environment settings."""
        return cls(
            persist_dir=os.environ.get("METERLESS_HMEM_DIR", "~/.quantpilot/hmem"),
            engine=os.environ.get("METERLESS_ENGINE", "hmem"),
            node=os.environ.get("METERLESS_NODE", "node"),
        )

    def _call(self, payload: dict) -> Any:
        payload = dict(payload, persistDir=self.persist_dir)
        try:
            proc = subprocess.run(
                [self.node, "--experimental-transform-types", "--no-warnings", _BRIDGE],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=_ROOT,
            )
        except FileNotFoundError as error:
            raise MeterlessEngineError(f"Node not found ({self.node}); H-MEM needs Node 23.6+") from error
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            raise MeterlessEngineError(f"H-MEM bridge gave no output: {proc.stderr.strip()[:300]}")
        reply = json.loads(lines[-1])
        if not reply.get("ok"):
            raise MeterlessEngineError(reply.get("error", "unknown H-MEM error"))
        return reply["result"]

    def remember(
        self,
        key: str,
        value: Any,
        tags: Optional[List[str]] = None,
        confidence: float = 0.9,
    ) -> str:
        """Store a JSON-serializable value under key. Returns the memory id."""
        if not key or not key.strip():
            raise ValueError("key must be a non-empty string")
        json.dumps(value)  # fail early on values H-MEM cannot store
        result = self._call(
            {"op": "remember", "key": key, "value": value, "tags": tags or [], "confidence": confidence}
        )
        return result["id"]

    def recall(
        self,
        query: str,
        top_n: int = 5,
        threshold: Optional[float] = None,
    ) -> List[dict]:
        """Ranked memories for a query: [{id, key, value, relevance, layer}]."""
        payload = {"op": "recall", "query": query, "topN": top_n}
        if threshold is not None:
            payload["threshold"] = threshold
        return self._call(payload)["items"]

    def count(self) -> int:
        """Number of live (not superseded) memories."""
        return self._call({"op": "count"})["count"]
