.PHONY: help setup doctor instances pilot run status report clean clean-worktrees clean-state
.DEFAULT_GOAL := help

H := harness
PY := python3
PILOT ?= 3
WORKERS ?=

help:                     ## show this help
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

setup:                    ## install everything and verify it works
	@bash $(H)/setup.sh

doctor:                   ## verify the environment, change nothing
	@bash $(H)/setup.sh doctor

instances:                ## mine PRs -> harness/instances.jsonl
	@bash $(H)/mine.sh
	@cd $(H) && $(PY) resolve.py /tmp/prs.jsonl instances.jsonl

pilot:                    ## run PILOT instances (default 3) with live status
	@cd $(H) && $(PY) orchestrate.py --limit $(PILOT) --fresh

run:                      ## run all instances with live status
	@cd $(H) && $(PY) orchestrate.py

ids:                      ## run specific PRs: make ids IDS=14493,14466
	@cd $(H) && $(PY) orchestrate.py --ids $(IDS) --fresh

compare:                  ## compare two models: make compare A=opus B=sonnet
	@cd $(H) && $(PY) compare.py $(or $(A),opus) $(or $(B),sonnet)

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
