# swe-local-bench

A local, self-contained SWE-bench-style harness.
It mines real bug-fix pull requests, reconstructs the repository state before and after each fix, lets a coding agent attempt the fix from the issue text alone, and scores it against the maintainers' own tests.

Currently targets [`pytest-dev/pytest`](https://github.com/pytest-dev/pytest).

## Why this exists

Published benchmarks go stale: models are trained on them.
Every instance here is mined from pull requests merged well after the public SWE-bench cutoff, so no agent has memorized the answers.
The harness re-mines on demand, so the benchmark stays fresh as the upstream repo moves.

## Quick start

```bash
git clone https://github.com/pytest-dev/pytest.git      # the repo under test
make setup                                             # tools, venv, smoke test
make pilot                                             # 3 instances
make run                                               # all instances
make report                                            # results-<model>.md
```

`make setup` is idempotent and verifies rather than assumes.
`make doctor` checks the environment without changing anything.

## How an instance is scored

Each instance is one merged pull request that closes at least one issue and touches both `src/` and `testing/`.
Its diff is split in two: `patch` (the source fix) and `test_patch` (the tests proving it).

```
setup ─┬─► probe   apply test_patch at base_commit, record which tests FAIL
       └─► agent ─► capture      agent sees only the issue text
                          └────────► test    restore tests, apply test_patch, re-run
                                       └────► judge   compare against the real fix
```

Two independent verdicts, deliberately kept separate:

| Verdict | Type | Meaning |
|---|---|---|
| `resolved` | objective, binary | every `FAIL_TO_PASS` test now passes and no `PASS_TO_PASS` test broke |
| `similarity` | subjective, graded | `equivalent` / `different-but-valid` / `worse` / `wrong` |

**`resolved` is the headline metric.** `similarity` is a diagnostic: it explains *why* something failed, and disagreement between the two usually indicates a harness bug rather than an agent one.

## Design notes

These are the non-obvious parts. Each was a bug that produced silently wrong results before it was found.

**The agent must not see future git history.**
A `git worktree` shares the parent `.git`, which lets the agent read the actual fix commit and score ~100% for free.
Instances are materialized with `git archive` into a fresh single-commit repo instead.

**An editable install overrides `PYTHONPATH`.**
`pip install -e` registers a meta-path finder that wins over `sys.path`, so every instance silently tests the main clone rather than its own checkout.
The shared venv installs pytest's *dependencies* and then uninstalls pytest itself.
`make setup` asserts imports resolve into the worktree and fails loudly otherwise.

**`_pytest/_version.py` is generated at build time** by setuptools_scm, so a raw checkout cannot import pytest.
The harness synthesizes it per instance, and rewrites it again immediately before scoring.
The rewrite is not redundant: an agent that triggers a build - `pip install -e .`, `tox`, or running pytest a certain way - makes setuptools_scm regenerate the file from the synthetic one-commit repo as `0.1.dev1+g<sha>`.
pytest's own `pyproject.toml` sets `minversion = "2.0"`, so pytest then refuses to start, collects nothing, and a completely correct fix scores zero.

**Test targets are discovered, not guessed.**
A `test_patch` often touches non-tests (`pytest.ini`, `example_scripts/`), which makes pytest abort and collect nothing.
Filtering by filename is wrong in the other direction: pytest's own suite adds `testing/python/*.py` to `python_files`, so a `test_*.py` rule discards ~17 valid instances.
The harness asks pytest via `--collect-only` instead.

**Zero parsed results is a harness failure, not a verdict.**
It is indistinguishable from "no failing tests" and would quietly discard good instances.

**The agent's fix is defined as exactly its changes under `src/`.**
Before scoring, everything outside `src/` is reverted to base and any file the agent added there is deleted.
That covers tests, so the agent cannot pass by weakening the suite, and equally covers config, tooling and build metadata, so an incidental `pip install -e .` cannot break scoring.
Gold patches only ever touch `src/`, so nothing legitimate is discarded.

**Cost is read from the CLI, never estimated.**
Token-count heuristics drift as pricing changes and silently misprice cache reads.
For pi, only `message_end` events are summed: `turn_end` repeats the same message object and `agent_end` repeats the whole conversation, so counting those multiplies the bill.
An unparseable cost is recorded as unknown rather than as zero, because a zero would quietly drag an average down.

**Runners are not perfectly isolated from user config.**
Both CLIs load user-level context (`~/.claude/CLAUDE.md`, `~/.pi` skills) that the harness does not control.
The repo under test carries no `AGENTS.md` or `CLAUDE.md`, so project-level context is at least equal across runners.
This is a known asymmetry, not a solved problem.

## Layout

```
Makefile              entry point for everything
harness/
  mine.sh             GraphQL sweep of merged PRs
  resolve.py          PR -> instance (issue text, base/fix commits, split patches)
  instances.jsonl     the dataset (tracked)
  config.py           paths, concurrency limits, timeouts, models
  orchestrate.py      async stage machine
  render.py           live status table
  report.py           results-<model>.md / .json
  compare.py          side-by-side model comparison
pytest/               the repo under test        (gitignored)
pytest-worktrees/     per-instance checkouts     (gitignored)
harness/state|runs/   run state and logs         (gitignored)
```

Run artifacts stay local by design: they are large, machine-specific, and regenerated by every run.

## Runners

The unit of comparison is a **runner**: a CLI harness plus the model driving it.
Both halves matter, since the same model scores differently under a different harness, so `claude-opus` and `pi-deepseek-v4-flash` are named as wholes rather than as models.

```bash
make runners                                  # list them
make pilot RUNNER=pi-deepseek-v4-flash        # benchmark one
make compare A=claude-opus B=claude-haiku
```

State, logs and results are scoped per runner, so runs never overwrite each other.

Adding a runner means adding an entry to `RUNNERS` in `harness/config.py`.
A new CLI additionally needs a command builder and a cost parser in `CLIS` in `harness/orchestrate.py` - roughly ten lines each.

Every model and thinking level is pinned in the harness rather than inherited from `~/.claude/settings.json` or `~/.pi/agent/settings.json`.
A personal setting change must never silently move a benchmark number.

`JUDGE_MODEL` is deliberately not part of the runner.
It stays fixed across every comparison, otherwise two variables move at once, and it is always Claude so that a runner under test never grades itself.

## Cost and time

Each runner reports what it spent, taken from the CLI's own accounting: `total_cost_usd` for Claude, and the sum of per-turn `usage.cost.total` for pi.
A runner that resolves 60% for twenty times the money is not the better runner, and without per-issue cost the table cannot say so.

Only agent spend is attributed to the runner.
The summarizer and the judge are harness overhead and are billed to the harness, not to the thing being measured.

## Tuning

Stage concurrency is set per stage, since API-bound and CPU-bound stages have different ceilings.

```bash
W_AGENT=6 make run        # default 4
T_AGENT=3600 make run     # per-agent timeout, seconds
```

Agents often run the full pytest suite to check their own work, which is the real cost driver.
Note that pytest's own suite calls `faulthandler._sigabrt()` on purpose, so macOS may show crash dialogs during a run. They are harmless.

## Interpreting results

A single run is one sample of a nondeterministic process.
Differences of a few points between models on a small instance set are noise.

Some instances are API design changes rather than bug fixes.
These systematically penalize valid alternative solutions, because the issue describes a symptom while the tests encode one specific redesign.
An agent can write defensible code and still score `resolved: no`.
