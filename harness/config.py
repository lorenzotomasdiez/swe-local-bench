"""Shared paths and tunables for the mini-SWE-bench harness."""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
REPO = ROOT / "pytest"
WORKTREES = ROOT / "pytest-worktrees"
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"

INSTANCES = HARNESS / "instances.jsonl"

# Pinned explicitly so results never depend on ~/.claude/settings.json.
# AGENT_MODEL is what's being benchmarked; JUDGE_MODEL grades it and should
# stay fixed across models, otherwise you're changing two variables at once.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "opus")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "opus")

# State is scoped per agent model so runs never clobber each other.
STATE = HARNESS / "state" / AGENT_MODEL
RUNS = HARNESS / "runs" / AGENT_MODEL

# Stage-level concurrency. API-bound stages get fewer slots than CPU-bound ones.
LIMITS = {
    "setup": int(os.environ.get("W_SETUP", 6)),
    "probe": int(os.environ.get("W_PROBE", 6)),
    "agent": int(os.environ.get("W_AGENT", 4)),
    "capture": int(os.environ.get("W_CAPTURE", 4)),
    "test": int(os.environ.get("W_TEST", 6)),
    "judge": int(os.environ.get("W_JUDGE", 4)),
}

TIMEOUTS = {
    "setup": 300,
    "probe": 900,
    "agent": int(os.environ.get("T_AGENT", 1800)),
    "capture": 300,
    "test": 900,
    "judge": 600,
}

STAGES = ["setup", "probe", "agent", "capture", "test", "judge"]

# setuptools_scm generates this at build time; we synthesize it per worktree.
VERSION_STUB = (
    'version = "8.0.0.dev0"\n'
    'version_tuple = (8, 0, 0, "dev0")\n'
    "__version__ = version\n"
)
