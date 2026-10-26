"""Impact study: the guardrail statistics are counted, and the modeled
probability of profit matches an independent lognormal calculation."""
from __future__ import annotations

import importlib.util
import math
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("impact_study", REPO / "scripts" / "impact_study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)

AS_OF = datetime(2026, 10, 26, 19, tzinfo=timezone.utc).timestamp()   # 15:00 ET
EXP = int(datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp())    # 4 DTE on the ET date


def _c(strike, bid, ask, iv=0.40):
    return {"contractSymbol": f"T{strike}", "strike": strike, "bid": bid, "ask": ask,
            "lastPrice": (bid + ask) / 2, "volume": 10, "openInterest": 100,
            "impliedVolatility": iv, "expiration": EXP}


def capture():
    return {"as_of_epoch": AS_OF, "captured_at_utc": "test", "names": {"TST": {"spot": 100.0, "chains": [
        {"expiration": EXP, "dte": 4,
         "calls": [_c(100, 1.90, 2.10), _c(115, 0.01, 0.03), _c(120, 0.0, 0.02)],   # last one has no bid: excluded
         "puts": [_c(85, 0.02, 0.04)]}]}}}


def test_universe_and_cheap_counts():
    rows = study.evaluate_capture(capture())
    assert len(rows) == 3                       # the no-bid contract is not tradeable
    s = study.summarize(rows)
    assert s["cheap"]["contracts"] == 2          # $0.02 and $0.03 premiums
    assert s["cheap"]["share_failing_guardrail"] == 1.0
    assert s["guardrail_passers"]["contracts"] == 1


def test_pop_matches_independent_lognormal():
    """ATM 100 call, premium $2.00 (mid), breakeven 102, 4 days, IV 40%,
    r = 4.3%: P(S_T > 102) = N(d) with
    d = (ln(100/102) + (0.043 - 0.5 x 0.16) x 4/365) / (0.40 x sqrt(4/365))."""
    T = 4 / 365
    d = (math.log(100 / 102) + (0.043 - 0.5 * 0.40 ** 2) * T) / (0.40 * math.sqrt(T))
    expected = 0.5 * (1 + math.erf(d / math.sqrt(2)))
    row = [r for r in study.evaluate_capture(capture()) if r["strike"] == 100][0]
    assert abs(row["pop"] - expected) < 1e-4
    assert round(expected, 3) == 0.315


def test_committed_study_reproduces():
    folder = REPO / "samples" / "impact-study-2026-10-26"
    import json
    cap = json.loads((folder / "chains_raw.json").read_text())
    s = study.summarize(study.evaluate_capture(cap))
    committed = json.loads((folder / "impact_study.json").read_text())
    assert s["contracts"] == committed["contracts"] == 5349
    assert s["cheap"]["contracts"] == committed["cheap"]["contracts"]
