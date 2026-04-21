.PHONY: install install-nlp-sentiment smoke smoke-transformer clean-smoke test help

PYTHON ?= python
PROFILE ?= transformer-arch
SMOKE_LAB := _smoke_$(PROFILE)

help:
	@echo "labrat Makefile targets:"
	@echo "  make install                    editable install with core runtime deps"
	@echo "  make install-nlp-sentiment      editable install with the bundled NLP example deps"
	@echo "  make smoke [PROFILE=<name>]   end-to-end smoke test for a profile (default: transformer-arch)"
	@echo "  make smoke-transformer        alias for 'make smoke PROFILE=transformer-arch'"
	@echo "  make clean-smoke              remove the temporary smoke lab"
	@echo "  make test                     alias for 'make smoke'"

install:
	@$(PYTHON) -m pip install -e .

install-nlp-sentiment:
	@$(PYTHON) -m pip install -e '.[nlp-sentiment]'

test: smoke

smoke-transformer:
	@$(MAKE) smoke PROFILE=transformer-arch

clean-smoke:
	@rm -rf $(SMOKE_LAB)

smoke: clean-smoke
	@echo ">>> Scaffolding $(PROFILE) lab at $(SMOKE_LAB)..."
	@$(PYTHON) scripts/new_lab.py $(SMOKE_LAB) --profile=$(PROFILE) > /dev/null
	@echo ">>> Running doctor preflight..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/operator_helper.py doctor > /dev/null
	@echo ">>> Verifying Phase 0 readiness..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/operator_helper.py check-readiness
	@echo ">>> Verifying synthetic run_experiment.py (should be < 1s)..."
	@cd $(SMOKE_LAB) && mkdir -p experiments/_smoke/c0 && \
		printf '{"candidate_id":"c0","family":"scale_search","operator_type":"probe","resolved_config":{"data":{"train_path":"data/train_corpus.txt","holdout_path":"data/holdout_corpus.txt","block_size":32},"model":{"depth":4,"heads":4,"d_model":64,"activation":"gelu","dropout":0.0},"training":{"steps":100,"lr":0.003,"batch_size":16,"warmup_steps":10,"seed":1337,"checkpoint_every":20}}}' > experiments/_smoke/c0/candidate.json && \
		$(PYTHON) scripts/run_experiment.py --candidate experiments/_smoke/c0/candidate.json --output experiments/_smoke/c0/result.json && \
		test -f experiments/_smoke/c0/checkpoints.jsonl
	@echo ">>> Verifying evaluator picks up checkpoints.jsonl and infers failure_class..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/evaluator.py --result experiments/_smoke/c0/result.json --config evaluation.yaml | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['checkpoint_summary']['trend']=='improving', f'expected improving trend, got {d[\"checkpoint_summary\"][\"trend\"]}'; assert d['failure_class'] is None, f'expected no failure_class for clean run, got {d[\"failure_class\"]}'; print('  evaluator OK: trend=improving failure_class=None')"
	@echo ">>> Simulating a NaN-collapse run..."
	@cd $(SMOKE_LAB) && mkdir -p experiments/_smoke/c_nan && \
		printf '{"candidate_id":"c_nan","family":"scale_search","operator_type":"mutation","resolved_config":{"data":{"train_path":"data/train_corpus.txt","holdout_path":"data/holdout_corpus.txt","block_size":32},"model":{"depth":4,"heads":4,"d_model":64,"activation":"gelu","dropout":0.0},"training":{"steps":200,"lr":0.015,"batch_size":16,"warmup_steps":0,"seed":42,"checkpoint_every":20}}}' > experiments/_smoke/c_nan/candidate.json && \
		$(PYTHON) scripts/run_experiment.py --candidate experiments/_smoke/c_nan/candidate.json --output experiments/_smoke/c_nan/result.json && \
		$(PYTHON) scripts/evaluator.py --result experiments/_smoke/c_nan/result.json --config evaluation.yaml | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['failure_class']=='nan', f'expected failure_class=nan, got {d[\"failure_class\"]}'; assert d['checkpoint_summary']['trend']=='collapsed', f'expected collapsed trend, got {d[\"checkpoint_summary\"][\"trend\"]}'; print('  NaN path OK: failure_class=nan trend=collapsed')"
	@echo ">>> Bootstrapping the runtime..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/bootstrap.py > /dev/null
	@cd $(SMOKE_LAB) && $(PYTHON) -c "import json; state=json.load(open('state/jobs.json')); assert len(state['queued'])>=2, f'expected >= 2 queued jobs, got {len(state[\"queued\"])}'; print(f'  bootstrap OK: {len(state[\"queued\"])} jobs queued')"
	@echo ">>> Running the first leased candidate end-to-end..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/runtime.py lease --worker-id cpu-1 > /tmp/_smoke_lease.json && \
		$(PYTHON) -c "import json; d=json.load(open('/tmp/_smoke_lease.json')); print(f'  leased {d[\"candidate_id\"]}')" && \
		CID=$$($(PYTHON) -c "import json; d=json.load(open('/tmp/_smoke_lease.json')); print(d['candidate_id'])") && \
		DIR=$$($(PYTHON) -c "import json; d=json.load(open('/tmp/_smoke_lease.json')); print(d['artifact_dir'])") && \
		$(PYTHON) scripts/run_experiment.py --candidate "$$DIR/candidate.json" --output "$$DIR/result.json" && \
		$(PYTHON) scripts/runtime.py complete --candidate-id "$$CID" --result "$$DIR/result.json" --worker-id cpu-1 > /dev/null && \
		echo "  complete OK"
	@echo ">>> Computing Pareto rank..."
	@cd $(SMOKE_LAB) && $(PYTHON) scripts/pareto.py --lab-dir . > /dev/null && \
		$(PYTHON) -c "import json; d=json.load(open('state/pareto.json')); assert d['enabled'], 'pareto should be enabled'; assert d['front_count']>=1, 'expected >= 1 front'; print(f'  pareto OK: {d[\"front_count\"]} fronts, {len(d[\"candidates\"])} candidates')"
	@echo ">>> Verifying Claude Code ergonomics shipped..."
	@test -f $(SMOKE_LAB)/CLAUDE.md || (echo "ERROR: CLAUDE.md missing from lab root" && exit 1)
	@test -f $(SMOKE_LAB)/AGENTS.md || (echo "ERROR: AGENTS.md missing from lab root" && exit 1)
	@test -d $(SMOKE_LAB)/.claude/commands || (echo "ERROR: .claude/commands missing from lab root" && exit 1)
	@test -d $(SMOKE_LAB)/agent_prompts || (echo "ERROR: agent_prompts missing from lab root" && exit 1)
	@test -f $(SMOKE_LAB)/coordination/workspace_map.md || (echo "ERROR: coordination/workspace_map.md missing" && exit 1)
	@test -f $(SMOKE_LAB)/coordination/prioritized_tasks.md || (echo "ERROR: coordination/prioritized_tasks.md missing" && exit 1)
	@echo "  AGENTS.md + CLAUDE.md + .claude/commands + agent_prompts + coordination seeds OK"
	@echo ""
	@echo ">>> smoke PROFILE=$(PROFILE) PASSED"
	@echo "    (lab left at $(SMOKE_LAB)/ for inspection; run 'make clean-smoke' to remove)"
