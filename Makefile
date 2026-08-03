.PHONY: help setup doctor instances pilot run status report clean clean-worktrees clean-state
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

status:                   ## snapshot the current run (safe from another shell)
	@cd $(H) && $(PY) render.py

report:                   ## write results.md + results.json
	@cd $(H) && $(PY) report.py

clean-worktrees:          ## delete extracted worktrees only
	@rm -rf pytest-worktrees && echo "worktrees removed"

clean-state:              ## delete run state and logs (keeps instances.jsonl)
	@rm -rf $(H)/state $(H)/runs && echo "state removed"

clean: clean-worktrees clean-state  ## delete worktrees, state and venv
	@rm -rf .venv && echo "venv removed"
