#!/usr/bin/env python3
"""Open-interest feed check (audit item: section 4.1 of the review brief).

For each symbol, fetch the chain QuantPilot would actually trade (the
1-7 DTE expiry selection) straight from Yahoo and report how many
contracts print open interest > 0, alongside volume as a control.
Prints one JSON object; nothing is written anywhere else.

Usage:
    .venv/bin/python scripts/check_oi.py [SPY QQQ AAPL ...]
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.data.yahoo import YahooProvider  # noqa: E402
from src.guardrail.probability import fetch_trade_chain  # noqa: E402


def main(symbols) -> int:
    provider = YahooProvider()
    now = time.time()
    rows = []
    for symbol in symbols:
        try:
            chain = fetch_trade_chain(provider, symbol, as_of=now)
        except Exception as exc:
            rows.append({"symbol": symbol, "error": str(exc)})
            continue
        contracts = list(chain.get("calls", [])) + list(chain.get("puts", []))
        oi = [c.get("openInterest") for c in contracts]
        vol = [c.get("volume") for c in contracts]
        rows.append({
            "symbol": symbol,
            "expiration": chain.get("expiration"),
            "selection": chain.get("selection"),
            "contracts": len(contracts),
            "oi_missing": sum(1 for v in oi if v is None),
            "oi_positive": sum(1 for v in oi if (v or 0) > 0),
            "oi_total": sum(v or 0 for v in oi),
            "volume_positive": sum(1 for v in vol if (v or 0) > 0),
            "volume_total": sum(v or 0 for v in vol),
        })
    print(json.dumps({
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "AMZN"]))
