"""Run SQL against the local Zetaris, one statement at a time.

Usage:
  .venv/bin/python scripts/zsql.py "SELECT 1"
  .venv/bin/python scripts/zsql.py --file sql/yahoo_finance_create.sql [--skip-exists]

Statements in a file are split on lines ending with ';'. Comment lines
starting with '--' are dropped. The API key is read from the environment or
~/.zetaris-api-key and is never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.integrations.zetaris import ZetarisProvider  # noqa: E402


def split_statements(text: str) -> list:
    statements, current = [], []
    for line in text.splitlines():
        if line.strip().startswith("--"):
            continue
        current.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(current).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def run_one(provider: ZetarisProvider, sql: str, limit: int) -> tuple:
    resp = requests.post(
        provider.rest_url + "/sql-editor/sqls/run",
        headers=provider._headers(),
        json={
            "queryId": str(uuid.uuid4()),
            "sql": sql,
            "source": "SqlEditor",
            "limit": limit,
        },
        timeout=600,
    )
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:500]
    return resp.status_code, body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sql", nargs="?")
    parser.add_argument("--file")
    parser.add_argument("--skip-exists", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pause", type=float, default=0.0,
                        help="seconds to wait after each statement that calls an endpoint")
    args = parser.parse_args()

    provider = ZetarisProvider.from_env()
    if not provider.api_key:
        print("Zetaris API key missing (env or key file)")
        return 1

    if args.file:
        with open(args.file) as fh:
            statements = split_statements(fh.read())
    elif args.sql:
        statements = [args.sql.strip().rstrip(";")]
    else:
        parser.error("give a statement or --file")

    for i, stmt in enumerate(statements, 1):
        first_line = stmt.splitlines()[0][:100]
        started = time.time()
        status, body = run_one(provider, stmt, args.limit)
        elapsed = time.time() - started
        text = body if isinstance(body, str) else json.dumps(body)
        if status == 200:
            print(f"[{i}/{len(statements)}] OK {elapsed:.1f}s  {first_line}")
            if isinstance(body, dict) and body.get("data"):
                cols = body.get("columns") or body.get("schema") or ""
                if cols:
                    print("   columns:", json.dumps(cols)[:400])
                for row in body["data"][: args.limit]:
                    print("  ", row)
        elif args.skip_exists and "exist" in text.lower():
            print(f"[{i}/{len(statements)}] SKIP (exists)  {first_line}")
        else:
            print(f"[{i}/{len(statements)}] FAIL HTTP {status} {elapsed:.1f}s  {first_line}")
            print("   ", text[:1500])
            return 2
        if args.pause and "REST TABLE" in stmt.upper():
            time.sleep(args.pause)
    return 0


if __name__ == "__main__":
    sys.exit(main())
