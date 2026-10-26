"""QuantPilot Explorer build: the page's headline numbers are counted
from the committed run artifacts, never computed or estimated."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _builder():
    spec = importlib.util.spec_from_file_location("build_explorer", REPO / "scripts" / "build_explorer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sample_run_stats_match_the_artifacts():
    """Reference counted by hand from samples/example-run/artifacts.json:
    contracts evaluated = sum of ranked_count + rejected_count over the
    packets; card checks = all checks on all cards."""
    b = _builder()
    run = b.trim_run("sample", "samples/example-run", "sample", "t")
    a = json.loads((REPO / "samples/example-run/artifacts.json").read_text())
    evaluated = sum(p["guardrails"]["ranked_count"] + p["guardrails"]["rejected_count"]
                    for p in a["packets"].values())
    checks = [c for card in a["cards"] for c in card["checks"]]
    s = run["stats"]
    assert s["evaluated"] == evaluated == 36
    assert s["checks"] == len(checks)
    assert s["failed"] == sum(1 for c in checks if c["passed"] is False)
    assert (s["verified"], s["cited"]) == (14, 15)
    assert s["names"] == len(a["board"]["board"])


def test_page_is_self_contained_and_honest():
    b = _builder()
    assert b.main() == 0
    page = (REPO / "docs/explorer/index.html").read_text()
    assert "<script src" not in page and "https://" not in page.split("<script>")[1]
    assert "—" not in page
    assert "not a live market run" in page          # sample is labeled as such
    assert "personal financial advice" in page        # Ask box scope gate present


def test_judge_tour_has_five_steps_with_deep_links():
    b = _builder()
    assert b.main() == 0
    page = (REPO / "docs/explorer/index.html").read_text()
    assert "Judges: start here" in page
    assert page.count('run:"2026-10-') == 5          # five tour steps, all on live runs
    assert 'addEventListener("hashchange"' in page    # #tour=N links work in an open tab
    for target in ('"#tiles"', '"tr.bad"', '".card"', '"#ans"', '"#sponsorlog"'):
        assert target in page


def test_every_red_team_attack_is_caught():
    """Each attack runs against the real code; none may get through."""
    attacks = _builder().red_team()
    assert len(attacks) == 8
    for a in attacks:
        assert a["result"] in ("WATCH", "rejected", "treated as no reply", "refused"), a
