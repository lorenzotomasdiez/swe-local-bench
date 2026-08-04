#!/usr/bin/env python3
"""Cross-runner metrics.

Aggregates every runner that has state on disk into one comparison, and
writes metrics.md alongside the terminal output.

    python3 metrics.py                 # every runner found
    python3 metrics.py claude-opus pi-deepseek-v4-flash

Runners are compared over the instances they all attempted. Anything only
some of them ran is dropped and reported, because a resolve rate computed
over different instance sets is not a comparison.
"""

from __future__ import annotations

import json
import sys

from config import HARNESS, INSTANCES

G, Y, R, B, D, X = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[2m", "\033[0m"
)

# A judge verdict is either "this would be an acceptable fix" or it is not.
# The four-way verdict exists to explain why, but the confusion matrix only
# needs the binary.
VALID = {"equivalent", "different-but-valid"}


def load(runner: str) -> dict:
    return {p.stem: json.loads(p.read_text())
            for p in sorted((HARNESS / "state" / runner).glob("*.json"))}


def classify(d: dict) -> str | None:
    """Place a result in the confusion matrix of tests against judge.

    The tests are the objective signal and the judge the subjective one.
    Neither is ground truth on its own: a fix can pass the tests while being
    behaviourally wrong (FP), and a genuinely good fix can fail tests that
    encode one specific redesign (FN). The disagreements are the interesting
    rows - they are where the benchmark is lying to you in one direction or
    the other.
    """
    resolved, verdict = d.get("resolved"), d.get("similarity")
    if resolved is None or verdict is None:
        return None
    valid = verdict in VALID
    return ("TP" if resolved and valid else
            "FP" if resolved else
            "FN" if valid else "TN")


def stats(runner: str, states: dict, ids: list[str]) -> dict:
    rows = [states[i] for i in ids if i in states]
    scored = [d for d in rows if d.get("resolved") is not None]
    solved = [d for d in scored if d["resolved"]]

    cells = [classify(d) for d in rows]
    costs = [d["agent_cost_usd"] for d in rows
             if isinstance(d.get("agent_cost_usd"), (int, float))]
    secs = [d["stages"]["agent"]["secs"] for d in rows
            if "secs" in d.get("stages", {}).get("agent", {})]
    bad = [d for d in rows if d.get("status") in ("failed", "timeout")]

    return {
        "runner": runner,
        "attempted": len(rows),
        "evaluated": len(scored),
        "resolved": len(solved),
        "rate": len(solved) / len(scored) if scored else None,
        **{k: cells.count(k) for k in ("TP", "FP", "FN", "TN")},
        "unjudged": cells.count(None),
        "failed": len(bad),
        "cost_total": sum(costs) if costs else None,
        "cost_avg": sum(costs) / len(costs) if costs else None,
        "secs_avg": sum(secs) / len(secs) if secs else None,
    }


def fmt(s: dict) -> list[str]:
    rate = f"{s['resolved']}/{s['evaluated']} ({100 * s['rate']:.0f}%)" \
        if s["rate"] is not None else "-"
    cost = f"${s['cost_avg']:.4f}" if s["cost_avg"] is not None else "-"
    tot = f"${s['cost_total']:.2f}" if s["cost_total"] is not None else "-"
    mins = f"{s['secs_avg'] / 60:.1f}m" if s["secs_avg"] is not None else "-"
    return [s["runner"], rate, str(s["TP"]), str(s["FP"]), str(s["FN"]),
            str(s["TN"]), mins, cost, tot]


BEGIN, END = "<!-- RESULTS:BEGIN -->", "<!-- RESULTS:END -->"


def inject_readme(block: str) -> bool:
    """Replace the README's results section in place.

    Deterministic on purpose. The numbers already exist as JSON, so having a
    model rewrite the README would add nondeterminism, spend and the risk of
    it quietly reinterpreting a solve rate or reflowing the prose around it.
    """
    readme = HARNESS.parent / "README.md"
    text = readme.read_text()
    if BEGIN not in text or END not in text:
        return False
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{BEGIN}\n{block.strip()}\n{END}{tail}")
    return True


def main() -> None:
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    to_readme = "--readme" in sys.argv[1:]
    found = sorted(p.name for p in (HARNESS / "state").iterdir()
                   if p.is_dir() and any(p.glob("*.json")))
    runners = [r for r in (want or found)]
    missing = [r for r in runners if r not in found]
    if missing:
        sys.exit(f"no state for: {', '.join(missing)}")
    if not runners:
        sys.exit("no runner state found - run `make pilot` first")

    loaded = {r: load(r) for r in runners}

    # Compare over what every runner actually attempted, not the union.
    common = set.intersection(*(set(v) for v in loaded.values()))
    dropped = sorted(set().union(*(set(v) for v in loaded.values())) - common)
    ids = sorted(common)
    if not ids:
        sys.exit("runners share no instances - nothing to compare")

    insts = {json.loads(l)["instance_id"]: json.loads(l)
             for l in INSTANCES.read_text().splitlines() if l.strip()}
    rows = [stats(r, loaded[r], ids) for r in runners]

    w = max(len(r) for r in runners) + 2
    hdr = (f"{'RUNNER':<{w}}{'SOLVE RATE':<14}{'TP':<5}{'FP':<5}{'FN':<5}"
           f"{'TN':<5}{'AVG TIME':<11}{'AVG COST':<11}TOTAL")
    print(f"\n{B}{len(ids)} instances, {len(runners)} runners{X}")
    if dropped:
        print(f"{D}dropped (not run by every runner): "
              f"{', '.join(i.split('-')[-1] for i in dropped)}{X}")
    print(f"\n{hdr}\n{D}{'─' * len(hdr)}{X}")
    for s, r in zip(rows, runners):
        c = fmt(s)
        print(f"{c[0]:<{w}}{c[1]:<14}{G}{c[2]:<5}{X}{R}{c[3]:<5}{X}"
              f"{Y}{c[4]:<5}{X}{D}{c[5]:<5}{X}{c[6]:<11}{c[7]:<11}{c[8]}")

    print(f"\n{D}TP passed tests + judged valid   "
          f"FP passed tests but judged wrong{X}")
    print(f"{D}FN judged valid but failed tests  "
          f"TN failed tests + judged wrong{X}")

    # Per-instance grid: which problems are hard for everyone, and which
    # separate the runners. A row that is uniformly ❌ is a hard instance;
    # a row that is uniformly ✅ carries no signal and could be dropped.
    print(f"\n{B}per instance{X}\n")
    head = f"{'PR':<8}" + "".join(r[:14].ljust(16) for r in runners)
    print(head + f"\n{D}{'─' * len(head)}{X}")
    for iid in sorted(ids, key=lambda i: insts.get(i, {}).get("pr", 0)):
        line = f"{insts.get(iid, {}).get('pr', '?'):<8}"
        for r in runners:
            d = loaded[r][iid]
            res = d.get("resolved")
            mark = "✅" if res else "❌" if res is False else "–"
            cell = classify(d) or ""
            line += f"{mark} {cell:<13}"
        print(line)

    plural = "runner" if len(runners) == 1 else "runners"
    md = ["# Cross-runner metrics\n",
          f"{len(ids)} instances, {len(runners)} {plural}.\n"]
    if dropped:
        md.append("Dropped, not attempted by every runner: "
                  + ", ".join(i.split("-")[-1] for i in dropped) + ".\n")
    md += ["| Runner | Solve rate | TP | FP | FN | TN | Avg time | "
           "Avg cost | Total |",
           "|---|---|---|---|---|---|---|---|---|"]
    md += ["| " + " | ".join(fmt(s)) + " |" for s in rows]
    md += ["",
           "TP passed tests and judged valid. "
           "FP passed tests but judged wrong. "
           "FN judged valid but failed tests. "
           "TN failed tests and judged wrong.\n",
           "| PR | " + " | ".join(runners) + " |",
           "|---" * (len(runners) + 1) + "|"]
    for iid in sorted(ids, key=lambda i: insts.get(i, {}).get("pr", 0)):
        cells = []
        for r in runners:
            d = loaded[r][iid]
            res = d.get("resolved")
            cells.append(("✅" if res else "❌" if res is False else "–")
                         + " " + (classify(d) or ""))
        md.append(f"| {insts.get(iid, {}).get('pr', '?')} | "
                  + " | ".join(cells) + " |")

    (HARNESS / "metrics.md").write_text("\n".join(md) + "\n")
    written = "metrics.md"

    # An interrupted sweep leaves runners with state but nothing scored.
    # Publishing that produces a README full of empty rows that reads like a
    # real result, which is worse than publishing nothing.
    if to_readme and not any(s["evaluated"] for s in rows):
        print(f"{R}nothing scored - README left untouched{X}")
        to_readme = False

    if to_readme:
        block = [
            f"Last sweep: **{len(ids)} instances**, {len(runners)} {plural}, "
            f"judged by Claude `opus`.\n",
            "| Runner | Solve rate | TP | FP | FN | TN | Avg time | "
            "Avg cost | Total |",
            "|---|---|---|---|---|---|---|---|---|",
            *["| " + " | ".join(fmt(s)) + " |" for s in rows],
            "",
            "`TP` passed and judged valid. `FP` passed but judged wrong. "
            "`FN` judged valid but failed. `TN` failed and judged wrong.",
            "",
            "Solve rate alone overstates a runner that scores `FP`, and "
            "understates one that scores `FN`.",
            "Per-instance detail is in `harness/metrics.md`.",
        ]
        if inject_readme("\n".join(block)):
            written += " and README.md"
        else:
            print(f"{R}README markers missing - skipped{X}")

    print(f"\n{D}wrote {written}{X}")


if __name__ == "__main__":
    main()
