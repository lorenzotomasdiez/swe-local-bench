#!/usr/bin/env python3
"""Resolve each candidate PR into a SWE-bench-style instance:
issue text + base_commit (before) + fix_commit (after) + patch/test_patch."""
import json, subprocess, sys, pathlib

REPO = "/Users/lorenzotomasdiez/projects/mini-swe-bench-harness/pytest"
SRC_PREFIXES, TEST_PREFIXES = ("src/",), ("testing/",)

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout

def split_diff(base, fix):
    """Return (patch, test_patch) - source changes vs test changes."""
    names = git("diff", "--name-only", base, fix).split()
    src  = [f for f in names if f.startswith(SRC_PREFIXES)]
    test = [f for f in names if f.startswith(TEST_PREFIXES)]
    patch      = git("diff", base, fix, "--", *src)  if src  else ""
    test_patch = git("diff", base, fix, "--", *test) if test else ""
    return patch, test_patch, src, test

out = []
for line in open(sys.argv[1]):
    pr = json.loads(line)
    # filter: merged, closes >=1 issue, touches src/ and testing/, tidy diff
    files = [f["path"] for f in pr["files"]["nodes"]]
    if not (pr.get("mergeCommit") and pr["closingIssuesReferences"]["nodes"]
            and any(f.startswith(SRC_PREFIXES) for f in files)
            and any(f.startswith(TEST_PREFIXES) for f in files)
            and len(files) <= 10):
        continue
    fix = pr["mergeCommit"]["oid"]
    parents = git("rev-list", "--parents", "-n1", fix).split()
    if len(parents) < 2:
        continue
    base = parents[1]                      # first parent == main before the PR landed
    patch, test_patch, src, test = split_diff(base, fix)
    if not patch or not test_patch:
        continue
    issues = pr["closingIssuesReferences"]["nodes"]
    problem = "\n\n---\n\n".join(
        f"# {i['title']}\n\n{i['bodyText']}".strip() for i in issues
    )
    out.append({
        "instance_id":       f"pytest-dev__pytest-{pr['number']}",
        "pr":                pr["number"],
        "pr_title":          pr["title"],
        "merged_at":         pr["mergedAt"][:10],
        "issues":            [i["number"] for i in issues],
        "base_commit":       base,          # state WITH the bug
        "fix_commit":        fix,           # state WITH the fix
        "problem_statement": problem,
        "patch":             patch,         # gold source fix
        "test_patch":        test_patch,    # tests proving it
        "src_files":         src,
        "test_files":        test,
    })

dst = pathlib.Path(sys.argv[2])
dst.write_text("\n".join(json.dumps(o) for o in out))
print(f"resolved {len(out)} instances -> {dst}")
