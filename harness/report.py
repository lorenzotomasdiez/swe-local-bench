#!/usr/bin/env python3
"""Turn run state into results.json + results.md."""

from __future__ import annotations

import json

from config import HARNESS, INSTANCES, RUNNER, STATE

insts = {json.loads(l)["instance_id"]: json.loads(l)
         for l in INSTANCES.read_text().splitlines() if l.strip()}
rows = []
for p in sorted(STATE.glob("*.json")):
    d = json.loads(p.read_text())
    i = insts.get(d["id"], {})
    t = d["stages"].get("test", {})
    rows.append({
        "instance_id": d["id"],
        "pr": i.get("pr"),
        "issues": i.get("issues"),
        "base_commit": i.get("base_commit"),
        "fix_commit": i.get("fix_commit"),
        "status": d.get("status"),
        "resolved": d.get("resolved"),
        "similarity": d.get("similarity"),
        "f2p_passed": t.get("f2p_passed"),
        "f2p_total": t.get("f2p_total"),
        "p2p_broken": t.get("p2p_broken"),
        "agent_secs": d["stages"].get("agent", {}).get("secs"),
        "agent_cost_usd": d.get("agent_cost_usd"),
        "note": d.get("note", ""),
    })

(HARNESS / f"results-{RUNNER}.json").write_text(json.dumps(rows, indent=2))

scored = [r for r in rows if r["resolved"] is not None]
solved = [r for r in scored if r["resolved"]]
pct = f"{100 * len(solved) / len(scored):.1f}%" if scored else "n/a"

costs = [r["agent_cost_usd"] for r in rows
         if isinstance(r["agent_cost_usd"], (int, float))]
times = [r["agent_secs"] for r in rows if r["agent_secs"]]

md = [f"# Results - runner: {RUNNER}\n",
      f"**Resolve rate: {len(solved)}/{len(scored)} ({pct})** "
      f"of instances with a valid failing baseline.\n",
      f"Total attempted: {len(rows)}. "
      f"Excluded for no failing baseline: "
      f"{sum(1 for r in rows if 'NO_DISCRIMINATOR' in r['note'])}.\n"]
if costs:
    md.append(f"Agent spend: ${sum(costs):.4f} total, "
              f"${sum(costs) / len(costs):.4f} average per issue.\n")
if times:
    md.append(f"Agent time: {sum(times) / len(times) / 60:.1f} min "
              f"average per issue.\n")
md += ["| PR | Issues | Resolved | F2P | P2P broken | Judge | Time | Cost |",
       "|---|---|---|---|---|---|---|---|"]
for r in sorted(rows, key=lambda r: (r["resolved"] is not True, r["pr"] or 0)):
    res = "✅" if r["resolved"] else "❌" if r["resolved"] is False else "–"
    f2p = (f"{r['f2p_passed']}/{r['f2p_total']}"
           if r["f2p_total"] is not None else "–")
    secs = f"{r['agent_secs']:.0f}s" if r["agent_secs"] else "–"
    cost = (f"${r['agent_cost_usd']:.4f}"
            if isinstance(r["agent_cost_usd"], (int, float)) else "–")
    md.append(f"| {r['pr']} | {', '.join(map(str, r['issues'] or []))} | {res} | "
              f"{f2p} | {r['p2p_broken'] if r['p2p_broken'] is not None else '–'} | "
              f"{r['similarity'] or '–'} | {secs} | {cost} |")

(HARNESS / f"results-{RUNNER}.md").write_text("\n".join(md) + "\n")
print(f"resolved {len(solved)}/{len(scored)} ({pct})")
print(f"wrote results-{RUNNER}.md and results-{RUNNER}.json")
