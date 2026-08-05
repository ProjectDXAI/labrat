.PHONY: install install-nlp-sentiment smoke smoke-transformer smoke-corpus clean-smoke clean-smoke-corpus test help

PYTHON ?= python
PROFILE ?= transformer-arch
SMOKE_LAB := _smoke_$(PROFILE)
CORPUS_LAB := _smoke_quant-finance-corpus

help:
	@echo "labrat Makefile targets:"
	@echo "  make install                    editable install with core runtime deps"
	@echo "  make install-nlp-sentiment      editable install with the bundled NLP example deps"
	@echo "  make smoke [PROFILE=<name>]   end-to-end smoke test for a profile (default: transformer-arch)"
	@echo "  make smoke-transformer        alias for 'make smoke PROFILE=transformer-arch'"
	@echo "  make smoke-corpus             end-to-end smoke test for the quant-finance-corpus profile"
	@echo "  make clean-smoke              remove the temporary smoke lab"
	@echo "  make test                     alias for 'make smoke' + 'make smoke-corpus'"

install:
	@$(PYTHON) -m pip install -e .

install-nlp-sentiment:
	@$(PYTHON) -m pip install -e '.[nlp-sentiment]'

test: smoke smoke-corpus

smoke-transformer:
	@$(MAKE) smoke PROFILE=transformer-arch

clean-smoke:
	@rm -rf $(SMOKE_LAB)

clean-smoke-corpus:
	@rm -rf $(CORPUS_LAB)

smoke-corpus: clean-smoke-corpus
	@echo ">>> Scaffolding quant-finance-corpus lab at $(CORPUS_LAB)..."
	@$(PYTHON) scripts/new_lab.py $(CORPUS_LAB) --profile=quant-finance-corpus > /dev/null
	@echo ">>> Running doctor preflight and Phase 0 readiness..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/operator_helper.py doctor > /dev/null
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/operator_helper.py check-readiness > /dev/null
	@echo ">>> Validating the seed bibliography..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py validate | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok'], d['errors']; assert d['entry_count'] > 100, f'thin seed: {d[\"entry_count\"]}'; print(f'  validate OK: {d[\"entry_count\"]} entries')"
	@echo ">>> Checking the rights gate holds at seed (nothing confirmed => nothing eligible)..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py status --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['pages_manifest_eligible']==0, f'seed should clear nothing, got {d[\"pages_manifest_eligible\"]}'; assert d['frontier_open']>0, 'seed frontier is empty'; print(f'  gate OK: 0 eligible pages, {d[\"frontier_open\"]} frontier targets, {d[\"bridges\"]} bridges')"
	@echo ">>> Opening an expansion round..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py round open --mode expand --bucket market_microstructure --limit 5 > /dev/null && \
		test -f corpus/rounds/round-001/request.md || (echo "ERROR: round brief missing" && exit 1)
	@cd $(CORPUS_LAB) && printf 'round: 1\nentries:\n  - title: "Optimal Dealer Pricing under Transactions and Return Uncertainty"\n    authors: [Thomas Ho, Hans R. Stoll]\n    year: 1981\n    bucket: market_microstructure\n    form: paper\n    pages: 33\n    priority: 5\n    rights: {status: subscription_required, confidence: confirmed, evidence: "https://example.invalid/terms", checked_at: "2026-01-01"}\n    resolves: ["Ho & Stoll — Optimal dealer pricing under transactions and return uncertainty"]\n    refs:\n      - {target: zipkin-2000-foundations-inventory-management, relation: syllabus_with}\n  - id: mit-ocw-6262-discrete-stochastic-processes\n    rights: {status: cc_by_nc_sa, confidence: confirmed, evidence: "https://example.invalid/ocw", checked_at: "2026-01-01"}\n' > corpus/rounds/round-001/findings.yaml
	@echo ">>> Closing the round (merge, dedupe, frontier resolution)..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py round close | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['new_entries']==1, f'expected 1 new entry, got {d[\"new_entries\"]}'; assert d['updated']==1, f'expected 1 dedupe-merged update, got {d[\"updated\"]}'; assert d['frontier_resolved']>=1, 'frontier target was not closed'; assert d['eligible_pages_delta']>0, 'confirmed open licence did not clear any pages'; print(f'  merge OK: +{d[\"new_entries\"]} entry, {d[\"frontier_resolved\"]} frontier closed, +{d[\"eligible_pages_delta\"]} eligible pages')"
	@echo ">>> Verifying the manifest admits only confirmed-with-evidence entries..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py manifest | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['include']==1, f'expected exactly the CC-licensed entry, got {d[\"include\"]}'; assert d['hold']>100, 'hold list looks wrong'; print(f'  manifest OK: {d[\"include\"]} included, {d[\"hold\"]} held')"
	@cd $(CORPUS_LAB) && $(PYTHON) -c "import json; d=json.load(open('corpus/manifest.json')); row=[r for r in d['hold'] if r['id']=='harris-2003-trading-exchanges'][0]; assert row['use_class']=='reference_only', row; print('  reference_only path OK: commercial textbook held out of the manifest')"
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py report > /dev/null && $(PYTHON) scripts/corpus.py graph > /dev/null && test -f corpus/REPORT.md && test -f corpus/graph.json
	@echo ">>> Bootstrapping the runtime..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/bootstrap.py > /dev/null
	@echo ">>> Running one candidate through both phases (awaiting_findings, then scored)..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/runtime.py lease --worker-id cpu-1 > /tmp/_smoke_corpus_lease.json && \
		CID=$$($(PYTHON) -c "import json; print(json.load(open('/tmp/_smoke_corpus_lease.json'))['candidate_id'])") && \
		DIR=$$($(PYTHON) -c "import json; print(json.load(open('/tmp/_smoke_corpus_lease.json'))['artifact_dir'])") && \
		$(PYTHON) scripts/run_experiment.py --candidate "$$DIR/candidate.json" --output "$$DIR/result.json" && \
		$(PYTHON) -c "import json,sys; d=json.load(open('$$DIR/result.json')); assert d['failure_class']=='awaiting_findings', d; assert not d['valid']; print('  phase 1 OK: round opened, awaiting findings')" && \
		ROUND=$$($(PYTHON) -c "import json; print(json.load(open('$$DIR/corpus_round.json'))['round'])") && \
		printf 'round: 2\nentries:\n  - title: "A Smoke Test Monograph on Order Book Queues"\n    authors: [Smoke Tester]\n    year: 2026\n    bucket: queueing_networks\n    form: monograph\n    pages: 120\n    priority: 3\n    rights: {status: unknown, confidence: unknown}\n    refs:\n      - {target: harris-2003-trading-exchanges, relation: cites}\n' > corpus/rounds/round-00$$ROUND/findings.yaml && \
		$(PYTHON) scripts/run_experiment.py --candidate "$$DIR/candidate.json" --output "$$DIR/result.json" && \
		$(PYTHON) -c "import json; d=json.load(open('$$DIR/result.json')); assert d['valid'], d; assert d['proxy_metrics']['new_entries']==1, d['proxy_metrics']; assert d['metrics']['search']['primary_metric']>0, d['metrics']; print('  phase 2 OK: round merged and scored')" && \
		$(PYTHON) scripts/runtime.py complete --candidate-id "$$CID" --result "$$DIR/result.json" --worker-id cpu-1 > /dev/null && \
		echo "  complete OK"
	@echo ">>> Verifying corpus operator surfaces shipped..."
	@test -f $(CORPUS_LAB)/scripts/corpus.py || (echo "ERROR: corpus engine missing from lab" && exit 1)
	@test -f $(CORPUS_LAB)/corpus/bibliography.yaml || (echo "ERROR: seed bibliography missing" && exit 1)
	@test -f $(CORPUS_LAB)/corpus/taxonomy.yaml || (echo "ERROR: taxonomy missing" && exit 1)
	@test -f $(CORPUS_LAB)/.claude/commands/corpus-round.md || (echo "ERROR: /corpus-round command missing" && exit 1)
	@test -f $(CORPUS_LAB)/.claude/commands/corpus-status.md || (echo "ERROR: /corpus-status command missing" && exit 1)
	@test -f $(CORPUS_LAB)/.agents/skills/corpus-scout/SKILL.md || (echo "ERROR: Codex corpus-scout skill missing" && exit 1)
	@test -f $(CORPUS_LAB)/agent_prompts/shared/corpus_round.md || (echo "ERROR: shared corpus round prompt missing" && exit 1)
	@echo "  Claude commands + Codex skill + shared round prompt OK"
	@echo ""
	@echo ">>> smoke-corpus PASSED"
	@echo "    (lab left at $(CORPUS_LAB)/ for inspection; run 'make clean-smoke-corpus' to remove)"

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
	@echo ">>> Verifying agent ergonomics shipped..."
	@test -f $(SMOKE_LAB)/CLAUDE.md || (echo "ERROR: CLAUDE.md missing from lab root" && exit 1)
	@test -f $(SMOKE_LAB)/AGENTS.md || (echo "ERROR: AGENTS.md missing from lab root" && exit 1)
	@test -f $(SMOKE_LAB)/.agents/skills/labrat-operator/SKILL.md || (echo "ERROR: Codex labrat-operator skill missing from lab root" && exit 1)
	@test -d $(SMOKE_LAB)/.claude/commands || (echo "ERROR: .claude/commands missing from lab root" && exit 1)
	@test -d $(SMOKE_LAB)/agent_prompts || (echo "ERROR: agent_prompts missing from lab root" && exit 1)
	@test -f $(SMOKE_LAB)/coordination/workspace_map.md || (echo "ERROR: coordination/workspace_map.md missing" && exit 1)
	@test -f $(SMOKE_LAB)/coordination/prioritized_tasks.md || (echo "ERROR: coordination/prioritized_tasks.md missing" && exit 1)
	@echo "  AGENTS.md + .agents/skills + CLAUDE.md + .claude/commands + agent_prompts + coordination seeds OK"
	@echo ""
	@echo ">>> smoke PROFILE=$(PROFILE) PASSED"
	@echo "    (lab left at $(SMOKE_LAB)/ for inspection; run 'make clean-smoke' to remove)"
