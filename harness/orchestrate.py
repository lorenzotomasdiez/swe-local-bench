#!/usr/bin/env python3
"""Async orchestrator for the mini-SWE-bench harness.

Each instance advances through an independent stage machine. Nothing is
batched: instance A can be in `judge` while instance B is still in `setup`.

    setup ─┬─► probe  (measures FAIL_TO_PASS in a throwaway copy)  ─┐
           └─► agent ─► capture                                    ─┴─► test ─► judge

The agent copy never sees the tests. The probe copy is deleted before scoring.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import sys
import time

from config import (
    AGENT,
    HARNESS,
    INSTANCES,
    LIMITS,
    PYTHON,
    REPO,
    ROOT,
    RUNNER,
    RUNS,
    STAGES,
    JUDGE_MODEL,
    STATE,
    TIMEOUTS,
    VERSION_STUB,
    WORKTREES,
)
import render

RESULT_RE = re.compile(
    r"^(\S+::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", re.M
)


# ─────────────────────────────── state ────────────────────────────────


class State:
    """Per-instance state, written atomically so `make status` never tears."""

    def __init__(self, iid: str):
        self.iid = iid
        self.path = STATE / f"{iid}.json"
        self.d = json.loads(self.path.read_text()) if self.path.exists() else {
            "id": iid,
            "runner": RUNNER,
            "stage": None,
            "status": "pending",
            "stages": {},
            "started": None,
            "f2p": [],
            "p2p": [],
            "resolved": None,
            "similarity": None,
            "agent_cost_usd": None,
            "note": "",
        }
        self.d["runner"] = RUNNER

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=2))
        os.replace(tmp, self.path)  # atomic

    def begin(self, stage: str) -> None:
        self.d["started"] = self.d["started"] or time.time()
        self.d["stage"] = stage
        self.d["status"] = "running"
        self.d["stages"][stage] = {"status": "running", "t0": time.time()}
        self.save()

    def end(self, stage: str, status: str, **extra) -> None:
        s = self.d["stages"].setdefault(stage, {"t0": time.time()})
        s["status"] = status
        s["secs"] = round(time.time() - s["t0"], 1)
        s.update(extra)
        self.d["status"] = "running" if status == "ok" else status
        self.save()

    def done(self, status: str, note: str = "") -> None:
        self.d["status"] = status
        self.d["stage"] = "done"
        if note:
            self.d["note"] = note
        self.save()

    def skip(self, stage: str) -> bool:
        return self.d["stages"].get(stage, {}).get("status") == "ok"


# ────────────────────────────── helpers ───────────────────────────────


# Every child runs in its own process group so it can be killed as a tree.
# An agent CLI spawns its own children - node, python, git - and killing only
# the parent leaves those running: an orphaned agent kept burning API credit
# for 38 minutes past its 30 minute timeout because the orchestrator died
# first and nothing was left to enforce it.
LIVE: set[int] = set()


def _killpg(pgid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        except OSError:
            return


def _reap_all(*_) -> None:
    """Take every running agent down with us, then die."""
    for pgid in list(LIVE):
        _killpg(pgid)
    sys.exit(130)


async def sh(cmd: list[str], cwd=None, timeout=300, env=None, log=None):
    """Run a command, capture output, optionally tee to a log file."""
    e = {**os.environ, **(env or {})}
    p = await asyncio.create_subprocess_exec(
        *cmd, cwd=cwd, env=e,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    LIVE.add(p.pid)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _killpg(p.pid)
        try:
            await asyncio.wait_for(p.wait(), timeout=10)
        except asyncio.TimeoutError:
            pass
        if log:
            log.write_text("*** TIMEOUT ***\n")
        raise
    finally:
        LIVE.discard(p.pid)
    text = out.decode("utf-8", "replace")
    if log:
        log.write_text(text)
    return p.returncode, text


def write_version_stub(wt) -> None:
    """(Re)write the version file setuptools_scm would normally generate.

    Rewritten before scoring, not just at setup: an agent that triggers a
    build - `pip install -e .`, `tox`, even running pytest a certain way -
    makes setuptools_scm regenerate this from the synthetic one-commit repo
    as `0.1.dev1+g<sha>`. pytest's own pyproject.toml sets minversion = 2.0,
    so pytest then refuses to start and a correct fix scores zero.
    """
    (wt / "src" / "_pytest" / "_version.py").write_text(VERSION_STUB)


async def materialize(dest, commit: str, scrub: bool):
    """Extract `commit` into `dest` as a standalone git repo.

    We use `git archive` rather than `git worktree` on purpose: a worktree
    shares the parent .git, which would let the agent read the actual fix
    commit out of future history and score ~100% for free.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    rc, out = await sh(["bash", "-c",
                        f"git -C {REPO} archive {commit} | tar -x -C {dest}"])
    if rc != 0:
        raise RuntimeError(f"archive failed: {out}")

    write_version_stub(dest)

    if scrub:
        await sh(["git", "init", "-q", "-b", "main"], cwd=dest)
        await sh(["git", "add", "-A"], cwd=dest)
        await sh(["git", "-c", "user.email=h@h", "-c", "user.name=harness",
                  "commit", "-qm", "base"], cwd=dest)
    return dest


async def pytest_run(wt, files: list[str], timeout: int, log=None):
    """Run the given test files; return {nodeid: outcome}."""
    env = {"PYTHONPATH": str(wt / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    rc, out = await sh(
        # -v is required: node IDs only appear in verbose output, and the
        # scorer parses them. Never add -q here.
        [str(PYTHON), "-m", "pytest", *files,
         "-v", "--tb=no", "-p", "no:cacheprovider", "--no-header"],
        cwd=wt, timeout=timeout, env=env, log=log,
    )
    return {m.group(1): m.group(2) for m in RESULT_RE.finditer(out)}, rc, out


async def collect_targets(wt, files: list[str]) -> list[str]:
    """Which of these paths can pytest actually collect tests from?

    A test_patch often touches things that are not test modules: pytest.ini,
    example_scripts/ fixture data, typing_checks.py. Passing those to pytest
    makes it abort with "not found" and collect nothing, which looks exactly
    like a broken instance. We ask pytest per file instead of guessing from
    filenames - pytest's own suite adds `testing/python/*.py` to python_files,
    so a name-based rule would wrongly discard ~17 valid instances.
    """
    env = {"PYTHONPATH": str(wt / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    out_files = []
    for f in files:
        if not f.endswith(".py"):
            continue
        rc, out = await sh(
            [str(PYTHON), "-m", "pytest", f, "--collect-only", "-q",
             "--no-header", "-p", "no:cacheprovider"],
            cwd=wt, timeout=120, env=env,
        )
        if rc == 0 and "::" in out:
            out_files.append(f)
    return out_files


async def claude(prompt: str, cwd, timeout: int, log=None, model=None) -> str:
    """Run Claude and return its text reply. Used for capture and judge only."""
    rc, out = await sh(
        ["claude", "-p", prompt, "--dangerously-skip-permissions",
         "--model", model or JUDGE_MODEL],
        cwd=cwd, timeout=timeout, log=log,
    )
    if rc != 0:
        raise RuntimeError(f"claude exited {rc}")
    return out


# ──────────────────────────── agent runners ───────────────────────────
#
# Each runner reports what it spent. Cost is a first-class result: a runner
# that resolves 60% for 20x the money is not the better runner, and without
# per-runner cost the comparison table cannot say so.


def _claude_cmd(spec, prompt):
    return ["claude", "-p", prompt, "--dangerously-skip-permissions",
            "--model", spec["model"], "--output-format", "json"]


def _claude_cost(out: str) -> float:
    """`--output-format json` emits one object with total_cost_usd."""
    return float(json.loads(out).get("total_cost_usd") or 0.0)


def _pi_cmd(spec, prompt):
    cmd = ["pi", "-p", prompt, "--mode", "json", "--no-session",
           "--provider", spec["provider"], "--model", spec["model"]]
    if spec.get("thinking"):
        cmd += ["--thinking", spec["thinking"]]
    return cmd


def _pi_cost(out: str) -> float:
    """Sum cost over assistant turns in pi's JSONL event stream.

    Only `message_end` is summed. `turn_end` repeats the same message object
    and `agent_end` repeats the whole conversation, so counting those would
    multiply the bill. Tool results carry no usage.
    """
    total = 0.0
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "message_end":
            continue
        msg = ev.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        total += float(((msg.get("usage") or {}).get("cost") or {}).get("total") or 0.0)
    return total


CLIS = {
    "claude": (_claude_cmd, _claude_cost),
    "pi": (_pi_cmd, _pi_cost),
}


async def run_agent(prompt: str, cwd, timeout: int, log=None) -> float:
    """Run the configured agent in `cwd`; return what it cost in USD.

    The agent edits the checkout in place - the edits are the result. The
    return value is only the price tag.
    """
    build, price = CLIS[AGENT["cli"]]
    rc, out = await sh(build(AGENT, prompt), cwd=cwd, timeout=timeout, log=log)
    if rc != 0:
        raise RuntimeError(f"{AGENT['cli']} exited {rc}")
    try:
        return price(out)
    except Exception:
        # A cost we cannot parse must not fail an otherwise good run; it is
        # reported as unknown rather than silently counted as zero.
        return float("nan")


# ─────────────────────────────── stages ───────────────────────────────

SEM = {k: asyncio.Semaphore(v) for k, v in LIMITS.items()}


async def stage_setup(inst, st):
    async with SEM["setup"]:
        st.begin("setup")
        wt = WORKTREES / inst["instance_id"]
        await materialize(wt / "agent", inst["base_commit"], scrub=True)
        await materialize(wt / "probe", inst["base_commit"], scrub=True)
        (RUNS / inst["instance_id"]).mkdir(parents=True, exist_ok=True)
        st.end("setup", "ok")


async def stage_probe(inst, st):
    """Apply the tests at base_commit and see which fail. Then delete."""
    async with SEM["probe"]:
        st.begin("probe")
        wt = WORKTREES / inst["instance_id"] / "probe"
        run = RUNS / inst["instance_id"]
        (run / "test_patch.diff").write_text(inst["test_patch"])
        rc, out = await sh(["git", "apply", str(run / "test_patch.diff")], cwd=wt)
        if rc != 0:
            st.end("probe", "failed", error=f"test_patch did not apply: {out[:300]}")
            return False
        targets = await collect_targets(wt, inst["test_files"])
        if not targets:
            st.d["note"] = "NO_TEST_TARGETS: test_patch touches no collectable test"
            st.end("probe", "ok", discriminator=False)
            st.save()
            return True
        st.d["targets"] = targets
        res, _, _ = await pytest_run(
            wt, targets, TIMEOUTS["probe"], run / "probe.log"
        )
        if not res:
            # Zero parsed results means collection blew up or the output format
            # changed - a harness bug. It must not be reported as "no failing
            # test", which would silently drop a perfectly good instance.
            st.end("probe", "failed", error="no test results parsed - see probe.log")
            return False
        f2p = sorted(k for k, v in res.items() if v in ("FAILED", "ERROR"))
        p2p = sorted(k for k, v in res.items() if v == "PASSED")
        st.d["f2p"], st.d["p2p"] = f2p, p2p
        shutil.rmtree(wt, ignore_errors=True)  # agent must never see it
        if not f2p:
            st.end("probe", "ok", discriminator=False)
            st.d["note"] = "NO_DISCRIMINATOR: tests already pass at base"
            st.save()
            return True
        st.end("probe", "ok", discriminator=True, n_f2p=len(f2p), n_p2p=len(p2p))
        return True


AGENT_PROMPT = """You are working in a checkout of the pytest source code that \
contains a bug. Below is the issue report describing it.

Fix the bug. Edit the source under `src/`. Do not ask questions; make the change.

--- ISSUE ---
{problem}
--- END ISSUE ---
"""


async def stage_agent(inst, st):
    async with SEM["agent"]:
        st.begin("agent")
        wt = WORKTREES / inst["instance_id"] / "agent"
        run = RUNS / inst["instance_id"]
        try:
            cost = await run_agent(
                AGENT_PROMPT.format(problem=inst["problem_statement"]),
                cwd=wt, timeout=TIMEOUTS["agent"], log=run / "agent.log",
            )
        except asyncio.TimeoutError:
            st.end("agent", "timeout")
            return False
        except Exception as e:
            st.end("agent", "failed", error=str(e)[:300])
            return False
        st.d["agent_cost_usd"] = None if cost != cost else round(cost, 6)  # NaN check
        st.end("agent", "ok")
        return True


SUMMARY_PROMPT = """Below is a diff you produced to fix a bug in pytest. In \
plain English, describe what you changed and why, in at most 8 lines. Output \
only the description.

{diff}
"""


async def stage_capture(inst, st):
    async with SEM["capture"]:
        st.begin("capture")
        wt = WORKTREES / inst["instance_id"] / "agent"
        run = RUNS / inst["instance_id"]
        await sh(["git", "add", "-A"], cwd=wt)
        _, diff = await sh(["git", "diff", "--cached"], cwd=wt)
        (run / "agent.patch").write_text(diff)
        if not diff.strip():
            st.end("capture", "failed", error="agent produced no changes")
            return False
        try:
            s = await claude(SUMMARY_PROMPT.format(diff=diff[:20000]),
                             cwd=wt, timeout=TIMEOUTS["capture"])
            (run / "agent_summary.txt").write_text(s)
        except Exception:
            pass  # summary is for humans; never fail the instance on it
        st.end("capture", "ok", diff_lines=len(diff.splitlines()))
        return True


async def stage_test(inst, st):
    """Reduce the agent's work to its source changes, apply the real tests, score.

    The agent's contribution is defined as exactly what it changed under
    `src/`. Everything else is reverted to base: test edits (so it cannot
    pass by weakening the suite), and equally config, tooling and build
    metadata (so an incidental `pip install -e .` cannot break scoring).
    Gold patches only ever touch `src/`, so nothing legitimate is discarded.
    """
    async with SEM["test"]:
        st.begin("test")
        wt = WORKTREES / inst["instance_id"] / "agent"
        run = RUNS / inst["instance_id"]
        outside_src = ":(exclude)src"
        await sh(["git", "restore", "--source=HEAD", "--staged", "--worktree",
                  "--", outside_src], cwd=wt)
        # restore only revives tracked files; drop anything the agent added.
        await sh(["git", "clean", "-fdq", "--", outside_src], cwd=wt)
        write_version_stub(wt)
        rc, out = await sh(["git", "apply", str(run / "test_patch.diff")], cwd=wt)
        if rc != 0:
            st.end("test", "failed", error=f"test_patch did not apply: {out[:300]}")
            return False
        res, _, _ = await pytest_run(
            wt, st.d.get("targets") or inst["test_files"],
            TIMEOUTS["test"], run / "test.log"
        )
        f2p, p2p = st.d["f2p"], st.d["p2p"]
        f2p_ok = [t for t in f2p if res.get(t) == "PASSED"]
        p2p_bad = [t for t in p2p if res.get(t) not in ("PASSED", "SKIPPED", "XFAIL")]
        resolved = bool(f2p) and len(f2p_ok) == len(f2p) and not p2p_bad
        st.d["resolved"] = resolved if f2p else None
        st.end("test", "ok", f2p_passed=len(f2p_ok), f2p_total=len(f2p),
               p2p_broken=len(p2p_bad))
        return True


JUDGE_PROMPT = """Compare two fixes for the same pytest bug. Ignore formatting, \
naming and whitespace; judge behaviour only.

--- ISSUE ---
{problem}
--- REFERENCE FIX (what maintainers merged) ---
{gold}
--- CANDIDATE FIX ---
{agent}
--- END ---

Reply with ONLY a JSON object:
{{"verdict": "equivalent"|"different-but-valid"|"worse"|"wrong",
  "reasoning": "<2-3 sentences>"}}
"""


async def stage_judge(inst, st):
    async with SEM["judge"]:
        st.begin("judge")
        run = RUNS / inst["instance_id"]
        agent_patch = (run / "agent.patch").read_text()
        try:
            out = await claude(
                JUDGE_PROMPT.format(problem=inst["problem_statement"][:6000],
                                    gold=inst["patch"][:20000],
                                    agent=agent_patch[:20000]),
                cwd=ROOT, timeout=TIMEOUTS["judge"], log=run / "judge.log",
                model=JUDGE_MODEL,
            )
            m = re.search(r"\{.*\}", out, re.S)
            v = json.loads(m.group(0))
            st.d["similarity"] = v.get("verdict")
            (run / "judge.json").write_text(json.dumps(v, indent=2))
        except Exception as e:
            st.end("judge", "failed", error=str(e)[:200])
            return False
        st.end("judge", "ok")
        return True


# ──────────────────────────── stage machine ───────────────────────────


async def run_instance(inst):
    st = State(inst["instance_id"])
    try:
        if not st.skip("setup"):
            await stage_setup(inst, st)

        # probe and agent are independent: run them concurrently.
        probe = asyncio.create_task(stage_probe(inst, st))

        async def agent_chain():
            return await stage_agent(inst, st) and await stage_capture(inst, st)

        agent_ok, probe_ok = await asyncio.gather(agent_chain(), probe)

        if not probe_ok:
            st.done("failed", "probe failed")
            return

        if not agent_ok:
            # The agent failed to deliver a fix - it timed out, crashed, or
            # produced no diff at all. That is a failed attempt, not an
            # unmeasurable one, so it scores as unresolved rather than
            # dropping out of the denominator. Excluding it would reward a
            # runner for failing loudly: an agent that edits nothing on three
            # instances would score better than one that tries and misses.
            #
            # The exception is an instance with no failing baseline, which
            # cannot discriminate anything for any runner.
            why = (st.d["stages"].get("capture", {}).get("error")
                   or st.d["stages"].get("agent", {}).get("error")
                   or st.d["stages"].get("agent", {}).get("status")
                   or "agent failed")
            if st.d.get("f2p"):
                st.d["resolved"] = False
                st.d["note"] = f"NO_FIX: {why}"
            st.done(st.d["stages"].get("agent", {}).get("status", "failed"))
            return
        if not await stage_test(inst, st):
            st.done("failed", "test stage failed")
            return
        await stage_judge(inst, st)
        st.done("ok")
    except Exception as e:
        st.done("failed", f"{type(e).__name__}: {e}"[:200])


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="run only the first N")
    ap.add_argument("--ids", default="", help="comma-separated PR numbers")
    ap.add_argument("--fresh", action="store_true", help="ignore existing state")
    ap.add_argument("--no-ui", action="store_true", help="plain log output")
    a = ap.parse_args()

    insts = [json.loads(l) for l in INSTANCES.read_text().splitlines() if l.strip()]
    if a.ids:
        want = {int(x) for x in a.ids.split(",")}
        insts = [i for i in insts if i["pr"] in want]
    if a.limit:
        insts = insts[: a.limit]
    if not insts:
        sys.exit("no instances selected")

    for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(s, _reap_all)

    STATE.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    if a.fresh:
        for i in insts:
            (STATE / f"{i['instance_id']}.json").unlink(missing_ok=True)

    print(f"runner {RUNNER} ({AGENT['cli']} / {AGENT['model']}), judge {JUDGE_MODEL}")
    print(f"running {len(insts)} instance(s): "
          f"{', '.join(str(i['pr']) for i in insts)}\n")

    ids = [i["instance_id"] for i in insts]
    tasks = [asyncio.create_task(run_instance(i)) for i in insts]
    ui = asyncio.create_task(render.live(ids, tasks, plain=a.no_ui))
    await asyncio.gather(*tasks)
    ui.cancel()
    render.final(ids)


if __name__ == "__main__":
    asyncio.run(main())
