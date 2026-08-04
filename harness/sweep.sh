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

# Validate the whole list before spending anything. A sweep costs money and
# hours, so a typo must fail in the first second, not after the cheap runner
# has finished and the expensive one starts on a name nobody meant.
KNOWN=$(python3 -c 'import config; print(" ".join(config.RUNNERS))')
for r in "${RUNNERS[@]}"; do
  case " $KNOWN " in
    *" $r "*) ;;
    *) printf '\033[31munknown runner: %s\033[0m\nknown: %s\n' "$r" "$KNOWN"; exit 1 ;;
  esac
done

# --fresh discards prior results for these instances. Say so up front: an
# accidental re-run of an already-benchmarked runner is expensive to undo.
printf 'sweep: %s instances x %s runner(s): %s\n' "$N" "${#RUNNERS[@]}" "${RUNNERS[*]}"
for r in "${RUNNERS[@]}"; do
  n=$(ls "state/$r"/*.json 2>/dev/null | wc -l | tr -d ' ')
  [ "$n" -gt 0 ] && printf '\033[33m  %s already has %s result(s) - they will be discarded\033[0m\n' "$r" "$n"
done

for r in "${RUNNERS[@]}"; do
  printf '\n\033[36m▸ %s (%s instances)\033[0m\n' "$r" "$N"
  RUNNER="$r" python3 orchestrate.py --limit "$N" --fresh --no-ui \
    > "/tmp/sweep-$r.log" 2>&1
  rc=$?
  RUNNER="$r" python3 render.py | tail -n +2
  [ $rc -eq 0 ] || printf '\033[31m%s exited %s - see /tmp/sweep-%s.log\033[0m\n' "$r" "$rc" "$r"
done

printf '\n\033[36m▸ metrics\033[0m\n'
python3 metrics.py --readme "${RUNNERS[@]}"
