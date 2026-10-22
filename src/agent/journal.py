"""Self-scoring journal (build plan module 8) + 2-loss breaker (9).

The ledger data model from the trading stack, applied to agent
output: SQLite, append-only. An entry row (timestamp, symbol,
verdict, conviction, card JSON, the full debate run record, packet
hash) is written once and NEVER rewritten. Outcomes are appended
later as separate rows, so the journal can always show what the
agent said at the time and what the market did afterwards - "the
journal that writes itself", and the demo's proof that the
Evaluator loop really ran (both debate rounds live in the entry).

Scoring: an outcome marks the underlying's move since the entry
price. A TRADE entry hits when the move agrees with the card's
direction (call: up, put: down). WATCH / SKIP entries can carry
outcomes for the record but are never scored as hits or losses -
the agent did not take the trade. Stats use each entry's LATEST
outcome; the append-only history stays intact underneath.

Circuit breaker (module 9): after CIRCUIT_BREAKER_LOSSES
consecutive losing scored entries, breaker_state() reports
tripped, with the one line the morning briefing prints.

US markets only. Research journal: no orders, no positions.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .. import config
from ..data.provider import MarketDataProvider
from .packet import packet_fingerprint

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    verdict TEXT,
    conviction INTEGER,
    direction TEXT,
    entry_price REAL,
    card_json TEXT,
    debate_json TEXT,
    packet_hash TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES entries(id),
    ts TEXT NOT NULL,
    spot REAL,
    move_pct REAL,
    hit INTEGER,
    note TEXT
);
CREATE TABLE IF NOT EXISTS iv_snapshots (
    symbol TEXT NOT NULL,
    day TEXT NOT NULL,
    atm_iv REAL NOT NULL,
    expiration INTEGER,
    ts TEXT NOT NULL,
    PRIMARY KEY (symbol, day)
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Journal:
    """Append-only SQLite journal of debate entries and outcomes."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or config.JOURNAL_DB_PATH
        folder = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(folder, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle ------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- entries (written once, never updated) -------------------------
    def record_entry(
        self,
        debate_result: Dict,
        card: Dict,
        packet: Optional[Dict] = None,
        entry_price: Optional[float] = None,
        ts: Optional[str] = None,
    ) -> int:
        """Append one entry; returns its id.

        The full debate run record (both rounds when the Evaluator
        loop fired) is stored in debate_json - that is what makes
        the loop visible in the journal and the demo.
        """
        if entry_price is None and packet is not None:
            entry_price = packet.get("spot")
        # The journal scores what the agent actually proposed: a judge
        # TRADE that the card (or the risk review) downgraded is not a
        # trade, so it is stored as WATCH and never scored as a hit or
        # a miss. The judge's own verdict stays in debate_json.
        verdict = debate_result.get("verdict")
        if verdict == "TRADE" and (card or {}).get("kind") == "no_trade":
            verdict = "WATCH"
        packet_hash = debate_result.get("packet_hash")
        if packet_hash is None and packet is not None:
            packet_hash = packet_fingerprint(packet)
        cur = self._conn.execute(
            "INSERT INTO entries (ts, symbol, verdict, conviction, "
            "direction, entry_price, card_json, debate_json, packet_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts or _now_iso(),
                debate_result.get("symbol")
                or (packet or {}).get("symbol"),
                verdict,
                debate_result.get("conviction"),
                debate_result.get("direction"),
                float(entry_price) if entry_price is not None else None,
                json.dumps(card, sort_keys=True, default=str),
                json.dumps(debate_result, sort_keys=True, default=str),
                packet_hash,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_entry(self, entry_id: int) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            return None
        return self._entry_dict(row)

    def list_entries(self, limit: Optional[int] = None) -> List[Dict]:
        sql = "SELECT * FROM entries ORDER BY id"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return [self._entry_dict(r) for r in self._conn.execute(sql)]

    def _entry_dict(self, row: sqlite3.Row) -> Dict:
        return {
            "id": row["id"],
            "ts": row["ts"],
            "symbol": row["symbol"],
            "verdict": row["verdict"],
            "conviction": row["conviction"],
            "direction": row["direction"],
            "entry_price": row["entry_price"],
            "card": json.loads(row["card_json"]) if row["card_json"] else None,
            "debate": (
                json.loads(row["debate_json"]) if row["debate_json"] else None
            ),
            "packet_hash": row["packet_hash"],
        }

    # -- outcomes (appended later, entries never rewritten) -------------
    def record_outcome(
        self,
        entry_id: int,
        spot: float,
        ts: Optional[str] = None,
        note: str = "",
    ) -> Dict:
        """Append an outcome for an entry and return it.

        hit is 1 / 0 only for TRADE entries with a direction and an
        entry price; otherwise None (recorded, never scored).
        """
        row = self._conn.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no journal entry {entry_id}")
        entry_price = row["entry_price"]
        ts_value = ts or _now_iso()
        move_pct: Optional[float] = None
        hit: Optional[int] = None
        if entry_price:
            move_pct = (float(spot) - float(entry_price)) / float(entry_price) * 100.0
            if row["verdict"] == "TRADE" and row["direction"] in ("call", "put"):
                if row["direction"] == "call":
                    hit = 1 if move_pct > 0 else 0
                else:
                    hit = 1 if move_pct < 0 else 0
        cur = self._conn.execute(
            "INSERT INTO outcomes (entry_id, ts, spot, move_pct, hit, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry_id,
                ts_value,
                float(spot),
                round(move_pct, 4) if move_pct is not None else None,
                hit,
                note,
            ),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid),
            "entry_id": entry_id,
            "ts": ts_value,
            "spot": float(spot),
            "move_pct": round(move_pct, 4) if move_pct is not None else None,
            "hit": hit,
            "note": note,
        }

    def list_outcomes(self, entry_id: Optional[int] = None) -> List[Dict]:
        if entry_id is None:
            rows = self._conn.execute(
                "SELECT * FROM outcomes ORDER BY id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM outcomes WHERE entry_id = ? ORDER BY id",
                (entry_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def open_entries(self) -> List[Dict]:
        """Entries with no outcome yet - the ones scoring still owes."""
        rows = self._conn.execute(
            "SELECT e.* FROM entries e "
            "LEFT JOIN outcomes o ON o.entry_id = e.id "
            "WHERE o.id IS NULL ORDER BY e.id"
        ).fetchall()
        return [self._entry_dict(r) for r in rows]

    def score_with_provider(
        self,
        provider: MarketDataProvider,
        ts: Optional[str] = None,
        note: str = "auto-score",
    ) -> Dict:
        """Mark every open entry against the provider's live quote."""
        scored: List[Dict] = []
        skipped: List[Dict] = []
        for entry in self.open_entries():
            try:
                quote = provider.get_quote(entry["symbol"])
                outcome = self.record_outcome(
                    entry["id"], float(quote["price"]), ts=ts, note=note
                )
                scored.append(outcome)
            except Exception as exc:  # one bad symbol must not sink scoring
                skipped.append(
                    {
                        "entry_id": entry["id"],
                        "symbol": entry["symbol"],
                        "error": str(exc),
                    }
                )
        return {"scored": scored, "skipped": skipped, "stats": self.stats()}

    # -- IV snapshots (Part C addition 3) -------------------------------
    def record_iv_snapshot(
        self,
        symbol: str,
        day: str,
        atm_iv: Optional[float],
        expiration: Optional[int] = None,
    ) -> bool:
        """Store one ET day's at-the-money IV for a symbol.

        First snapshot of the day wins (ledger model: never rewritten).
        Returns False when nothing was stored (unknown IV or the day is
        already recorded).
        """
        if atm_iv is None or float(atm_iv) <= 0:
            return False
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO iv_snapshots (symbol, day, atm_iv, "
            "expiration, ts) VALUES (?, ?, ?, ?, ?)",
            (symbol, day, float(atm_iv), expiration, _now_iso()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def iv_history(self, symbol: str, before_day: Optional[str] = None) -> Dict:
        """IV range from our own snapshots, labeled by how much exists.

        low/high are None until config.IV_SNAPSHOT_MIN_DAYS distinct
        days exist - a rank over a handful of days would be noise
        dressed up as a number. before_day excludes that day and later
        (today's IV is ranked against history, not against itself).
        """
        sql = "SELECT day, atm_iv FROM iv_snapshots WHERE symbol = ?"
        params: list = [symbol]
        if before_day is not None:
            sql += " AND day < ?"
            params.append(before_day)
        rows = self._conn.execute(sql + " ORDER BY day", params).fetchall()
        days = len(rows)
        out: Dict = {"days": days, "low": None, "high": None, "basis": None}
        if days >= config.IV_SNAPSHOT_MIN_DAYS:
            ivs = [float(r["atm_iv"]) for r in rows]
            out["low"], out["high"] = min(ivs), max(ivs)
            label = (
                "snapshot-based" if days < config.IV_SNAPSHOT_FULL_DAYS
                else "own-history"
            )
            out["basis"] = f"{label} {days}-day"
        return out

    # -- stats + circuit breaker ----------------------------------------
    def _latest_hits(self) -> List[Dict]:
        """Per-entry latest scored outcome, in entry order."""
        rows = self._conn.execute(
            "SELECT e.id AS entry_id, e.symbol, e.verdict, o.hit, o.move_pct "
            "FROM entries e "
            "JOIN outcomes o ON o.entry_id = e.id "
            "WHERE o.id = (SELECT MAX(id) FROM outcomes WHERE entry_id = e.id) "
            "AND o.hit IS NOT NULL "
            "ORDER BY e.id"
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        total = self._conn.execute(
            "SELECT COUNT(*) AS n FROM entries"
        ).fetchone()["n"]
        outcome_count = self._conn.execute(
            "SELECT COUNT(*) AS n FROM outcomes"
        ).fetchone()["n"]
        latest = self._latest_hits()
        hits = sum(1 for r in latest if r["hit"] == 1)
        losses = sum(1 for r in latest if r["hit"] == 0)
        scored = hits + losses
        by_verdict: Dict[str, Dict] = {}
        for row in latest:
            bucket = by_verdict.setdefault(
                row["verdict"] or "unknown", {"scored": 0, "hits": 0}
            )
            bucket["scored"] += 1
            bucket["hits"] += 1 if row["hit"] == 1 else 0
        for bucket in by_verdict.values():
            bucket["hit_rate"] = (
                round(bucket["hits"] / bucket["scored"], 4)
                if bucket["scored"]
                else None
            )
        return {
            "entries": total,
            "outcomes": outcome_count,
            "scored_entries": scored,
            "hits": hits,
            "losses": losses,
            "hit_rate": round(hits / scored, 4) if scored else None,
            "by_verdict": by_verdict,
            "breaker": self.breaker_state(),
        }

    def breaker_state(self) -> Dict:
        """Module 9: the 2-loss circuit breaker, from scored entries."""
        streak = 0
        for row in self._latest_hits():
            streak = streak + 1 if row["hit"] == 0 else 0
        threshold = config.CIRCUIT_BREAKER_LOSSES
        tripped = streak >= threshold
        if tripped:
            line = (
                f"CIRCUIT BREAKER: {streak} consecutive losing scored "
                f"entries - the {threshold}-loss rule says stand down."
            )
        else:
            line = (
                f"Circuit breaker: {streak} consecutive losing scored "
                f"entries (trips at {threshold})."
            )
        return {
            "tripped": tripped,
            "consecutive_losses": streak,
            "threshold": threshold,
            "line": line,
        }


def open_journal(db_path: Optional[str] = None) -> Journal:
    """Factory mirroring the provider factories elsewhere in src/."""
    return Journal(db_path)
