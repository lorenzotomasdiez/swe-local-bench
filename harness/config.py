"""Shared paths and tunables for the mini-SWE-bench harness."""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = ROOT / "harness"
REPO = ROOT / "pytest"
WORKTREES = ROOT / "pytest-worktrees"

# The agent's checkout and the evaluation checkouts live under separate roots.
# The evaluation copies hold the tests and, for `gold`, the maintainers' actual
# fix; keeping them out of the agent's sibling directories means a stray `ls ..`
# cannot hand an agent the answer.
AGENT_TREES = WORKTREES / "agent"
EVAL_TREES = WORKTREES / "eval"
VENV = ROOT / ".venv"
PYTHON = VENV / "bin" / "python"

INSTANCES = HARNESS / "instances.jsonl"

# ─────────────────────────────── runners ──────────────────────────────
#
# A runner is the thing under test: a CLI harness plus the model driving it.
# Both halves matter - the same model scores differently under a different
# harness - so the runner name, not the model name, is the unit of comparison.
#
# Every field is pinned here rather than inherited from ~/.claude/settings.json
# or ~/.pi/agent/settings.json. A personal setting change must never silently
# move a benchmark number.

RUNNERS = {
    "claude-opus": {"cli": "claude", "model": "opus"},
    "claude-sonnet": {"cli": "claude", "model": "sonnet"},
    "claude-haiku": {"cli": "claude", "model": "haiku"},
    "pi-deepseek-v4-flash": {
        "cli": "pi",
        "provider": "openrouter",
        "model": "deepseek/deepseek-v4-flash",
        # pi reads defaultThinkingLevel from user settings; pin it.
        "thinking": "high",
    },
}

RUNNER = os.environ.get("RUNNER", "claude-opus")
if RUNNER not in RUNNERS:
    raise SystemExit(
        f"unknown RUNNER {RUNNER!r}. known: {', '.join(sorted(RUNNERS))}"
    )
AGENT = RUNNERS[RUNNER]

# The judge grades every runner and must stay fixed, otherwise a comparison
# moves two variables at once. It is always Claude: a runner being benchmarked
# should never also be scoring itself.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "opus")

# State is scoped per runner so runs never clobber each other.
STATE = HARNESS / "state" / RUNNER
RUNS = HARNESS / "runs" / RUNNER

# Stage-level concurrency. API-bound stages get fewer slots than CPU-bound ones.
LIMITS = {
    "setup": int(os.environ.get("W_SETUP", 6)),
    "probe": int(os.environ.get("W_PROBE", 6)),
    "gold": int(os.environ.get("W_GOLD", 6)),
    "agent": int(os.environ.get("W_AGENT", 4)),
    "capture": int(os.environ.get("W_CAPTURE", 4)),
    "test": int(os.environ.get("W_TEST", 6)),
    "judge": int(os.environ.get("W_JUDGE", 4)),
}

TIMEOUTS = {
    "setup": 300,
    "probe": 900,
    "gold": 900,
    "agent": int(os.environ.get("T_AGENT", 1800)),
    "capture": 300,
    "test": 900,
    "judge": 600,
}

STAGES = ["setup", "probe", "gold", "agent", "capture", "test", "judge"]

# setuptools_scm generates this at build time; we synthesize it per worktree.
VERSION_STUB = (
    'version = "8.0.0.dev0"\n'
    'version_tuple = (8, 0, 0, "dev0")\n'
    "__version__ = version\n"
)
