# swe-local-bench

A local, self-contained SWE-bench-style harness.
It mines real bug-fix pull requests, reconstructs the repository state before and after each fix, lets a coding agent attempt the fix from the issue text alone, and scores it against the maintainers' own tests.

Currently targets [`pytest-dev/pytest`](https://github.com/pytest-dev/pytest).

## Results

<!-- RESULTS:BEGIN -->
Last sweep: **15 instances**, 4 runners, judged by Claude `opus`.

| Runner | Solve rate | TP | FP | FN | TN | Avg time | Avg cost | Total | $/win |
|---|---|---|---|---|---|---|---|---|---|
| pi-deepseek-v4-flash | 5/15 (33%) | 2 | 3 | 2 | 8 | 3.8m | $0.0322 | $0.48 | $0.24 |
| claude-haiku | 5/15 (33%) | 4 | 1 | 2 | 8 | 6.6m | $0.7730 | $11.59 | $2.90 |
| claude-sonnet | 10/15 (67%) | 10 | 0 | 3 | 2 | 2.6m | $0.7537 | $11.31 | $1.13 |
| claude-opus | 8/15 (53%) | 8 | 0 | 5 | 2 | 4.3m | $1.2559 | $18.84 | $2.35 |

`TP` passed and judged valid. `FP` passed but judged wrong. `FN` judged valid but failed. `TN` failed and judged wrong.

Solve rate alone overstates a runner that scores `FP`, and understates one that scores `FN`.
Per-instance detail is in `harness/metrics.md`.
<!-- RESULTS:END -->

## Why this exists

Published benchmarks go stale: models are trained on them.
Every instance here is mined from pull requests merged well after the public SWE-bench cutoff, so no agent has memorized the answers.
The harness re-mines on demand, so the benchmark stays fresh as the upstream repo moves.

## Quick start

```bash
git clone https://github.com/pytest-dev/pytest.git      # the repo under test
make setup                                             # tools, venv, smoke test
make sweep                                             # every runner, PILOT instances
make metrics                                           # the comparison table
```

`make stop` halts a sweep and every agent it spawned.
The destructive targets refuse to run while a sweep is in flight, since a run costs real money and hours.

`make setup` is idempotent and verifies rather than assumes.
`make doctor` checks the environment without changing anything.

## Commands

`make help` lists these at any time.

| Command | What it does |
|---|---|
| `make setup` | install and verify everything |
| `make doctor` | verify the environment, change nothing |
| `make instances` | re-mine PRs into `instances.jsonl` |
| `make runners` | list the runners that can be benchmarked |
| `make sweep` | benchmark runners over the same instances |
| `make pilot RUNNER=x` | benchmark one runner |
| `make ids IDS=14493` | run specific PRs |
| `make status` | snapshot a run in progress, from any shell |
| `make metrics` | cross-runner table and confusion matrix |
| `make report` | per-runner detail |
| `make compare A=x B=y` | two-runner diff |
| `make stop` | halt a sweep and every agent it spawned |
| `make clean` | drop worktrees, run state and per-runner reports |
| `make clean-venv` | drop the venv too, slow to rebuild |

`sweep`, `pilot` and `ids` all pass `--fresh`, which discards prior results for the instances they touch, and only those.
Results for instances outside the current selection survive, and `make metrics` still counts them: a `PILOT=2` sweep on top of a previous `PILOT=10` one reports ten instances, two of them fresh.
`sweep` says how many of each up front, and `make clean-state` gives a clean slate.

`make metrics` refuses to write the README when the state it would publish contains an instance that never finished, or one measured before the `gold` stage existed.
An interrupted sweep is exactly when the numbers still on disk belong to the previous run, and a stale table under "Last sweep" is indistinguishable from a current one.

## How an instance is scored

Each instance is one merged pull request that closes at least one issue and touches both `src/` and `testing/`.
Its diff is split in two: `patch` (the source fix) and `test_patch` (the tests proving it).

```
setup ─┬─► probe ─► gold   probe  apply test_patch at base_commit, record which FAIL
       │                   gold   apply patch too, require every one of them to PASS
       └─► agent ─► capture      agent sees only the issue text
                          └────────► test    restore tests, apply test_patch, re-run
                                       └────► judge   compare against the real fix
```

`probe` and `gold` are the two halves of validating an instance: the tests must fail without the maintainers' fix and pass with it.
An instance that fails either half is unmeasurable rather than hard, and is reported as **discarded** instead of entering the denominator.
Only the agent branch is scored.

Two independent verdicts, deliberately kept separate:

| Verdict | Type | Meaning |
|---|---|---|
| `resolved` | objective, binary | every `FAIL_TO_PASS` test now passes and no `PASS_TO_PASS` test broke |
| `similarity` | subjective, graded | `equivalent` / `different-but-valid` / `worse` / `wrong` |

**`resolved` is the headline metric.**
`similarity` is the diagnostic that explains why.

Crossing them gives the confusion matrix that `make metrics` reports:

| | judge says valid | judge says wrong |
|---|---|---|
| **passed tests** | `TP` genuinely fixed | `FP` passes but behaviourally wrong |
| **failed tests** | `FN` plausible fix the tests reject | `TN` genuinely failed |

Neither signal is ground truth alone.
A fix can pass every test while leaking global state, and a defensible fix can fail tests that encode one specific redesign.
The off-diagonal is where the benchmark is misleading you, in one direction or the other, so `FP` and `FN` counts matter as much as the solve rate.

## Design notes

These are the non-obvious parts. Each was a bug that produced silently wrong results before it was found.

**The agent must not see future git history.**
A `git worktree` shares the parent `.git`, which lets the agent read the actual fix commit and score ~100% for free.
Instances are materialized with `git archive` into a fresh single-commit repo instead.

**Nor the evaluation copies.**
The `probe` copy holds the tests and the `gold` copy holds the actual fix, so both are extracted under `pytest-worktrees/eval/` while the agent works in `pytest-worktrees/agent/`.
They are never siblings of the agent's checkout: a stray `ls ..` must not be able to hand over the answer.
Each is deleted as soon as its stage is done, well before scoring.

**A failing test is not proof of a valid instance.**
`probe` establishes that the tests fail at `base_commit`, but tests fail for reasons the pull request never addressed: a missing fixture, an environment mismatch, or a part of the diff that lives outside `src/` and `testing/` and is therefore in neither `patch` nor `test_patch`.
Such a test is indistinguishable from a real `FAIL_TO_PASS` and is unresolvable by any agent, so it would surface as every runner failing a hard problem rather than as a broken instance.
`gold` closes that gap by making the same assertion `test` makes about the agent, against the reference fix: `base + patch + test_patch` must pass every `FAIL_TO_PASS` test with no `PASS_TO_PASS` regression.
Both stages grade through the same function, so the rules that validate an instance cannot drift from the rules the agent is scored under.
When `gold` fails, `resolved` stays `null` and the instance is discarded with the reason, for every runner at once - it is not counted as a loss against whichever runner happened to draw it.

**Time and cost are summed over the scored instances only.**
A discarded instance still burned agent money, but pricing a solve rate against work that solve rate does not account for makes `$/win` quietly wrong.

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
  config.py           paths, concurrency limits, timeouts, runners
  orchestrate.py      async stage machine
  sweep.sh            benchmark every runner over the same instances
  metrics.py          cross-runner table, confusion matrix, README injection
  metrics.md          the comparison result (tracked)
  render.py           live status table
  report.py           per-runner detail       (gitignored)
  compare.py          two-runner diff
pytest/               the repo under test     (gitignored)
pytest-worktrees/
  agent/<id>/         what the agent edits    (gitignored)
  eval/<id>/          probe and gold copies   (gitignored)
harness/state|runs/   run state and logs      (gitignored)
```

Run artifacts stay local by design: they are large, machine-specific, and regenerated by every run.

## Runners

The unit of comparison is a **runner**: a CLI harness plus the model driving it.
Both halves matter, since the same model scores differently under a different harness, so `claude-opus` and `pi-deepseek-v4-flash` are named as wholes rather than as models.

```bash
make runners                                  # list them
make pilot RUNNER=pi-deepseek-v4-flash        # benchmark one
make sweep                                    # benchmark all of them, same instances
make metrics                                  # solve rate, confusion matrix, time, cost
```

`make sweep` runs the runners one at a time rather than in parallel.
They share the agent concurrency limit, and the Claude runners share a rate limit, so overlapping them trades wall-clock for throttling.
It goes cheapest first, so a broken sweep surfaces before the expensive runners spend anything.

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
