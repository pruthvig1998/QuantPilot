#!/usr/bin/env python3
"""Build the QuantPilot Explorer: one self-contained page judges can click.

    .venv/bin/python scripts/build_explorer.py
    open docs/explorer/index.html

Reads the committed run folders (samples/live-run-* and samples/example-run),
trims each run's artifacts to what the page shows, re-checks every debate's
citations with the current grounding verifier, and writes
docs/explorer/index.html with the data embedded. No server, no keys, no
network: it opens from file:// or any static host (e.g. GitHub Pages).

The page's Ask box mirrors src/agent/ask.py's deterministic path (scope
gate, board / card / IV-rank / journal / posture answers) over the same
artifacts: every number it prints comes from the run it is pointed at.
"""
from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src import config  # noqa: E402
from src.agent.debate import _judge_text  # noqa: E402
from src.agent.grounding import grounding_report  # noqa: E402

RUNS = [
    ("2026-10-26", "samples/live-run-2026-10-26", "live",
     "Mon Oct 26, 2026 - 12:15 ET - through Meterless Nightshift (Nemotron Ultra)"),
    ("2026-10-23", "samples/live-run-2026-10-23", "live",
     "Fri Oct 23, 2026 - 10:00 ET - NVIDIA direct (Nemotron Ultra)"),
    ("2026-10-22", "samples/live-run-2026-10-22", "live",
     "Thu Oct 22, 2026 - 10:00 ET - NVIDIA direct (Nemotron Ultra)"),
    ("sample", "samples/example-run", "sample",
     "Offline sample run - synthetic fixture data, not a live market run"),
]


def trim_run(key, folder, kind, title):
    a = json.load(open(os.path.join(REPO, folder, "artifacts.json")))
    packets = a.get("packets") or {}
    debates = {}
    cited = verified = 0
    for sym, d in (a.get("debates") or {}).items():
        p = packets.get(sym) or {}
        rounds = []
        for r in d.get("rounds") or []:
            g = {who: grounding_report(t, p) for who, t in (
                ("bull", r.get("bull_case") or ""), ("bear", r.get("bear_case") or ""),
                ("judge", _judge_text(r.get("judge") or {})))}
            for rep in g.values():
                cited += rep["cited"]; verified += rep["verified"]
            rounds.append({
                "round": r.get("round"), "gap_note_in": r.get("gap_note_in"), "gap": r.get("gap"),
                "bull": r.get("bull_case"), "bear": r.get("bear_case"),
                "judge": {k: (r.get("judge") or {}).get(k) for k in
                          ("verdict", "conviction", "direction", "summary", "biggest_risk", "key_evidence", "loop_note")},
                "grounding": {who: {"cited": rep["cited"], "verified": rep["verified"],
                                    "failed": [f"[{c['path']} = {c['stated']}] {c['status']}"
                                               + (f" (packet: {c['actual']})" if c["status"] == "mismatch" else "")
                                               for c in rep["mismatched"] + rep["unresolved"]],
                                    "free": rep["unsupported_numbers"]} for who, rep in g.items()},
            })
        debates[sym] = {"verdict": d.get("verdict"), "conviction": d.get("conviction"),
                        "direction": d.get("direction"), "looped": d.get("looped"), "why": d.get("why"),
                        "rounds": rounds}
    pk = {}
    evaluated = rankable = 0
    for sym, p in packets.items():
        gr = p.get("guardrails") or {}
        evaluated += (gr.get("ranked_count") or 0) + (gr.get("rejected_count") or 0)
        rankable += gr.get("ranked_count") or 0
        ev = p.get("events") or {}
        pk[sym] = {"spot": p.get("spot"), "memory": p.get("memory"),
                   "iv_rank": (ev.get("iv") or {}).get("rank_pct"), "one_liner": ev.get("one_liner"),
                   "earnings": ev.get("earnings"), "selection": gr.get("selection"),
                   "ranked": gr.get("ranked_count"), "rejected": gr.get("rejected_count"),
                   "missing": (p.get("data_quality") or {}).get("missing")}
    cards = []
    for c in a.get("cards") or []:
        cards.append({k: c.get(k) for k in ("symbol", "kind", "verdict", "direction", "conviction", "contract",
                                             "levels", "sizing", "greeks_plain", "checks", "rejection",
                                             "downgraded", "downgrade_reason")}
                     | {"risk_line": (c.get("risk_review") or {}).get("line"),
                        "sector_line": (c.get("sector_context") or {}).get("line")})
    checks = [c for c in cards for c in (c.get("checks") or [])]
    xray = a.get("xray") or {}
    mc = a.get("model_calls") or []
    llm = (a.get("timings") or {}).get("llm") or {}
    return {
        "key": key, "kind": kind, "title": title, "date": a.get("date"), "as_of": a.get("as_of"),
        "board": (a.get("board") or {}).get("board") or [],
        "xray": {"read": xray.get("read"), "sectors": ((xray.get("sectors") or {}).get("sectors") or [])},
        "cards": cards, "debates": debates, "packets": pk,
        "journal": a.get("journal_stats"),
        "stats": {
            "names": len((a.get("board") or {}).get("board") or []),
            "debated": len(debates), "evaluated": evaluated, "rankable": rankable,
            "checks": len(checks), "failed": sum(1 for c in checks if c.get("passed") is False),
            "unknown": sum(1 for c in checks if c.get("passed") is None),
            "cited": cited, "verified": verified,
            "model_calls": len(mc) or llm.get("calls"), "mean_s": llm.get("mean_s"),
            "providers": sorted({m.get("provider") for m in mc}) if mc else [],
            "models": sorted({m.get("model") for m in mc}) if mc else ([llm.get("model")] if llm.get("model") else []),
            "zetaris_queries": len(a.get("data_calls") or []),
            "errors": len(a.get("errors") or []),
        },
    }


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantPilot Explorer</title>
<style>
:root{--bg:#0b0f17;--panel:#111826;--line:#243047;--text:#e6edf3;--muted:#8fa0b6;--blue:#7fb4ff;--green:#5fe3a1;--red:#ff7b6b;--amber:#f5c451}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,'Helvetica Neue',Arial,sans-serif}
header{padding:22px 28px 10px;border-bottom:1px solid var(--line)}h1{margin:0;font-size:28px}h1 small{font-size:15px;color:var(--muted);font-weight:400;margin-left:10px}
.sub{color:var(--muted);margin-top:4px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.tab{background:#151d2b;border:1px solid var(--line);color:var(--text);padding:8px 14px;border-radius:999px;cursor:pointer;font-size:14px}
.tab.on{background:#1d3a66;border-color:#3d7cff}.tag{font-size:11px;font-weight:700;letter-spacing:.06em;padding:2px 7px;border-radius:999px;margin-right:6px}
.tag.live{background:#123d2a;color:var(--green)}.tag.sample{background:#3d2f12;color:var(--amber)}
main{padding:18px 28px 60px;max-width:1500px}.runtitle{color:var(--muted);margin:4px 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}.tile b{display:block;font-size:26px}.tile span{color:var(--muted);font-size:13px}
nav.sec{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 16px}nav.sec button{background:none;border:1px solid var(--line);color:var(--muted);padding:6px 12px;border-radius:8px;cursor:pointer}
nav.sec button.on{color:var(--text);border-color:#3d7cff;background:#14243f}
section.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:16px}
h2{margin:0 0 12px;font-size:20px}h3{margin:14px 0 8px;font-size:16px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid #1c2638;text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600;cursor:pointer;white-space:nowrap}td.n{text-align:right;font-variant-numeric:tabular-nums}
.pill{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px}.pass{background:#123d2a;color:var(--green)}.fail{background:#45161a;color:var(--red)}.unk{background:#3d2f12;color:var(--amber)}
.v{font-weight:700}.v.TRADE{color:var(--green)}.v.WATCH{color:var(--amber)}.v.SKIP,.v.INSUFFICIENT_EVIDENCE{color:var(--muted)}
.card{border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}.muted{color:var(--muted)}
.filters button{background:none;border:1px solid var(--line);color:var(--muted);border-radius:7px;padding:3px 9px;margin-right:6px;cursor:pointer}.filters button.on{color:var(--text);border-color:#3d7cff}
.case{background:#0d1420;border:1px solid var(--line);border-radius:10px;padding:12px;margin:8px 0;white-space:pre-wrap}.who{font-weight:700;color:var(--blue);margin-bottom:4px}
.bad{background:rgba(255,90,90,.16)}.gap{border-left:4px solid var(--amber);padding:8px 12px;background:#1a1609;margin:8px 0}
select,input{background:#0d1420;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:14px}
.ask{display:flex;gap:8px}.ask input{flex:1}.ask button,.chips button{background:#1d3a66;border:1px solid #3d7cff;color:var(--text);border-radius:8px;padding:8px 14px;cursor:pointer}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.chips button{background:#14243f;font-size:13px;padding:5px 10px}
.answer{margin-top:12px;background:#0d1420;border:1px solid var(--line);border-radius:10px;padding:14px}.answer .meta{color:var(--muted);font-size:12px;margin-top:8px}
footer{color:var(--muted);padding:0 28px 30px;font-size:13px}code{background:#0d1420;padding:1px 5px;border-radius:5px}
</style></head><body>
<header><h1>QuantPilot Explorer<small>the options research agent that has to show its work</small></h1>
<div class="sub">Open Agent Hackathon 2026 - Track 02: The Agent That Can Explain Why. Every number on this page comes from a committed run in the repo; nothing is computed by the page except the Ask box's lookups.</div>
<div class="tabs" id="tabs"></div></header>
<main><div class="runtitle" id="runtitle"></div><div class="tiles" id="tiles"></div>
<nav class="sec" id="secnav"></nav><div id="view"></div></main>
<footer>Built from samples/live-run-* and samples/example-run by <code>scripts/build_explorer.py</code>. Data: Yahoo Finance through the Zetaris harness; model: NVIDIA Nemotron Ultra (through Meterless Nightshift on Oct 26). Educational only - not financial advice.</footer>
<script>
const RUNS = __DATA__;
const WATCH = __WATCHLIST__;
let run = RUNS[0], sec = "overview";
const $ = s => document.querySelector(s);
const esc = v => v == null ? "" : String(v).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const num = (v, d=2) => v == null || isNaN(v) ? "unknown" : (+v).toFixed(d);
const sgn = v => v == null || isNaN(v) ? "unknown" : (v >= 0 ? "+" : "") + (+v).toFixed(2);
const pill = p => p === true ? '<span class="pill pass">PASS</span>' : p === false ? '<span class="pill fail">FAIL</span>' : '<span class="pill unk">UNKNOWN</span>';
const SECS = [["overview","Overview"],["board","Liquidity Board"],["cards","Trade cards"],["debates","Debates + grounding"],["memory","Memory + events"],["ask","Ask QuantPilot"]];

function tabs(){ $("#tabs").innerHTML = RUNS.map((r,i)=>`<button class="tab ${r===run?'on':''}" onclick="pick(${i})"><span class="tag ${r.kind}">${r.kind==='live'?'LIVE':'SAMPLE'}</span>${r.kind==='live'?r.key:'Sample run'}</button>`).join(""); }
function pick(i){ run = RUNS[i]; render(); }
function go(s){ sec = s; render(); }
function tiles(){
  const s = run.stats;
  const t = [
    [s.names, "watchlist names ranked"],
    [s.evaluated, `option contracts evaluated (${s.rankable} passed the guardrail, ${s.evaluated - s.rankable} rejected)`],
    [`${s.verified} / ${s.cited}`, "debate citations verified against the packet"],
    [s.checks, `checks printed on cards (${s.failed} failed, ${s.unknown} unknown)`],
    [s.model_calls ?? "-", (s.providers.length ? `model calls via ${s.providers.join(", ")}` : "model calls") + (s.mean_s ? `, mean ${s.mean_s}s` : "")],
    [s.zetaris_queries || "-", s.zetaris_queries ? "Zetaris SQL queries" : "Zetaris trace (logged from Oct 23)"],
  ];
  $("#tiles").innerHTML = t.map(([b, sp]) => `<div class="tile"><b>${esc(b)}</b><span>${esc(sp)}</span></div>`).join("");
}
function overview(){
  const r = run.xray.read || {};
  const cards = run.cards.map(c => `<tr><td><b>${esc(c.symbol)}</b></td><td class="v ${esc(c.verdict)}">${esc(c.verdict)}</td><td class="n">${esc(c.conviction)}/10</td><td>${esc(c.kind)}</td><td class="muted">${esc((run.debates[c.symbol]||{}).rounds?.slice(-1)[0]?.judge?.biggest_risk || "")}</td></tr>`).join("");
  return `<section class="panel"><h2>What happened in this run</h2>
  <p>Market posture <b>${esc(r.posture || "unknown")}</b>: ${esc(r.bullish_share_pct)}% of the watchlist bullish, ${esc(r.bearish_share_pct)}% bearish, ${esc(r.pct_above_200dma)}% above the 200-day average. Leading sectors: ${esc((r.leading_sectors||[]).join(", ") || "none")}. Lagging: ${esc((r.lagging_sectors||[]).join(", ") || "none")}.</p>
  <h3>The verdicts and the judge's biggest risk</h3><table><tr><th>Name</th><th>Verdict</th><th>Conviction</th><th>Card</th><th>Biggest risk (judge)</th></tr>${cards}</table>
  <p class="muted">The pipeline: Zetaris data -> Liquidity Board + Market X-Ray -> evidence packet per top name -> bull / bear / judge debate on Nemotron -> every citation checked in code -> risk review -> trade card -> journal + Meterless H-Mem memory.</p></section>`;
}
let sortKey = "rank", sortDir = 1;
function sortBy(k){ sortDir = (sortKey === k) ? -sortDir : 1; sortKey = k; render(); }
function board(){
  const val = (r,k) => k in r ? r[k] : (r.components||{})[k] ?? (r.inputs||{})[k];
  const rows = [...run.board].sort((a,b) => { const x = val(a,sortKey), y = val(b,sortKey); return (x>y?1:x<y?-1:0)*sortDir; });
  const cols = [["rank","#"],["ticker","Ticker"],["price","Price"],["change_pct","Day %"],["score","Score"],["direction","Read"],["options_oi","OI bias"],["options_volume","Opt vol"],["momentum","Momentum"],["relative_volume","Relvol"]];
  return `<section class="panel"><h2>Liquidity Board <span class="muted" style="font-size:13px">click a column to sort</span></h2>
  <table><tr>${cols.map(([k,l])=>`<th onclick="sortBy('${k}')">${l}${sortKey===k?(sortDir>0?' ^':' v'):''}</th>`).join("")}</tr>
  ${rows.map(r=>`<tr><td class="n">${r.rank}</td><td><b>${esc(r.ticker)}</b></td><td class="n">${num(r.price)}</td><td class="n">${r.inputs?.change_pct==null?"unknown":num(r.inputs.change_pct)+"%"}</td><td class="n"><b>${num(r.score,1)}</b></td><td>${esc(r.direction)}</td><td class="n">${sgn(r.components?.options_oi)}</td><td class="n">${sgn(r.components?.options_volume)}</td><td class="n">${sgn(r.components?.momentum)}</td><td class="n">${sgn(r.components?.relative_volume)}</td></tr>`).join("")}</table>
  <p class="muted">Score = 100 x weighted blend of open-interest bias (0.30), options-volume bias (0.25), momentum (0.25) and signed relative volume (0.20); unknown components drop out and the rest are renormalized.</p></section>`;
}
let cardFilter = "all";
function cardsView(){
  const f = c => cardFilter === "all" || (cardFilter === "fail" && c.passed === false) || (cardFilter === "unknown" && c.passed == null);
  return `<section class="panel"><h2>Trade cards</h2><div class="filters">Show checks: ${["all","fail","unknown"].map(k=>`<button class="${cardFilter===k?'on':''}" onclick="cardFilter='${k}';render()">${k}</button>`).join("")}</div>
  ${run.cards.map(c=>{ const k=c.contract||{}, l=c.levels||{}, s=c.sizing||{};
   return `<div class="card"><h3>${esc(c.symbol)} - <span class="v ${esc(c.verdict)}">${esc(c.verdict)}</span> ${esc(c.direction)} - conviction ${esc(c.conviction)}/10 - ${esc(c.kind)}</h3>
   ${c.downgraded?`<p style="color:var(--red)">Downgraded: ${esc(c.downgrade_reason)}</p>`:""}
   <p>${c.kind==="trade"?"Contract":"Nearest candidate"}: <b>${esc(k.contract_symbol)}</b> ${esc(k.option_type)} strike ${num(k.strike)} premium ${num(k.premium)} - ${esc(k.days_to_expiry)} DTE</p>
   <p>Levels: spot ${num(l.spot)} | entry ${num(l.entry)} | stop ${num(l.stop)} | target ${num(l.target)} (${esc(l.target_source||"none in packet")}) - size ${esc(s.contracts)} contract(s), risk budget $${num(s.risk_budget_usd)}</p>
   <p>Greeks in plain English: ${esc((c.greeks_plain||{}).line)}</p>
   <p class="muted">${esc(c.sector_line)}<br>${esc(c.risk_line)}</p>
   ${c.rejection?`<p class="muted">No-trade reason: ${esc(c.rejection.reason)}</p>`:""}
   <table><tr><th>Check</th><th>Source</th><th>Status</th><th>Detail</th></tr>${(c.checks||[]).filter(f).map(x=>`<tr><td>${esc(x.check)}</td><td>${esc(x.source)}</td><td>${pill(x.passed)}</td><td>${esc(x.detail)}</td></tr>`).join("")}</table></div>`;}).join("")}</section>`;
}
let debSym = null;
function debatesView(){
  const syms = Object.keys(run.debates); if (!syms.includes(debSym)) debSym = syms[0];
  const d = run.debates[debSym] || {rounds: []};
  return `<section class="panel"><h2>Debates + grounding check</h2>
  <p>Name: <select onchange="debSym=this.value;render()">${syms.map(s=>`<option ${s===debSym?"selected":""}>${s}</option>`).join("")}</select>
  &nbsp; Final: <span class="v ${esc(d.verdict)}">${esc(d.verdict)}</span> ${esc(d.direction)} - conviction ${esc(d.conviction)}/10${d.looped?" - the Evaluator loop fired":""}</p>
  ${d.rounds.map(r=>`<h3>Round ${r.round}${r.round>1?" - loop-back":""}</h3>
   ${r.gap_note_in?`<div class="gap"><b>Evaluator feedback carried into this round:</b> ${esc(r.gap_note_in)}</div>`:""}
   <div class="case"><div class="who">BULL</div>${esc(r.bull)}</div><div class="case"><div class="who">BEAR</div>${esc(r.bear)}</div>
   <div class="case"><div class="who">JUDGE</div><span class="v ${esc(r.judge.verdict)}">${esc(r.judge.verdict)}</span> conviction ${esc(r.judge.conviction)}/10, direction ${esc(r.judge.direction)}\n${esc(r.judge.summary)}\nKey evidence: ${esc((r.judge.key_evidence||[]).join(" ; "))}\nBiggest risk: ${esc(r.judge.biggest_risk)}${r.judge.loop_note?"\nCode override: "+esc(r.judge.loop_note):""}</div>
   ${r.gap?`<div class="gap"><b>Evaluator gap (why the loop fired):</b> ${esc(r.gap)}</div>`:""}
   <table><tr><th>Voice</th><th>Citations</th><th>Verified</th><th>Failed citations</th><th>Numbers not in packet</th></tr>
   ${["bull","bear","judge"].map(w=>{const g=r.grounding[w]; return `<tr class="${g.failed.length?"bad":""}"><td>${w.toUpperCase()}</td><td class="n">${g.cited}</td><td class="n">${g.verified}</td><td>${esc(g.failed.join("; ")||"none")}</td><td>${esc(g.free.join(", ")||"none")}</td></tr>`;}).join("")}</table>`).join("")}
  <p class="muted">Every [path = value] citation is resolved against the evidence packet by src/agent/grounding.py. A TRADE whose key evidence does not verify is downgraded to WATCH in code.</p></section>`;
}
function memoryView(){
  return `<section class="panel"><h2>Memory (Meterless H-Mem) and event risk</h2><table><tr><th>Name</th><th>Past calls recalled into the packet</th><th>Event / IV read</th><th>Expiry chosen</th><th>Contracts</th><th>Missing data (named)</th></tr>
  ${Object.entries(run.packets).map(([s,p])=>{const m=p.memory; const calls = m==null?"not recorded in this run":(m.calls==null?"unknown ("+esc(m.error)+")":(m.calls.length?m.calls.map(c=>`${esc(c.date)}: ${esc(c.judge_verdict)} ${esc(c.conviction)}/10 at ${num(c.entry_spot)}${c.outcome?` -> ${num(c.outcome.move_pct)}% later`:""}`).join("<br>"):"none yet")); const sel=p.selection||{};
   return `<tr><td><b>${esc(s)}</b></td><td>${calls}</td><td>${esc(p.one_liner)}</td><td>${sel.dte!=null?esc(sel.dte)+" DTE ("+esc(sel.basis)+")":"front chain"}</td><td class="n">${esc(p.ranked)} pass / ${esc(p.rejected)} rejected</td><td>${esc((p.missing||[]).join(", ")||"none")}</td></tr>`;}).join("")}</table></section>`;
}
/* ---- Ask: deterministic answers over this run (mirrors src/agent/ask.py) ---- */
const ADVICE = ["should i","should we","my money","my portfolio","my savings","invest my","retirement","tax advice","financial advice","buy now","sell now","i buy","i sell"];
const NOT_T = new Set(["AI","AM","ATM","ATR","BEST","CALL","CEO","CPI","DMA","DTE","EMA","ET","ETF","FAIL","FOMC","GDP","HOW","ITM","IV","LLM","NFP","OI","OTM","PM","POP","PUT","RISK","RSI","SMA","THE","TOP","USA","USD","VWAP","WHAT","WHEN","WHY"]);
function syms(){ return [...new Set([...run.board.map(r=>r.ticker), ...run.cards.map(c=>c.symbol), ...Object.keys(run.packets)])]; }
function answer(q){
  const lower = q.toLowerCase();
  if (ADVICE.some(p => lower.includes(p))) return ["That is personal financial advice, which is out of scope. QuantPilot explains its own run artifacts - board rankings, trade cards, debate verdicts, journal stats - and does not recommend trades for anyone's money.", "refused (out of scope)"];
  const toks = q.match(/\b[A-Za-z]{1,5}\b/g) || []; const known = new Set(syms());
  let sym = null, absent = null;
  for (const t of toks) if (known.has(t.toUpperCase())) { sym = t.toUpperCase(); break; }
  if (!sym) { for (const t of toks) if (WATCH.includes(t.toUpperCase())) { absent = t.toUpperCase(); break; }
    if (!absent) for (const t of (q.match(/\b[A-Z]{2,5}\b/g)||[])) if (!NOT_T.has(t)) { absent = t; break; } }
  if (absent) return [WATCH.includes(absent) ? `Unknown in the artifacts: ${absent} is on the watchlist but has no board row, card, packet or debate in this run.` : `${absent} is outside QuantPilot's watchlist and this run's artifacts, so there is no evidence to answer from.`, "unknown in the artifacts"];
  const card = run.cards.find(c => c.symbol === sym), row = run.board.find(r => r.ticker === sym), pk = run.packets[sym], deb = run.debates[sym];
  if (/hit rate|win rate|track record|performance|journal/.test(lower)) { const s = run.journal || {}; return [s.hit_rate == null ? `The journal holds ${s.entries||0} entries and none are scored as trades yet, so the hit rate is unknown - not zero.` : `The journal holds ${s.entries} entries; ${s.scored_entries} scored: ${s.hits} hits and ${s.losses} losses, a hit rate of ${(s.hit_rate*100).toFixed(1)}%.`, "source: journal stats"]; }
  if (sym && /iv rank|implied vol/.test(lower)) return pk ? [pk.iv_rank == null ? `Unknown in the artifacts: ${sym}'s IV rank is not available - no IV range exists yet. Packet one-liner: ${pk.one_liner}` : `${sym}'s IV rank is ${pk.iv_rank}. ${pk.one_liner}`, "source: packet"] : [`Unknown in the artifacts: no packet for ${sym} in this run.`, "unknown"];
  if (sym && /fail|invalidate|go wrong|risk|why not|stand aside/.test(lower)) { if (!card) return [`Unknown in the artifacts: no card for ${sym}.`, "unknown"];
    const failed = (card.checks||[]).filter(c=>c.passed===false).slice(0,3).map(c=>`${c.check} - ${c.detail}`); const unk = (card.checks||[]).filter(c=>c.passed==null).map(c=>c.check);
    const risk = deb?.rounds?.slice(-1)[0]?.judge?.biggest_risk;
    return [`The ${sym} card is ${card.kind === "trade" ? "a live trade idea" : "a no-trade (verdict " + card.verdict + ")"}.${risk ? " Judge's biggest risk: " + risk : ""}${failed.length ? " Failed checks: " + failed.join("; ") + "." : ""}${unk.length ? " Checks the packet could not score: " + unk.join(", ") + "." : ""}`, "source: card + debate"]; }
  const boardAnswer = () => { const top = [...run.board].sort((a,b)=>a.rank-b.rank)[0]; const c = row.components||{}, i = row.inputs||{};
    return [`${top.ticker !== sym && /first|top|lead/.test(lower) ? `${sym} is not ranked first - it is #${row.rank}; ${top.ticker} leads at ${num(top.score)}. ` : ""}${sym} ranks #${row.rank} of ${run.board.length} with a score of ${num(row.score)} (${row.direction}). Components: options OI ${sgn(c.options_oi)} (weight 0.30), options volume ${sgn(c.options_volume)} (0.25), momentum ${sgn(c.momentum)} (0.25), relative volume ${sgn(c.relative_volume)} (0.20). Inputs: call OI ${i.call_oi} vs put OI ${i.put_oi}, call volume ${i.call_volume} vs put volume ${i.put_volume}, day change ${i.change_pct == null ? "unknown" : i.change_pct + "%"}, 5-day return ${i.ret_5d_pct}%.${card ? "" : ` ${sym} was not in the top names debated this run, so it has no card.`}`, "source: board"]; };
  if (sym && row && /rank|first|top|lead|score|why/.test(lower) && !/why.*(watch|skip|trade)/.test(lower)) return boardAnswer();
  if (sym && deb) return [deb.why, "source: debate"];
  if (sym && row) return boardAnswer();
  if (/posture|breadth|sector|market/.test(lower)) { const r = run.xray.read || {}; return [`Market posture is ${r.posture}: ${r.bullish_share_pct}% bullish, ${r.bearish_share_pct}% bearish, ${r.pct_above_200dma}% of the watchlist above the 200DMA. Leading sectors: ${(r.leading_sectors||[]).join(", ")}. Lagging: ${(r.lagging_sectors||[]).join(", ")}.`, "source: X-Ray"]; }
  return [`This run holds a ${run.board.length}-name board, ${run.cards.length} cards and ${Object.keys(run.debates).length} debates. Ask about a name's ranking, why a card stood aside, an IV rank, the market posture, or the journal.`, "help"];
}
function askView(){
  const ex = run.cards.length ? [`Why is ${[...run.board].sort((a,b)=>a.rank-b.rank)[0]?.ticker} ranked first?`, `Why did the ${run.cards[0].symbol} judge stand aside?`, `What is ${run.cards[run.cards.length-1].symbol}'s IV rank?`, "What is the market posture?", "Should I buy calls with my savings?"] : [];
  return `<section class="panel"><h2>Ask QuantPilot about this run</h2><div class="ask"><input id="q" placeholder="e.g. Why is TSLA ranked first?" onkeydown="if(event.key==='Enter')ask()"><button onclick="ask()">Ask</button></div>
  <div class="chips">${ex.map(e=>`<button onclick="$('#q').value=this.textContent;ask()">${esc(e)}</button>`).join("")}</div><div id="ans"></div>
  <p class="muted">Answers are looked up from this run's artifacts (the deterministic path of src/agent/ask.py): scope gate first, unknowns stated as unknown, personal advice refused.</p></section>`;
}
function ask(){ const q = $("#q").value.trim(); if (!q) return; const [a, m] = answer(q); $("#ans").innerHTML = `<div class="answer"><b>Q:</b> ${esc(q)}<br><br>${esc(a)}<div class="meta">${esc(m)} - run ${esc(run.kind === "live" ? run.key : "sample")}</div></div>`; }
function render(){
  tabs(); $("#runtitle").innerHTML = `<span class="tag ${run.kind}">${run.kind==="live"?"LIVE":"SAMPLE"}</span>${esc(run.title)}`;
  tiles(); $("#secnav").innerHTML = SECS.map(([k,l])=>`<button class="${sec===k?'on':''}" onclick="go('${k}')">${l}</button>`).join("");
  $("#view").innerHTML = ({overview, board, cards: cardsView, debates: debatesView, memory: memoryView, ask: askView})[sec]();
}
render();
</script></body></html>
"""


def main() -> int:
    data = [trim_run(*r) for r in RUNS]
    out_dir = os.path.join(REPO, "docs", "explorer")
    os.makedirs(out_dir, exist_ok=True)
    blob = json.dumps(data, separators=(",", ":"), default=str).replace("</", "<\\/")
    html = PAGE.replace("__DATA__", blob).replace("__WATCHLIST__", json.dumps(list(config.WATCHLIST)))
    path = os.path.join(out_dir, "index.html")
    with open(path, "w") as fh:
        fh.write(html)
    for r in data:
        s = r["stats"]
        print(f"{r['key']}: {s['evaluated']} contracts evaluated, {s['verified']}/{s['cited']} citations verified")
    print(f"wrote {path} ({os.path.getsize(path) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
