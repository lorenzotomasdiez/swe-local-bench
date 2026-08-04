.PHONY: help setup doctor instances pilot run ids runners sweep metrics status report stop clean clean-worktrees clean-state clean-venv
.DEFAULT_GOAL := help

H := harness
PY := python3
PILOT ?= 10

# The runner under test. See RUNNERS in harness/config.py for the list.
RUNNER ?= claude-opus
export RUNNER

help:                     ## show this help
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

setup:                    ## install everything and verify it works
	@bash $(H)/setup.sh

doctor:                   ## verify the environment, change nothing
	@bash $(H)/setup.sh doctor

instances:                ## mine PRs -> harness/instances.jsonl
	@bash $(H)/mine.sh
	@cd $(H) && $(PY) resolve.py /tmp/prs.jsonl instances.jsonl

pilot:                    ## run PILOT instances (default 10): make pilot RUNNER=pi-deepseek-v4-flash
	@cd $(H) && $(PY) orchestrate.py --limit $(PILOT) --fresh

run:                      ## run all instances with live status
	@cd $(H) && $(PY) orchestrate.py

ids:                      ## run specific PRs: make ids IDS=14493,14466
	@cd $(H) && $(PY) orchestrate.py --ids $(IDS) --fresh

runners:                  ## list the runners that can be benchmarked
	@cd $(H) && $(PY) -c "import config,json; [print(f'{k:<24}{v[\"cli\"]:<8}{v[\"model\"]}') for k,v in config.RUNNERS.items()]"

compare:                  ## compare runners: make compare A=claude-opus B=claude-haiku
	@cd $(H) && $(PY) compare.py $(or $(A),claude-opus) $(or $(B),claude-sonnet)

sweep:                    ## benchmark runners over the same PILOT instances: make sweep RUNNERS="claude-haiku claude-opus"
	@bash $(H)/sweep.sh $(PILOT) $(RUNNERS)

metrics:                  ## solve rate, confusion matrix, time and cost per runner
	@cd $(H) && $(PY) metrics.py $(RUNNERS)

status:                   ## snapshot the current run (safe from another shell)
	@cd $(H) && $(PY) render.py

report:                   ## write results.md + results.json
	@cd $(H) && $(PY) report.py

# Every destructive target refuses to run while a sweep is in flight.
# A run costs real money and takes hours; deleting its state or its
# worktrees mid-flight throws that away with no way to recover it.
define no-run-in-flight
	@pgrep -f "orchestrate.py" >/dev/null 2>&1 && { \
	  echo "a run is in progress - stop it first (make stop)"; exit 1; } || true
endef

stop:                     ## stop a running sweep and its agents
	@pkill -f sweep.sh 2>/dev/null || true
	@pkill -f orchestrate.py 2>/dev/null || true
	@echo "stopped"

clean-worktrees:          ## delete extracted worktrees only
	$(no-run-in-flight)
	@rm -rf pytest-worktrees && echo "worktrees removed"

clean-state:              ## delete run state and logs (keeps instances.jsonl)
	$(no-run-in-flight)
	@rm -rf $(H)/state $(H)/runs && echo "state removed"

clean: clean-worktrees clean-state  ## delete worktrees and run state
	@rm -f $(H)/results-*.json $(H)/results-*.md
	@echo "results removed (venv kept - use clean-venv to drop it)"

clean-venv:               ## delete the venv too (slow to rebuild)
	$(no-run-in-flight)
	@rm -rf .venv && echo "venv removed - run make setup"
