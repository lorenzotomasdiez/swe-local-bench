#!/usr/bin/env python3
"""Side-by-side comparison of two agent models on the same instances.

Usage: python3 compare.py opus sonnet
"""

from __future__ import annotations

import json
import pathlib
import sys

from config import HARNESS, INSTANCES

A, B = (sys.argv[1:3] + ["opus", "sonnet"])[:2]
insts = {json.loads(l)["instance_id"]: json.loads(l)
         for l in INSTANCES.read_text().splitlines() if l.strip()}


def load(model):
    d = {}
    for p in sorted((HARNESS / "state" / model).glob("*.json")):
        s = json.loads(p.read_text())
        d[s["id"]] = s
    return d


a, b = load(A), load(B)
shared = sorted(set(a) & set(b))
if not shared:
    sys.exit(f"no overlapping instances between '{A}' and '{B}' "
             f"({len(a)} vs {len(b)} found)")

G, R, D, X = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
mark = {True: f"{G}✅{X}", False: f"{R}❌{X}", None: f"{D}–{X}"}
rows, agree, only_a, only_b = [], 0, 0, 0

print(f"{'PR':<8}{A:<12}{B:<12}DELTA")
print(D + "─" * 46 + X)
for iid in shared:
    ra, rb = a[iid].get("resolved"), b[iid].get("resolved")
    if ra is None or rb is None:
        delta = f"{D}not scored{X}"
    elif ra == rb:
        agree += 1
        delta = ""
    elif ra:
        only_a += 1
        delta = f"{G}only {A}{X}"
    else:
        only_b += 1
        delta = f"{G}only {B}{X}"
    print(f"{insts.get(iid, {}).get('pr', '?'):<8}{mark[ra]:<20}{mark[rb]:<20}{delta}")


def rate(d):
    s = [v for v in d.values() if v.get("resolved") is not None]
    w = [v for v in s if v["resolved"]]
    return f"{len(w)}/{len(s)}" + (f" ({100*len(w)/len(s):.0f}%)" if s else "")


print(f"\n{A}: {rate({k: a[k] for k in shared})}"
      f"   |  {B}: {rate({k: b[k] for k in shared})}")
print(f"agree on {agree}/{len(shared)}   |  "
      f"{A}-only wins: {only_a}   |  {B}-only wins: {only_b}")
