"""Live terminal status for the harness.

Imported by orchestrate.py for the in-run display, and executed directly by
`make status` to inspect a run from another terminal.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from config import STAGES, STATE

G, Y, R, B, D, X = (
    "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[2m", "\033[0m"
)
GLYPH = {"ok": f"{G}●{X}", "running": f"{Y}◐{X}", "failed": f"{R}✗{X}",
         "timeout": f"{R}✗{X}", None: f"{D}·{X}"}


def read(ids):
    out = []
    for iid in ids:
        p = STATE / f"{iid}.json"
        out.append(json.loads(p.read_text()) if p.exists()
                   else {"id": iid, "stage": None, "status": "pending",
                         "stages": {}, "started": None})
    return out


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
    L = [f"{'INSTANCE':<14}{pipe_hdr}  {'ELAPSED':<9}{'F2P':<7}"
         f"{'RESOLVED':<10}{'JUDGE':<20}STATUS",
         D + "─" * 108 + X]
    for d in rows:
        pipe = "".join(
            GLYPH.get(d["stages"].get(s, {}).get("status")).ljust(
                5 + len(GLYPH.get(d["stages"].get(s, {}).get("status"))) - 1)
            for s in STAGES
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
               else Y if status == "running" else D)
        cur = d.get("stage") or ""
        note = f"  {D}{d.get('note', '')[:38]}{X}" if d.get("note") else ""
        L.append(f"{d['id'].split('-')[-1]:<14}{pipe}  {_elapsed(d):<9}"
                 f"{f2p:<7}{resolved:<19}{sim:<20}{col}{status}{X}"
                 f"{D}/{cur}{X}{note}")
    return "\n".join(L)


def summary(ids) -> str:
    rows = read(ids)
    done = [d for d in rows if d.get("stage") == "done"]
    scored = [d for d in done if d.get("resolved") is not None]
    solved = [d for d in scored if d["resolved"]]
    nodisc = [d for d in done if "NO_DISCRIMINATOR" in (d.get("note") or "")]
    bad = [d for d in done if d.get("status") in ("failed", "timeout")]
    pct = f"{100 * len(solved) / len(scored):.0f}%" if scored else "n/a"
    return (f"\n{B}resolved {len(solved)}/{len(scored)} scored ({pct}){X}"
            f"   |  no-discriminator: {len(nodisc)}"
            f"   |  failed/timeout: {len(bad)}"
            f"   |  complete: {len(done)}/{len(rows)}")


async def live(ids, tasks, plain=False):
    """Redraw the table until every task finishes."""
    try:
        while True:
            if plain:
                for d in read(ids):
                    print(f"[{d['id']}] {d.get('stage')} {d.get('status')}")
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
