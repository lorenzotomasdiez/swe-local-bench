#!/usr/bin/env bash
# Benchmark every runner over the same instances, one runner at a time.
#
#   bash harness/sweep.sh [N] [runner ...]
#
# Runners are run sequentially rather than in parallel: they share the agent
# concurrency limit and, for the Claude runners, the same rate limit, so
# overlapping them would only trade wall-clock for throttling. Order is
# cheapest first, so a broken sweep is caught before the expensive runners.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

N="${1:-10}"
shift || true
RUNNERS=("$@")
if [ ${#RUNNERS[@]} -eq 0 ]; then
  RUNNERS=(pi-deepseek-v4-flash claude-haiku claude-sonnet claude-opus)
fi

for r in "${RUNNERS[@]}"; do
  printf '\n\033[36m▸ %s (%s instances)\033[0m\n' "$r" "$N"
  RUNNER="$r" python3 orchestrate.py --limit "$N" --fresh --no-ui \
    > "/tmp/sweep-$r.log" 2>&1
  rc=$?
  RUNNER="$r" python3 render.py | tail -n +2
  [ $rc -eq 0 ] || printf '\033[31m%s exited %s - see /tmp/sweep-%s.log\033[0m\n' "$r" "$rc" "$r"
done

printf '\n\033[36m▸ metrics\033[0m\n'
python3 metrics.py "${RUNNERS[@]}"
