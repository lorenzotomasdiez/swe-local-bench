#!/usr/bin/env bash
# Bootstrap the harness. Idempotent: safe to re-run.
# Usage: setup.sh [doctor]   - `doctor` verifies only, changes nothing.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
REPO="$ROOT/pytest"
MODE="${1:-setup}"
FAIL=0

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; FAIL=1; }
step() { printf '\n\033[36m▸ %s\033[0m\n' "$*"; }

step "checking tools"
for t in git jq uv gh claude pi tar; do
  command -v "$t" >/dev/null && ok "$t" || bad "$t not found on PATH"
done

PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
if [ -n "$PYV" ] && python3 -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)'; then
  ok "python3 $PYV"
else
  bad "python3 >= 3.11 required (found ${PYV:-none})"
fi

gh auth status >/dev/null 2>&1 && ok "gh authenticated" || bad "gh not authenticated - run: gh auth login"

step "checking claude CLI"
# macOS ships no `timeout`; perl's alarm is always available.
_timeout() { local s=$1; shift; perl -e 'alarm shift; exec @ARGV' "$s" "$@"; }
if _timeout 90 claude -p 'reply with exactly: OK' 2>/dev/null | grep -q OK; then
  ok "claude -p responds"
else
  bad "claude -p did not respond - check your login"
fi

step "checking pi CLI"
# pi drives the non-Claude runners. Its credentials live in ~/.pi/agent/auth.json
# (or provider env vars); a missing key only surfaces at agent time otherwise.
if _timeout 120 pi -p --no-session 'reply with exactly: OK' 2>/dev/null | grep -q OK; then
  ok "pi -p responds"
else
  bad "pi -p did not respond - run: pi, then /login"
fi

step "checking repo"
if [ -d "$REPO/.git" ]; then
  ok "clone present ($(git -C "$REPO" rev-list --count HEAD) commits)"
  [ "$(git -C "$REPO" rev-parse --is-shallow-repository)" = "false" ] \
    && ok "full history" || bad "clone is shallow - run: git -C pytest fetch --unshallow"
else
  bad "missing clone - run: git clone https://github.com/pytest-dev/pytest.git"
fi

if [ "$MODE" = "doctor" ]; then
  step "venv"
  [ -x "$VENV/bin/python" ] && ok "venv built" || bad "venv missing - run: make setup"
  # grep -c, not wc -l: the file has no trailing newline, so wc undercounts
  # by one and the dataset silently looks smaller than it is.
  [ -f "$ROOT/harness/instances.jsonl" ] \
    && ok "instances.jsonl ($(grep -c . "$ROOT/harness/instances.jsonl") instances)" \
    || bad "instances.jsonl missing - run: make instances"
  [ "$FAIL" = 0 ] && printf '\n\033[32mall good\033[0m\n' || printf '\n\033[31mproblems found\033[0m\n'
  exit "$FAIL"
fi

[ "$FAIL" = 0 ] || { printf '\n\033[31mfix the above before continuing\033[0m\n'; exit 1; }

step "building shared venv"
# One venv holds pytest's DEPENDENCIES. pytest itself is deliberately
# uninstalled afterwards: an editable install registers a meta-path finder
# that silently overrides PYTHONPATH, which would make every instance test
# the main clone instead of its own worktree.
if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python 3.12 "$VENV" >/dev/null || exit 1
fi
uv pip install -q --python "$VENV/bin/python" -e "$REPO[dev]" || exit 1
uv pip uninstall -q --python "$VENV/bin/python" pytest >/dev/null 2>&1
ok "deps installed, pytest itself removed"

step "smoke test (does a worktree resolve to its own source?)"
SMOKE=$(mktemp -d)
git -C "$REPO" archive HEAD | tar -x -C "$SMOKE"
printf 'version = "8.0.0.dev0"\nversion_tuple = (8, 0, 0, "dev0")\n__version__ = version\n' \
  > "$SMOKE/src/_pytest/_version.py"
RESOLVED=$(PYTHONPATH="$SMOKE/src" "$VENV/bin/python" \
  -c 'import _pytest,pathlib;print(pathlib.Path(_pytest.__file__).parent)' 2>&1)
case "$RESOLVED" in
  "$SMOKE"/*) ok "imports resolve to the worktree" ;;
  *) bad "LEAK: resolved to $RESOLVED"; rm -rf "$SMOKE"; exit 1 ;;
esac

if (cd "$SMOKE" && PYTHONPATH="$SMOKE/src" "$VENV/bin/python" -m pytest \
     testing/test_assertion.py -q -x --no-header -p no:cacheprovider 2>&1 | tail -1 \
     | grep -qE '[0-9]+ passed'); then
  ok "pytest runs from source"
else
  bad "smoke test failed - inspect manually"
fi
rm -rf "$SMOKE"

[ "$FAIL" = 0 ] && printf '\n\033[32msetup complete - run: make pilot\033[0m\n' || exit 1
