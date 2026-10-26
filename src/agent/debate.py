"""Debate agent loop (agent core, Day 3 drop).

The desk's debate pattern (debate.py in the trading stack), rebuilt
on the packet: prefilter happens upstream (liquidity board), then

    bull case -> bear case -> judge verdict

with an Evaluator feedback loop on top, per the official HackOS
Demo Video Guide: the demo must show at least two agents with
clear roles AND a real collaboration loop. The judge (Evaluator)
may return a fourth verdict, INSUFFICIENT_EVIDENCE, naming the
specific gap - a missing packet field or an unsupported claim.
On that verdict the loop re-runs ONCE: bull and bear get a
follow-up pass with the judge's gap note in their prompts (they
must address the gap from the packet or explicitly concede it
cannot be resolved), and the judge re-verdicts. The second
verdict cannot be INSUFFICIENT_EVIDENCE - if the gap persists it
lands on WATCH, never on a guess. Both rounds are kept in the
run record (result["rounds"]) and the journal stores that record
whole, so the loop is visible in the demo and in the journal.

Grounding discipline (the Cluse truth-layer lesson): every prompt
orders the model to use ONLY packet values, to cite them, and to
say "unknown in packet" instead of estimating. The judge's parsed
verdict is also constrained in code: a TRADE with no direction is
downgraded to WATCH rather than trusted.

All LLM calls go through src/integrations/llm.py. The client is
injectable (anything with chat_text(prompt, model, max_tokens)),
so tests run on a mock - no live calls in the test suite.

US markets only. Research output only: the agent proposes, a
human approves every order.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from ..integrations.llm import get_llm_provider
from .grounding import grounding_report, is_verified, verify_key_evidence
from .packet import packet_fingerprint

VERDICT_TRADE = "TRADE"
VERDICT_WATCH = "WATCH"
VERDICT_SKIP = "SKIP"
VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
FINAL_VERDICTS = (VERDICT_TRADE, VERDICT_WATCH, VERDICT_SKIP)
ALL_VERDICTS = FINAL_VERDICTS + (VERDICT_INSUFFICIENT,)
DIRECTIONS = ("call", "put", "none")

GROUNDING_RULES = """GROUNDING RULES - non-negotiable:
1. Use ONLY numbers and facts that appear in the packet JSON. No outside knowledge, no remembered prices, no news that is not in the packet.
2. Cite the packet value behind every claim, in brackets, like [liquidity.score = 42.5] or [indicators.long_filter.price_above_200dma = true].
3. Where a packet value is null or a section is missing, write "unknown in packet". Never estimate, extrapolate, or fill a gap with a plausible number.
4. Argue only from the packet even when it argues against your assigned side: a weak case stated honestly beats a strong case built on invented evidence."""


# ----------------------------------------------------------------------
# prompts
# ----------------------------------------------------------------------
def _packet_json(packet: Dict) -> str:
    return json.dumps(packet, indent=1, sort_keys=True, default=str)


def _gap_section(gap_note: Optional[str]) -> str:
    if not gap_note:
        return ""
    return f"""

EVALUATOR FEEDBACK - ROUND 1: The judge returned INSUFFICIENT_EVIDENCE and named this gap:
"{gap_note}"
You must either resolve the gap using ONLY values present in the packet, or explicitly concede by including this sentence in your answer: CONCEDED: this gap cannot be resolved from the packet.
Do not invent the missing value, and do not repeat a claim the judge flagged as unsupported."""


def build_bull_prompt(
    packet: Dict,
    gap_note: Optional[str] = None,
    round_no: int = 1,
) -> str:
    """Bull analyst prompt (round 2 carries the judge's gap note)."""
    return f"""You are the BULL analyst on a three-stage options research desk (bull, bear, judge). Your job: the strongest honest case FOR a long-premium trade in {packet.get('symbol')}, calls side, over a 1-7 day horizon.

{GROUNDING_RULES}

EVIDENCE PACKET (JSON):
{_packet_json(packet)}{_gap_section(gap_note)}

Write 4-6 sentences of plain English. End with one line in this exact shape:
STRONGEST BULL EVIDENCE: <the single most persuasive packet value, cited>"""


def build_bear_prompt(
    packet: Dict,
    bull_text: str,
    gap_note: Optional[str] = None,
    round_no: int = 1,
) -> str:
    """Bear analyst prompt: argues the put side AND attacks the bull."""
    return f"""You are the BEAR analyst on a three-stage options research desk (bull, bear, judge). Your job: the strongest honest case AGAINST the bull thesis in {packet.get('symbol')} - for puts, or for standing aside - over a 1-7 day horizon. Attack the bull case's weakest evidence directly.

{GROUNDING_RULES}

EVIDENCE PACKET (JSON):
{_packet_json(packet)}

THE BULL ANALYST WROTE:
{bull_text}{_gap_section(gap_note)}

Write 4-6 sentences of plain English. End with one line in this exact shape:
STRONGEST BEAR EVIDENCE: <the single most persuasive packet value, cited>"""


def build_judge_prompt(
    packet: Dict,
    bull_text: str,
    bear_text: str,
    round_no: int = 1,
    gap_note: Optional[str] = None,
) -> str:
    """Judge / Evaluator prompt. Round 2 is final: no INSUFFICIENT."""
    if round_no >= 2:
        verdict_rule = f"""This is the FINAL round. The verdict MUST be one of TRADE, WATCH, SKIP - INSUFFICIENT_EVIDENCE is not available this round. If the round-1 gap ("{gap_note}") persists or the analysts conceded it cannot be resolved from the packet, return WATCH (or SKIP if the packet affirmatively argues against any trade). Never guess past a missing value."""
    else:
        verdict_rule = """The verdict must be one of:
- TRADE: the packet evidence is one-sided, the guardrail checks pass, and a trade card can be built.
- WATCH: the setup is plausible but something material is unproven.
- SKIP: the packet argues against trading this name now.
- INSUFFICIENT_EVIDENCE: a specific packet field is missing or a claim in either case is unsupported by the packet, so no honest verdict is possible yet. Name the gap exactly in the "gap" field - which field was missing or which claim was unsupported. Only use this when the gap is specific and material."""
    return f"""You are the JUDGE (Evaluator) on a three-stage options research desk. You decide from the evidence packet and the two analyst cases - nothing else.

{GROUNDING_RULES}

EVIDENCE PACKET (JSON):
{_packet_json(packet)}

BULL CASE:
{bull_text}

BEAR CASE:
{bear_text}

{verdict_rule}

A TRADE also requires: direction "call" or "put" (a directionless TRADE is invalid and will be downgraded), and it should not contradict a failed guardrail check or a red_flag in the packet's events section without saying why in key_evidence.

Reply with ONLY a JSON object, no markdown fences, with exactly these fields:
{{"verdict": "TRADE" | "WATCH" | "SKIP" | "INSUFFICIENT_EVIDENCE", "conviction": <integer 0-10>, "direction": "call" | "put" | "none", "gap": <string naming the gap, or null>, "key_evidence": [<up to 3 strings, each exactly "packet.path = value" as it appears in the packet, e.g. "liquidity.score = 42.5" - code verifies every one against the packet and a TRADE whose evidence does not verify is downgraded>], "biggest_risk": <one sentence>, "summary": <one or two sentences: the decision and why>}}"""


# ----------------------------------------------------------------------
# judge parsing
# ----------------------------------------------------------------------
def parse_judge(text: str) -> Dict:
    """Parse the judge's reply into a verdict block.

    Tolerant on purpose (fences, surrounding prose), strict on
    values (unknown verdicts land on WATCH, parse_ok says so).
    """
    parsed: Optional[Dict] = None
    if text:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                candidate = json.loads(match.group(0))
                if isinstance(candidate, dict):
                    parsed = candidate
            except ValueError:
                parsed = None
    if parsed is not None:
        verdict = str(parsed.get("verdict", "")).upper().replace(" ", "_")
        if verdict not in ALL_VERDICTS:
            verdict = VERDICT_WATCH
        direction = str(parsed.get("direction", "none")).lower()
        if direction not in DIRECTIONS:
            direction = "none"
        conviction = parsed.get("conviction")
        try:
            conviction = max(0, min(10, int(conviction)))
        except (TypeError, ValueError):
            conviction = 0
        gap = parsed.get("gap")
        return {
            "verdict": verdict,
            "conviction": conviction,
            "direction": direction,
            "gap": str(gap) if gap else None,
            "key_evidence": [
                str(e) for e in (parsed.get("key_evidence") or [])
            ][:3],
            "biggest_risk": str(parsed.get("biggest_risk") or ""),
            "summary": str(parsed.get("summary") or ""),
            "parse_ok": True,
            "forced_default": False,
        }
    # Fallback: no JSON at all. Scan for a verdict word, stay safe.
    upper = (text or "").upper()
    verdict = VERDICT_WATCH
    if "INSUFFICIENT" in upper:
        verdict = VERDICT_INSUFFICIENT
    elif "SKIP" in upper:
        verdict = VERDICT_SKIP
    elif "TRADE" in upper:
        verdict = VERDICT_TRADE
    gap = None
    if verdict == VERDICT_INSUFFICIENT:
        gap_match = re.search(r"gap[:\-]\s*(.+)", text or "", re.IGNORECASE)
        gap = gap_match.group(1).strip() if gap_match else None
    return {
        "verdict": verdict,
        "conviction": 0,
        "direction": "none",
        "gap": gap,
        "key_evidence": [],
        "biggest_risk": "",
        "summary": "",
        "parse_ok": False,
        "forced_default": False,
    }


def _enforce_invariants(judge: Dict, round_no: int) -> Dict:
    """Code-level constraints the model cannot talk its way past."""
    judge = dict(judge)
    notes: List[str] = []
    if round_no >= 2 and judge["verdict"] == VERDICT_INSUFFICIENT:
        judge["verdict"] = VERDICT_WATCH
        judge["forced_default"] = True
        notes.append(
            "second INSUFFICIENT_EVIDENCE is not permitted - the gap "
            "persisted, so the loop defaulted to WATCH rather than guess"
        )
    if judge["verdict"] == VERDICT_TRADE and judge["direction"] == "none":
        judge["verdict"] = VERDICT_WATCH
        notes.append("TRADE without a direction is invalid - downgraded to WATCH")
    if notes:
        judge["loop_note"] = "; ".join(notes)
    return judge


def _enforce_grounding(judge: Dict, packet: Dict) -> Dict:
    """A TRADE must rest on key_evidence that verifies against the packet.

    The model cannot talk its way past this one either: every
    key_evidence citation must resolve to the packet value it states,
    and at least one must exist. Otherwise the TRADE lands on WATCH
    with the failed citations named.
    """
    judge = dict(judge)
    cites = verify_key_evidence(judge.get("key_evidence") or [], packet)
    judge["key_evidence_check"] = cites
    if judge["verdict"] != VERDICT_TRADE:
        return judge
    bad = [c for c in cites if not is_verified(c)]
    if cites and not bad:
        return judge
    if not cites:
        why = "key_evidence is empty - a TRADE needs packet citations"
    else:
        why = "key_evidence citation(s) failed against the packet: " + "; ".join(
            (f"'{c['stated']}' cites no packet field" if c["path"] is None else
             f"[{c['path']} = {c['stated']}] is {c['status']}")
            + (f" (packet: {c['actual']})" if c["status"] == "mismatch" else "")
            for c in bad
        )
    judge["verdict"] = VERDICT_WATCH
    judge["forced_default"] = True
    note = f"TRADE downgraded to WATCH - {why}"
    judge["loop_note"] = (
        f"{judge['loop_note']}; {note}" if judge.get("loop_note") else note
    )
    return judge


def _judge_text(judge: Dict) -> str:
    # Bare "path = value" evidence is bracketed so the report counts it.
    evidence = [
        e if e.lstrip().startswith("[") or "=" not in e else f"[{e}]"
        for e in judge.get("key_evidence") or []
    ]
    return " ".join(
        evidence + [judge.get("summary") or "", judge.get("biggest_risk") or ""]
    )


# ----------------------------------------------------------------------
# why composition (deterministic: built from the outputs, no LLM)
# ----------------------------------------------------------------------
def _clip_sentences(text: str, max_sentences: int = 2, max_chars: int = 420) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    clipped = " ".join(parts[:max_sentences]).strip()
    return clipped[:max_chars].rstrip()


def _compose_why(
    packet: Dict,
    rounds: List[Dict],
    final: Dict,
) -> str:
    symbol = packet.get("symbol", "?")
    last = rounds[-1]
    pieces: List[str] = []
    if len(rounds) > 1:
        gap = rounds[0].get("gap") or "an unnamed evidence gap"
        pieces.append(
            f"Round 1 came back INSUFFICIENT_EVIDENCE (gap: {gap}). "
            "After the follow-up pass, "
        )
        head = ""
    else:
        head = f"{symbol}: "
    verdict_line = (
        f"{head}{final['verdict']} (conviction {final['conviction']}/10, "
        f"{final['direction']} bias)."
    )
    pieces.append(verdict_line)
    if final.get("summary"):
        pieces.append(final["summary"])
    bull = _clip_sentences(last["bull_case"])
    if bull:
        pieces.append(f"Bull case: {bull}")
    bear = _clip_sentences(last["bear_case"])
    if bear:
        pieces.append(f"Bear case: {bear}")
    if final.get("biggest_risk"):
        pieces.append(f"Biggest risk: {final['biggest_risk']}")
    if final.get("forced_default") and final.get("loop_note"):
        pieces.append(f"Code override: {final['loop_note']}.")
    return " ".join(pieces)


# ----------------------------------------------------------------------
# the loop
# ----------------------------------------------------------------------
def run_debate(
    packet: Dict,
    client=None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
) -> Dict:
    """Run bull -> bear -> judge, with the Evaluator feedback loop.

    client: anything with chat_text(prompt, model, max_tokens)
    (src.integrations.llm.LLMProvider qualifies). None resolves the
    configured provider via llm.py. The run record keeps BOTH
    rounds when the loop fires - the journal stores it whole.
    """
    if client is None:
        client = get_llm_provider()
    model_name = model
    if model_name is None:
        cfg = getattr(client, "config", None)
        model_name = getattr(cfg, "model", None)

    rounds: List[Dict] = []
    gap_note: Optional[str] = None
    final: Optional[Dict] = None
    for round_no in (1, 2):
        bull = client.chat_text(
            build_bull_prompt(packet, gap_note=gap_note, round_no=round_no),
            model=model,
            max_tokens=max_tokens,
        )
        bear = client.chat_text(
            build_bear_prompt(
                packet, bull, gap_note=gap_note, round_no=round_no
            ),
            model=model,
            max_tokens=max_tokens,
        )
        judge_prompt = build_judge_prompt(
            packet, bull, bear, round_no=round_no, gap_note=gap_note
        )
        judge_raw = client.chat_text(judge_prompt, model=model, max_tokens=max_tokens)
        judge_retried = False
        if not (judge_raw or "").strip():
            # Measured live (TSLA, Oct 22): ultra-550b spent the whole
            # budget reasoning and returned no answer. One retry with
            # twice the budget; still nothing is recorded as such.
            judge_retried = True
            judge_raw = client.chat_text(
                judge_prompt, model=model, max_tokens=max_tokens * 2
            )
        judge = _enforce_grounding(
            _enforce_invariants(parse_judge(judge_raw), round_no), packet
        )
        judge["retried_empty"] = judge_retried
        if not (judge_raw or "").strip():
            judge["no_reply"] = True
            judge["summary"] = (
                "The judge returned no answer (the model exhausted its token "
                "budget reasoning, twice), so the code defaulted to WATCH - no "
                "verdict was invented."
            )
        grounding = {
            "bull": grounding_report(bull, packet),
            "bear": grounding_report(bear, packet),
            "judge": grounding_report(_judge_text(judge), packet),
        }
        rounds.append(
            {
                "round": round_no,
                "gap_note_in": gap_note,
                "bull_case": bull,
                "bear_case": bear,
                "judge_raw": judge_raw,
                "judge": judge,
                "grounding": grounding,
                "verdict": judge["verdict"],
                "gap": (
                    judge.get("gap")
                    if judge["verdict"] == VERDICT_INSUFFICIENT
                    else None
                ),
            }
        )
        final = judge
        if judge["verdict"] != VERDICT_INSUFFICIENT:
            break
        gap_note = judge.get("gap") or "unspecified evidence gap"

    assert final is not None  # loop always runs at least round 1
    totals = {"cited": 0, "verified": 0, "mismatched": 0, "unresolved": 0,
              "unsupported_numbers": 0}
    for r in rounds:
        for rep in r["grounding"].values():
            totals["cited"] += rep["cited"]
            totals["verified"] += rep["verified"]
            totals["mismatched"] += len(rep["mismatched"])
            totals["unresolved"] += len(rep["unresolved"])
            totals["unsupported_numbers"] += len(rep["unsupported_numbers"])
    return {
        "symbol": packet.get("symbol"),
        "packet_hash": packet_fingerprint(packet),
        "model": model_name,
        "rounds": rounds,
        "looped": len(rounds) > 1,
        "gap_history": [r["gap"] for r in rounds if r["gap"]],
        "bull_case": rounds[-1]["bull_case"],
        "bear_case": rounds[-1]["bear_case"],
        "judge": final,
        "verdict": final["verdict"],
        "conviction": final["conviction"],
        "direction": final["direction"],
        "grounding": totals,
        "why": _compose_why(packet, rounds, final),
    }
