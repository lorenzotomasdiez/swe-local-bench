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

# --fresh discards prior results, but only for the instances this sweep
# selects. Count exactly those: saying "10 results will be discarded" when a
# PILOT=2 sweep deletes 2 of them and silently keeps 8 is worse than saying
# nothing, because the kept ones are what metrics.py publishes at the end.
printf 'sweep: %s instances x %s runner(s): %s\n' "$N" "${#RUNNERS[@]}" "${RUNNERS[*]}"
SELECTED=$(head -n "$N" instances.jsonl | jq -r .instance_id)
for r in "${RUNNERS[@]}"; do
  hit=0; keep=0
  for f in "state/$r"/*.json; do
    [ -e "$f" ] || continue
    # -x: whole-line match. A substring test would count an instance whose id
    # is a prefix of a selected one as selected.
    if printf '%s\n' "$SELECTED" | grep -qxF "$(basename "$f" .json)"; then
      hit=$((hit + 1))
    else
      keep=$((keep + 1))
    fi
  done
  [ "$hit" -gt 0 ] && printf '\033[33m  %s: %s of the %s selected instance(s) already measured - those will be re-run\033[0m\n' "$r" "$hit" "$N"
  # Stale results are not deleted, and metrics.py will fold them into the
  # published table alongside this sweep's. That mixes two runs of possibly
  # two different harness versions into one solve rate.
  [ "$keep" -gt 0 ] && printf '\033[33m  %s: %s older result(s) kept and STILL COUNTED by make metrics - run make clean-state for a clean slate\033[0m\n' "$r" "$keep"
done

ABORTED=0
trap 'ABORTED=1' INT TERM

for r in "${RUNNERS[@]}"; do
  printf '\n\033[36m▸ %s (%s instances)\033[0m\n' "$r" "$N"
  RUNNER="$r" python3 orchestrate.py --limit "$N" --fresh --no-ui \
    > "/tmp/sweep-$r.log" 2>&1
  rc=$?
  RUNNER="$r" python3 render.py | tail -n +2
  [ $rc -eq 0 ] || printf '\033[31m%s exited %s - see /tmp/sweep-%s.log\033[0m\n' "$r" "$rc" "$r"
  # Ctrl-C must end the sweep, not the current runner. Bash keeps looping after
  # a child dies on SIGINT, so without this an interrupt silently demoted
  # itself into "skip to the next runner" and every remaining runner got a few
  # seconds of life before the next interrupt - four half-runs and no results.
  if [ "$ABORTED" = 1 ] || [ $rc -eq 130 ]; then
    printf '\033[31m\nsweep interrupted during %s - stopping here\033[0m\n' "$r"
    printf '\033[33mstate for %s is incomplete; re-run or make clean-state\033[0m\n' "$r"
    exit 130
  fi
done

printf '\n\033[36m▸ metrics\033[0m\n'
python3 metrics.py --readme "${RUNNERS[@]}"
