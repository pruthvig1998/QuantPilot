"""Grounding verifier (audit repair, Oct 22).

The debate prompts ORDER the model to cite packet values as
[path = value]; this module CHECKS that it did. Prompt rules are a
request, the verifier is the enforcement - the project's core claim
is traceability, so a citation that does not match the packet, or a
number that appears nowhere in the evidence, is surfaced in the run
record instead of being trusted.

Two checks, both deterministic:
- verify_citations(text, evidence): every [path = value] citation is
  resolved against the evidence JSON and compared. Status per
  citation: verified / mismatch (path exists, value differs) /
  unresolved (no such path).
- unsupported_numbers(text, evidence): every number written in the
  text must match some number present anywhere in the evidence
  (rounding-tolerant; a fraction may be written as a percent). Small
  integers (0-10) are allowed as ordinary prose ("4-6 sentences",
  "conviction 7/10").

Pure functions, no I/O, no LLM. US markets only.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Optional, Tuple

# [path = value] where path may itself carry [n] indices; one bracket
# may hold several "path = value" pairs separated by commas.
CITATION_RE = re.compile(
    r"\[\s*([A-Za-z_][\w.\-]*(?:\[\d+\][\w.\-]*)*)\s*=\s*((?:[^\[\]]|\[\d+\])+?)\s*\]"
)
_PAIR_SPLIT_RE = re.compile(r",\s*(?=[A-Za-z_][\w.\-]*(?:\[\d+\][\w.\-]*)*\s*=)")
_PAIR_RE = re.compile(r"^\s*([A-Za-z_][\w.\-]*(?:\[\d+\][\w.\-]*)*)\s*=\s*(.+?)\s*$")
# Numbers as models write them: 1,234.5  -5.31%  $2.15  212k  1.0e-05
NUMBER_RE = re.compile(
    r"(?<![\w.])-?\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:[eE]([-+]?\d+))?(%|[kKmM](?![a-zA-Z]))?"
)
SMALL_INT_MAX = 10
CLOCK_RE = re.compile(r"(?<![\d.])\d{1,2}:\d{2}(?::\d{2})?(?!\d)")

_MISSING = object()


# ----------------------------------------------------------------------
# path resolution
# ----------------------------------------------------------------------
def _tokens(path: str) -> List[str]:
    path = path.strip()
    for prefix in ("packet.", "evidence."):
        if path.startswith(prefix):
            path = path[len(prefix):]
    out: List[str] = []
    for part in path.split("."):
        # name[0][1] -> name, 0, 1
        head, *idx = re.split(r"\[", part)
        if head:
            out.append(head)
        out.extend(i.rstrip("]") for i in idx)
    return out


def resolve_path(evidence, path: str):
    """Value at a dotted path (list indices as [n] or .n), or _MISSING."""
    node = evidence
    for tok in _tokens(path):
        if isinstance(node, dict):
            if tok not in node:
                return _MISSING
            node = node[tok]
        elif isinstance(node, list):
            try:
                node = node[int(tok)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return node


def _leaf_paths(node, prefix=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaf_paths(v, prefix + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _leaf_paths(v, prefix + (str(i),))
    else:
        yield prefix, node


def _is_subsequence(short: List[str], full) -> bool:
    it = iter(full)
    return all(tok in it for tok in short)


def resolve_path_lenient(evidence, path: str):
    """(value, corrected_path) when the cited path names exactly ONE real
    leaf whose path contains the cited tokens in order and ends on the
    same key - e.g. "candidates[0].metrics.delta" for the real
    "candidates.0.evaluation.metrics.delta". Ambiguity resolves to
    nothing: a path is never guessed between candidates."""
    want = _tokens(path)
    if not want:
        return _MISSING, None
    hits = [
        (full, value)
        for full, value in _leaf_paths(evidence)
        if full and full[-1] == want[-1] and full[0] == want[0]
        and _is_subsequence(want, full)
    ]
    if len(hits) != 1:
        return _MISSING, None
    full, value = hits[0]
    return value, ".".join(full)


# ----------------------------------------------------------------------
# value comparison
# ----------------------------------------------------------------------
def _number_from_match(m) -> Tuple[float, int]:
    """(value, decimals) for a NUMBER_RE match. Precision follows the
    digits written: 212k carries thousands precision, 1.5e-05 carries
    the exponent, so rounding tolerance scales with the notation."""
    whole = m.group(1).replace(",", "")
    frac = m.group(2) or ""
    decimals = len(frac) - 1 if frac else 0
    value = float(whole + frac)
    if m.group(3):
        exp = int(m.group(3))
        value *= 10 ** exp
        decimals -= exp
    suffix = (m.group(4) or "").lower()
    if suffix == "k":
        value *= 1e3
        decimals -= 3
    elif suffix == "m":
        value *= 1e6
        decimals -= 6
    return value, decimals


def _parse_number(text: str) -> Optional[Tuple[float, int]]:
    """(value, decimals written) of the first number in text, or None."""
    match = NUMBER_RE.search(text)
    if not match:
        return None
    return _number_from_match(match)


def _close(stated: float, decimals: int, actual: float) -> bool:
    """stated equals actual at the precision it was written with."""
    tol = 0.5 * 10 ** (-decimals) + 1e-9 * max(1.0, abs(actual))
    return abs(abs(stated) - abs(actual)) <= tol


def number_matches(stated: float, decimals: int, actual: float) -> bool:
    """Match as written, or a fraction written as a percent."""
    return _close(stated, decimals, actual) or _close(stated, decimals, actual * 100.0)


def values_match(stated: str, actual) -> bool:
    s = stated.strip().strip("\"'").lower()
    if isinstance(actual, bool):
        return s in ("true", "yes") if actual else s in ("false", "no")
    if actual is None:
        return s in ("null", "none", "unknown", "n/a", "unknown in packet")
    if isinstance(actual, (int, float)):
        parsed = _parse_number(s)
        return parsed is not None and number_matches(parsed[0], parsed[1], float(actual))
    if isinstance(actual, str):
        a = actual.strip().lower()
        return s == a or (len(s) >= 3 and (s in a or a in s))
    if isinstance(actual, (list, dict)):
        # Citing a whole object: accept when the stated text is in it.
        return s in json.dumps(actual, default=str).lower()
    return s == str(actual).lower()


# ----------------------------------------------------------------------
# public checks
# ----------------------------------------------------------------------
def verify_citations(text: str, evidence: Dict) -> List[Dict]:
    """Every [path = value] citation in text, checked against evidence."""
    pairs: List[Tuple[str, str]] = []
    for match in CITATION_RE.finditer(text or ""):
        body = f"{match.group(1)} = {match.group(2)}"
        for part in _PAIR_SPLIT_RE.split(body):
            pair = _PAIR_RE.match(part)
            if pair:
                pairs.append((pair.group(1), pair.group(2)))
    results: List[Dict] = []
    for path, stated in pairs:
        actual = resolve_path(evidence, path)
        corrected = None
        if actual is _MISSING:
            actual, corrected = resolve_path_lenient(evidence, path)
        if actual is _MISSING:
            status = "unresolved"
            actual_out = None
        else:
            ok = values_match(stated, actual)
            status = (
                ("verified_path_corrected" if corrected else "verified")
                if ok else "mismatch"
            )
            actual_out = actual if not isinstance(actual, (dict, list)) else "<object>"
        row = {"path": path, "stated": stated, "actual": actual_out, "status": status}
        if corrected:
            row["resolved_path"] = corrected
        results.append(row)
    return results


BARE_CITATION_RE = re.compile(r"^\s*\[?\s*([A-Za-z_][\w.\[\]\-]*)\s*[=:]\s*(.+?)\s*\]?\s*$")


def verify_key_evidence(items: Iterable[str], evidence: Dict) -> List[Dict]:
    """Judge key_evidence: each item is "path = value" (brackets optional)."""
    results: List[Dict] = []
    for item in items or []:
        found = verify_citations(item, evidence)
        if not found:
            bare = BARE_CITATION_RE.match(item or "")
            if bare:
                found = verify_citations(f"[{bare.group(1)} = {bare.group(2)}]", evidence)
        if not found:
            found = [{"path": None, "stated": item, "actual": None,
                      "status": "uncited"}]
        results.extend(found)
    return results


def is_verified(citation: Dict) -> bool:
    return citation.get("status", "").startswith("verified")


def _evidence_numbers(evidence) -> List[float]:
    blob = json.dumps(evidence, default=str)
    return sorted(set(abs(_number_from_match(m)[0]) for m in NUMBER_RE.finditer(blob)))


def unsupported_numbers(
    text: str,
    evidence,
    allow: Iterable[float] = (),
) -> List[str]:
    """Numbers written in text that appear nowhere in the evidence."""
    pool = _evidence_numbers(evidence) + [abs(float(a)) for a in allow]
    out: List[str] = []
    clock = [c.span() for c in CLOCK_RE.finditer(text or "")]
    for m in NUMBER_RE.finditer(text or ""):
        token = m.group(0)
        if any(lo <= m.start() < hi for lo, hi in clock):
            continue  # "13:50" is a time of day, not a claimed value
        value, decimals = _number_from_match(m)
        value = abs(value)
        if decimals == 0 and value <= SMALL_INT_MAX and not m.group(3):
            continue
        if any(number_matches(value, decimals, n) for n in pool):
            continue
        out.append(token)
    return out


def grounding_report(text: str, evidence: Dict, allow: Iterable[float] = ()) -> Dict:
    """Citations + free numbers for one piece of model text."""
    cites = verify_citations(text, evidence)
    # Numbers inside citations are judged by the citation check.
    bare = CITATION_RE.sub(" ", text or "")
    free = unsupported_numbers(bare, evidence, allow=allow)
    return {
        "citations": cites,
        "cited": len(cites),
        "verified": sum(1 for c in cites if is_verified(c)),
        "path_corrected": sum(1 for c in cites if c["status"] == "verified_path_corrected"),
        "mismatched": [c for c in cites if c["status"] == "mismatch"],
        "unresolved": [c for c in cites if c["status"] == "unresolved"],
        "unsupported_numbers": free,
        "clean": all(is_verified(c) for c in cites) and not free,
    }
