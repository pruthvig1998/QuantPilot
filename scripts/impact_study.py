#!/usr/bin/env python3
"""Impact study: how many cheap weekly options can actually win?

    .venv/bin/python scripts/impact_study.py [samples/impact-study-2026-10-26]

Reads chains_raw.json (live chains captured during US market hours for the
12-name watchlist, every expiry 1-7 days out), runs every contract through
QuantPilot's own probability guardrail (src/guardrail/probability.py), and
writes impact_study.json + a Markdown summary next to it. Deterministic:
the same capture always gives the same numbers.

Universe: contracts with a two-sided market (bid > 0 and ask > 0) - the
ones a retail trader could actually buy. "Probability of profit" is the
guardrail's model figure (lognormal, from the chain's own implied
volatility): a model estimate, labeled as such everywhere it appears.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from typing import Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.guardrail.probability import evaluate_contract  # noqa: E402

CHEAP_MAX = 1.00          # premium per share: $100 per contract or less
LOW_POP = 0.20            # "long shot": modeled probability of profit below 20%
BUCKETS = [(0.0, 0.50), (0.50, 1.00), (1.00, 2.00), (2.00, 5.00), (5.00, 1e9)]


def evaluate_capture(capture: Dict) -> List[Dict]:
    """Every tradeable contract in the capture, through the guardrail."""
    as_of = float(capture["as_of_epoch"])
    rows: List[Dict] = []
    for sym, entry in capture["names"].items():
        if "error" in entry:
            continue
        spot = float(entry["spot"])
        for ch in entry["chains"]:
            for side, key in (("call", "calls"), ("put", "puts")):
                for c in ch[key]:
                    bid, ask = c.get("bid") or 0, c.get("ask") or 0
                    if not (bid > 0 and ask > 0):
                        continue
                    ev = evaluate_contract(c, side, spot, as_of=as_of, expiration=ch["expiration"])
                    m = ev["metrics"]
                    if m["premium"] is None or m["probability_of_profit"] is None:
                        continue  # unknown stays out of the statistics, never filled in
                    rows.append({
                        "symbol": sym, "side": side, "strike": ev["strike"], "dte": ev["days_to_expiry"],
                        "premium": m["premium"], "pop": m["probability_of_profit"], "delta": m["delta"],
                        "breakeven_move_pct": m["breakeven_move_pct"],
                        "theta_usd_day": m["theta_burn_usd_per_day"],
                        "theta_pct_premium_day": (m["theta_burn_usd_per_day"] / (m["premium"] * 100.0) * 100.0)
                        if m["theta_burn_usd_per_day"] is not None and m["premium"] else None,
                        "rankable": ev["rankable"], "contract": ev["contract_symbol"],
                    })
    return rows


def _median(xs, nd=4):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), nd) if xs else None


def summarize(rows: List[Dict]) -> Dict:
    cheap = [r for r in rows if r["premium"] <= CHEAP_MAX]
    passers = [r for r in rows if r["rankable"]]
    cheap_pass = [r for r in cheap if r["rankable"]]

    def block(rs):
        return {
            "contracts": len(rs),
            "median_pop": _median([r["pop"] for r in rs]),
            "share_pop_below_20pct": round(sum(1 for r in rs if r["pop"] < LOW_POP) / len(rs), 4) if rs else None,
            "median_abs_breakeven_move_pct": _median([abs(r["breakeven_move_pct"]) for r in rs
                                                      if r["breakeven_move_pct"] is not None], 1),
            "median_theta_pct_of_premium_per_day": _median([r["theta_pct_premium_day"] for r in rs], 1),
        }

    buckets = []
    for lo, hi in BUCKETS:
        rs = [r for r in rows if lo < r["premium"] <= hi] if lo > 0 else [r for r in rows if r["premium"] <= hi]
        label = f"${lo:.2f}-${hi:.2f}" if hi < 1e8 else f"over ${lo:.2f}"
        if lo == 0:
            label = f"up to ${hi:.2f}"
        buckets.append({"premium": label, **block(rs),
                        "share_failing_guardrail": round(sum(1 for r in rs if not r["rankable"]) / len(rs), 4) if rs else None})

    per_name = []
    for sym in sorted({r["symbol"] for r in rows}):
        rs = [r for r in rows if r["symbol"] == sym]
        cheapest = min(rs, key=lambda r: r["premium"])
        ok = [r for r in rs if r["rankable"]]
        cheapest_ok = min(ok, key=lambda r: r["premium"]) if ok else None
        per_name.append({
            "symbol": sym, "contracts": len(rs),
            "cheapest": {k: cheapest[k] for k in ("contract", "premium", "pop", "breakeven_move_pct")},
            "cheapest_that_passes": ({k: cheapest_ok[k] for k in ("contract", "premium", "pop", "breakeven_move_pct")}
                                     if cheapest_ok else None),
        })
    return {
        "universe": "two-sided quotes (bid > 0 and ask > 0), expiries 1-7 days out",
        "contracts": len(rows),
        "all": block(rows),
        "cheap": {"definition": f"premium <= ${CHEAP_MAX:.2f} per share (${CHEAP_MAX * 100:.0f} per contract)",
                  **block(cheap),
                  "share_failing_guardrail": round(sum(1 for r in cheap if not r["rankable"]) / len(cheap), 4) if cheap else None},
        "guardrail_passers": block(passers),
        "cheap_that_pass": block(cheap_pass),
        "by_premium": buckets,
        "per_name": per_name,
    }


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def markdown(capture: Dict, s: Dict) -> str:
    c, p = s["cheap"], s["guardrail_passers"]
    lines = [
        "# Impact study: can cheap weekly options actually win?", "",
        f"Live capture: {capture['captured_at_utc']} UTC (US market hours), the 12-name watchlist, "
        "every expiry 1-7 days out. Universe: contracts with a two-sided quote. Every contract was run "
        "through QuantPilot's own probability guardrail. Probability of profit is the guardrail's model "
        "estimate (lognormal, from the chain's own implied volatility), not a guarantee.", "",
        f"**{s['contracts']:,} tradeable contracts evaluated.**", "",
        "## Headline", "",
        f"- **Cheap contracts** ({c['definition']}): {c['contracts']:,} of them. "
        f"Median modeled probability of profit **{pct(c['median_pop'])}**; "
        f"**{pct(c['share_pop_below_20pct'])}** have less than a 20% modeled chance; "
        f"**{pct(c['share_failing_guardrail'])}** fail QuantPilot's guardrail. "
        f"Median move needed just to break even: {c['median_abs_breakeven_move_pct']}%; "
        f"median time decay: {c['median_theta_pct_of_premium_per_day']}% of the premium per day.",
        f"- **Contracts that pass the guardrail**: {p['contracts']:,}. Median modeled probability of profit "
        f"**{pct(p['median_pop'])}**, median breakeven move {p['median_abs_breakeven_move_pct']}%.", "",
        "## By premium", "",
        "| Premium (per share) | Contracts | Median modeled PoP | PoP below 20% | Fail the guardrail | Median breakeven move | Median decay per day (% of premium) |",
        "|---|---|---|---|---|---|---|",
    ]
    for b in s["by_premium"]:
        lines.append(f"| {b['premium']} | {b['contracts']:,} | {pct(b['median_pop'])} | {pct(b['share_pop_below_20pct'])} | "
                     f"{pct(b['share_failing_guardrail'])} | {b['median_abs_breakeven_move_pct']}% | {b['median_theta_pct_of_premium_per_day']}% |")
    lines += ["", "## Cheapest contract vs the cheapest one that can actually win", "",
              "| Name | Cheapest contract (premium, modeled PoP) | Cheapest that passes the guardrail (premium, modeled PoP) |",
              "|---|---|---|"]
    for n in s["per_name"]:
        ch, ok = n["cheapest"], n["cheapest_that_passes"]
        lines.append(f"| {n['symbol']} | {ch['contract']} - ${ch['premium']:.2f}, {pct(ch['pop'])} | "
                     + (f"{ok['contract']} - ${ok['premium']:.2f}, {pct(ok['pop'])}" if ok else "none passes") + " |")
    lines += ["", "Reproduce: `.venv/bin/python scripts/impact_study.py samples/impact-study-2026-10-26` "
              "(reads chains_raw.json in that folder).", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    folder = (argv or sys.argv[1:] or [os.path.join(REPO, "samples", "impact-study-2026-10-26")])[0]
    capture = json.load(open(os.path.join(folder, "chains_raw.json")))
    s = summarize(evaluate_capture(capture))
    s["captured_at_utc"] = capture["captured_at_utc"]
    json.dump(s, open(os.path.join(folder, "impact_study.json"), "w"), indent=1)
    open(os.path.join(folder, "impact_study.md"), "w").write(markdown(capture, s))
    print(markdown(capture, s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
