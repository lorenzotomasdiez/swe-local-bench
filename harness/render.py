"""Live terminal status for the harness.

Imported by orchestrate.py for the in-run display, and executed directly by
`make status` to inspect a run from another terminal.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from config import RUNNER, STAGES, STATE

G, Y, R, B, D, X = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[2m", "\033[0m"
)
GLYPH = {"ok": f"{G}●{X}", "running": f"{Y}◐{X}", "failed": f"{R}✗{X}",
         "timeout": f"{R}✗{X}", "invalid": f"{Y}⊘{X}", None: f"{D}·{X}"}


def glyph(status) -> str:
    """Any status the table cannot name would otherwise crash the display."""
    return GLYPH.get(status, f"{R}?{X}")


def read(ids):
    out = []
    for iid in ids:
        p = STATE / f"{iid}.json"
        out.append(json.loads(p.read_text()) if p.exists()
                   else {"id": iid, "stage": None, "status": "pending",
                         "stages": {}, "started": None})
    return out


def _running(d) -> str:
    """The stages actually in flight, not the last one to have started.

    `state["stage"]` is whatever called begin() most recently, and the
    validation and agent branches run concurrently - so an instance whose
    agent has been working for 15 minutes would report `gold`, the short
    stage that happened to start second.
    """
    return "+".join(s for s in STAGES
                    if d.get("stages", {}).get(s, {}).get("status") == "running")


def _elapsed(d):
    if not d.get("started"):
        return "-"
    end = d["started"]
    for s in d["stages"].values():
        end = max(end, s.get("t0", 0) + s.get("secs", 0))
    secs = int((time.time() if d.get("status") == "running" else end) - d["started"])
    return f"{secs // 60}m{secs % 60:02d}s"


def table(ids) -> str:
    rows = read(ids)
    pipe_hdr = "".join(s[:4].ljust(5) for s in STAGES)
    L = [f"{B}runner: {RUNNER}{X}",
         f"{'INSTANCE':<14}{pipe_hdr}  {'ELAPSED':<9}{'COST':<9}{'F2P':<7}"
         f"{'RESOLVED':<10}{'JUDGE':<20}STATUS",
         D + "─" * (88 + 5 * len(STAGES)) + X]
    for d in rows:
        pipe = "".join(
            # ljust must not count the colour escapes, hence the correction.
            glyph(g).ljust(5 + len(glyph(g)) - 1)
            for g in (d["stages"].get(s, {}).get("status") for s in STAGES)
        )
        t = d["stages"].get("test", {})
        f2p = (f"{t['f2p_passed']}/{t['f2p_total']}"
               if "f2p_total" in t else str(len(d.get("f2p", [])) or "-"))
        res = d.get("resolved")
        resolved = (f"{G}YES{X}" if res is True
                    else f"{R}no{X}" if res is False else f"{D}-{X}")
        sim = d.get("similarity") or "-"
        status = d.get("status", "")
        col = (G if status == "ok" else R if status in ("failed", "timeout")
               else Y if status == "running" else D)  # discarded reads as dim
        cur = _running(d) or d.get("stage") or ""
        note = f"  {D}{d.get('note', '')[:38]}{X}" if d.get("note") else ""
        c = d.get("agent_cost_usd")
        cost = f"${c:.4f}" if isinstance(c, (int, float)) else "-"
        L.append(f"{d['id'].split('-')[-1]:<14}{pipe}  {_elapsed(d):<9}"
                 f"{cost:<9}{f2p:<7}{resolved:<19}{sim:<20}{col}{status}{X}"
                 f"{D}/{cur}{X}{note}")
    return "\n".join(L)


def summary(ids) -> str:
    rows = read(ids)
    done = [d for d in rows if d.get("stage") == "done"]
    scored = [d for d in done if d.get("resolved") is not None]
    solved = [d for d in scored if d["resolved"]]
    nodisc = [d for d in done if "NO_DISCRIMINATOR" in (d.get("note") or "")]
    gold = [d for d in done if d.get("status") == "discarded"]
    bad = [d for d in done if d.get("status") in ("failed", "timeout")]
    pct = f"{100 * len(solved) / len(scored):.0f}%" if scored else "n/a"

    costs = [d["agent_cost_usd"] for d in rows
             if isinstance(d.get("agent_cost_usd"), (int, float))]
    secs = [d["stages"]["agent"]["secs"] for d in rows
            if "secs" in d.get("stages", {}).get("agent", {})]
    spend = (f"   |  spend ${sum(costs):.2f} (avg ${sum(costs)/len(costs):.4f})"
             if costs else "")
    dur = f"   |  avg agent {sum(secs)/len(secs)/60:.1f}m" if secs else ""

    return (f"\n{B}resolved {len(solved)}/{len(scored)} scored ({pct}){X}"
            f"   |  no-discriminator: {len(nodisc)}"
            f"   |  gold-discarded: {len(gold)}"
            f"   |  failed/timeout: {len(bad)}"
            f"   |  complete: {len(done)}/{len(rows)}"
            f"{spend}{dur}")


HEARTBEAT = 60  # seconds between progress lines in plain mode


async def live(ids, tasks, plain=False):
    """Redraw the table until every task finishes."""
    seen, tick = {}, 0
    try:
        while True:
            if plain:
                # Plain mode goes to a file (sweep.sh redirects it), and a
                # redirected stdout is block-buffered: without an explicit
                # flush nothing reaches the log until 8KB have accumulated.
                # A 20-minute agent stage then looks exactly like a hang.
                # Print on state change, and a heartbeat in between so a slow
                # stage still proves it is alive.
                tick += 1
                for d in read(ids):
                    now = f"{_running(d) or d.get('stage')} {d.get('status')}"
                    if seen.get(d["id"]) != now:
                        seen[d["id"]] = now
                        print(f"[{d['id']}] {now} ({_elapsed(d)})", flush=True)
                if tick % HEARTBEAT == 0:
                    print(summary(ids).strip(), flush=True)
            else:
                sys.stdout.write("\033[H\033[J" + table(ids) + summary(ids) + "\n")
                sys.stdout.flush()
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


def final(ids):
    sys.stdout.write("\033[H\033[J" + table(ids) + summary(ids) + "\n\n")
    sys.stdout.flush()


if __name__ == "__main__":
    ids = sorted(p.stem for p in STATE.glob("*.json"))
    if not ids:
        sys.exit("no state yet - run `make pilot` first")
    print(table(ids) + summary(ids))
