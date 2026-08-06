.PHONY: install install-nlp-sentiment smoke smoke-transformer smoke-corpus smoke-knowledge clean-smoke clean-smoke-corpus clean-smoke-knowledge test help web web-data

PYTHON ?= python
PROFILE ?= transformer-arch
SMOKE_LAB := _smoke_$(PROFILE)
CORPUS_LAB := _smoke_quant-finance-corpus
KNOWLEDGE_LAB := _smoke_dxap-knowledge

help:
	@echo "labrat Makefile targets:"
	@echo "  make install                    editable install with core runtime deps"
	@echo "  make install-nlp-sentiment      editable install with the bundled NLP example deps"
	@echo "  make smoke [PROFILE=<name>]   end-to-end smoke test for a profile (default: transformer-arch)"
	@echo "  make smoke-transformer        alias for 'make smoke PROFILE=transformer-arch'"
	@echo "  make smoke-corpus             end-to-end smoke test for the quant-finance-corpus profile"
	@echo "  make smoke-knowledge          end-to-end smoke test for the dxap-knowledge profile"
	@echo "  make clean-smoke              remove the temporary smoke lab"
	@echo "  make test                     runs every smoke path and self-test"
	@echo "  make web-data [LAB=dir]       export the corpus bundle the explorer reads"
	@echo "  make web                      export, then run the explorer at localhost:3000"

install:
	@$(PYTHON) -m pip install -e .

install-nlp-sentiment:
	@$(PYTHON) -m pip install -e '.[nlp-sentiment]'

test: selftest smoke smoke-corpus smoke-knowledge

smoke-transformer:
	@$(MAKE) smoke PROFILE=transformer-arch

clean-smoke:
	@rm -rf $(SMOKE_LAB)

clean-smoke-corpus:
	@rm -rf $(CORPUS_LAB)

clean-smoke-knowledge:
	@rm -rf $(KNOWLEDGE_LAB)

selftest:
	@echo ">>> Engine self-tests (graph algorithms, deterministic methods, attribution ledger)..."
	@$(PYTHON) scripts/graphops.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  graphops OK: {len(d[\"checks\"])} checks')"
	@$(PYTHON) scripts/methods.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  methods OK: {d[\"methods\"]} methods, {len(d[\"checks\"])} closed-form checks')"
	@$(PYTHON) scripts/ledger.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  ledger OK: {len(d[\"checks\"])} checks')"
	@$(PYTHON) scripts/corpus.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  corpus engine OK: {len(d[\"checks\"])} checks')"
	@$(PYTHON) scripts/knowledge.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  knowledge engine OK: {len(d[\"checks\"])} checks')"
	@$(PYTHON) scripts/resolve.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  resolver OK: {len(d[\"checks\"])} checks')"
	@$(PYTHON) scripts/passages.py self-test | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok']; print(f'  passage layer OK: {len(d[\"checks\"])} checks')"

smoke-knowledge: clean-smoke-knowledge selftest
	@echo ">>> Scaffolding stacked corpus + knowledge lab at $(KNOWLEDGE_LAB)..."
	@$(PYTHON) scripts/new_lab.py $(KNOWLEDGE_LAB) --profile=quant-finance-corpus --profile=dxap-knowledge > /dev/null
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/operator_helper.py doctor > /dev/null
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/operator_helper.py check-readiness > /dev/null
	@echo ">>> Running the SERVABLE gate over every card..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py validate --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok'], [r for r in d['concepts'] if not r['servable']]; c=d['counts']; assert c['servable_concepts']==c['concepts'], c; assert c['testable_hypotheses']==c['hypotheses'], c; print(f'  gate OK: {c[\"concepts\"]} concepts servable, {c[\"hypotheses\"]} hypotheses testable, {c[\"methods\"]} method bindings at pinned versions')"
	@echo ">>> Checking every diagnosed problem has a servable concept..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py status --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert not d['problems_uncovered'], f'problems with no servable concept: {d[\"problems_uncovered\"]}'; grounded=len(d['cards_anchored_to_read_units']); print(f'  coverage OK: {len(d[\"concepts_by_problem\"])} problems all covered, {grounded}/{d[\"counts\"][\"concepts\"]} cards on units someone opened')"
	@echo ">>> Checking a card cannot claim an implementation that is not bound..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys; sys.path.insert(0,'scripts'); import yaml, knowledge; p=knowledge.knowledge_paths(__import__('pathlib').Path('knowledge')); s=knowledge.load_store(p); src=knowledge.load_corpus_sources(__import__('pathlib').Path('.')); s['methods']=[]; bad=[r for r in (knowledge.concept_gate(c,src,s) for c in s['concepts']) if not r['servable']]; assert bad, 'removing every method binding should unservable the implemented cards'; print(f'  version/binding gate OK: {len(bad)} cards refuse to serve without their bound method')"
	@echo ">>> Checking the rights gate blocks a quote from a reference-only source..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys, pathlib; sys.path.insert(0,'scripts'); import knowledge; p=knowledge.knowledge_paths(pathlib.Path('knowledge')); s=knowledge.load_store(p); src=knowledge.load_corpus_sources(pathlib.Path('.')); c=dict(s['concepts'][0]); c['source_passage_ids']=[{'source_id':'harris-2003-trading-exchanges','anchor':'ch5','quote':'verbatim text'}]; r=knowledge.concept_gate(c,src,s); assert not r['servable'] and any('verbatim' in e for e in r['errors']), r; print('  rights gate OK: verbatim quote from a reference-only source is refused')"
	@echo ">>> Scoring the retrieval policies against the labelled trials..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py evaluate --json | $(PYTHON) -c "import json,sys; rows={r['policy']:r for r in json.load(sys.stdin)}; raw=rows['raw_similarity']; dv=rows['decision_value']; assert raw['non_applicability_accuracy']==0.0, raw; assert dv['non_applicability_accuracy']==1.0, dv; assert dv['precision']>raw['precision'], (dv['precision'],raw['precision']); assert dv['counterevidence_coverage']>raw['counterevidence_coverage'], (dv,raw); assert dv['mean_context_kilotokens']<raw['mean_context_kilotokens'], (dv,raw); print(f'  retrieval OK: raw similarity prec={raw[\"precision\"]:.2f} abstains={raw[\"non_applicability_accuracy\"]:.2f}; decision value prec={dv[\"precision\"]:.2f} abstains={dv[\"non_applicability_accuracy\"]:.2f} counter={dv[\"counterevidence_coverage\"]:.2f}')"
	@echo ">>> Checking point-in-time retrieval refuses sources published after the decision..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py evaluate --policy decision_value --json | $(PYTHON) -c "import json,sys; rows=json.load(sys.stdin)[0]['rows']; r=[x for x in rows if x['trial_id']=='T-NEG-BEFORE-SOURCES'][0]; assert r['abstained'], r; print('  point-in-time OK: a 1975 decision retrieves nothing from sources written later')"
	@echo ">>> Stress-testing the policies under perturbation..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py stress --json | $(PYTHON) -c "import json,sys; rows={r['policy']:r for r in json.load(sys.stdin)}; raw=rows['raw_similarity']; dv=rows['decision_value']; assert raw['integrity_violations']>0, 'unfiltered retrieval should serve cards it cannot compute'; assert dv['integrity_violations']==0, dv; assert dv['robustness']>raw['robustness'], (dv['robustness'],raw['robustness']); assert rows['conservative_abstain']['perturbations']['tool_loss']['retention']<0.5, 'over-cautious policy should switch itself off when tools vanish'; print(f'  stress OK: decision value robustness={dv[\"robustness\"]:.2f} with 0 violations; raw similarity={raw[\"robustness\"]:.2f} with {raw[\"integrity_violations\"]} violations')"
	@echo ">>> Budgeting source text against the three digest arms..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/make_digest_fixture.py
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py digest --context .digest-ctx.json --compare --budget 1200 --abstain-threshold 0.01 | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); a=d['arms']; assert a['never']['tokens_used']<a['policy']['tokens_used']<a['always']['tokens_used'], f'the three arms must actually differ: {a}'; assert not a['policy']['over_budget'], a['policy']; assert a['always']['tokens_used']>1200, 'the unbounded arm should blow the budget the policy respects'; assert a['policy']['by_tier']['excerpt']>0, a['policy']; print(f'  digest OK: never={a[\"never\"][\"tokens_used\"]} policy={a[\"policy\"][\"tokens_used\"]} always={a[\"always\"][\"tokens_used\"]} tokens; policy holds the 1200 ceiling the unbounded arm breaks')"
	@echo ">>> Checking a rights ceiling outranks every escalation trigger..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py digest --context .digest-ctx.json --budget 999999 --arm always --abstain-threshold 0.01 | $(PYTHON) -c "import json,sys; sys.path.insert(0,'scripts'); from digest import TIER_ORDER as T; d=json.load(sys.stdin); over=[r for r in d['passages'] if T.index(r['tier'])>T.index(r['rights_ceiling'])]; assert not over, over; print(f'  ceiling OK: {len(d[\"passages\"])} anchors served, none above its licence even with an unbounded budget')"
	@echo ">>> Checking the whole source arrives only when asked for by name..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py digest --context .digest-ctx.json --budget 999999 --abstain-threshold 0.01 | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert not d['full_text_served'], f'no --full was passed and a whole source arrived anyway: {d[\"full_text_served\"]}'; print('  opt-in OK: an ingestable source stays at excerpt until someone asks for it')"
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py digest --context .digest-ctx.json --budget 999999 --abstain-threshold 0.01 --full he-2022-fundamentals-perpetual-futures | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); served=d['full_text_served']; assert served==['he-2022-fundamentals-perpetual-futures'], served; texts=[r['text'] for r in d['passages'] if r['text']]; assert len(texts)==len(set(texts)), 'the same passage was served more than once'; print(f'  full source OK: {d[\"tokens_used\"]:,} tokens, every passage distinct')"
	@cd $(KNOWLEDGE_LAB) && rm -f .digest-ctx.json && rm -rf corpus/passages
	@echo ">>> Checking the frontier bets are refutable, grounded and runnable..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py bets --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); v=d['validation']; assert v['ok'], [r for r in v['bets'] if not r['ok']]; runnable=sum(1 for r in v['bets'] if r['runnable_now']); assert runnable>=4, runnable; top=d['ranked'][0]; assert top['first_computation'], 'the top-ranked bet must be runnable today'; print(f'  bets OK: {v[\"count\"]} refutable bets, {runnable} runnable now, top = {top[\"bet_id\"]} via {top[\"first_computation\"]}')"
	@echo ">>> Checking proposed extensions are grounded in material actually read..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py extensions --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); v=d['validation']; assert v['ok'], [r for r in v['extensions'] if not r['ok']]; assert v['units_read']>=6, v['units_read']; assert all(r['read_groundings'] for r in v['extensions']), 'every extension must cite a unit someone opened'; print(f'  extensions OK: {v[\"count\"]} proposals, all grounded in {v[\"units_read\"]} units marked read')"
	@echo ">>> Checking the read-grounding rule actually refuses ungrounded work..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys, pathlib; sys.path.insert(0,'scripts'); import knowledge; p=knowledge.knowledge_paths(pathlib.Path('knowledge')); s=knowledge.load_store(p); src=knowledge.load_corpus_sources(pathlib.Path('.')); e=dict(s['extensions'][0]); e['grounded_in']=['harris-2003-trading-exchanges#order-types-and-mechanics']; r=knowledge.validate_extensions({**s,'extensions':[e]}, src); assert not r['ok'] and any('not grounded' in m for m in r['extensions'][0]['errors']), r; print('  grounding gate OK: an extension citing an unread unit is refused')"
	@echo ">>> Running the top two frontier probes end to end..."
	@cd $(KNOWLEDGE_LAB) && printf '{"counts": [40,160,40,160,40,160,40,160,40,160,40,160,40,160,40,160,40,160,40,160,40,160,40,160]}' > /tmp/_probe.json && \
		$(PYTHON) scripts/methods.py run --method hawkes_branching_ratio --input /tmp/_probe.json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin)['result']; assert d['regime'] in {'endogenous','near_critical'}, d; print(f'  criticality probe OK: n={d[\"branching_ratio\"]:.2f} regime={d[\"regime\"]}')"
	@cd $(KNOWLEDGE_LAB) && printf '{"markets": {"a": 0.6, "b": 0.7, "a_and_b": 0.15}, "conjunctions": [{"a": "a", "b": "b", "market": "a_and_b"}], "cost": 0.02}' > /tmp/_probe2.json && \
		$(PYTHON) scripts/methods.py run --method prediction_market_consistency --input /tmp/_probe2.json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin)['result']; assert d['tradable'], d; print(f'  joint-bounds probe OK: {len(d[\"tradable\"])} cost-surviving violation, max gap {d[\"max_gap\"]:.2f}')"
	@echo ">>> Running the workstream probes end to end..."
	@cd $(KNOWLEDGE_LAB) && printf '{"actions": [{"action_id": "aggressor", "kind": "order", "tif": "ioc", "arrival_index": 0, "proposer_index": 0}, {"action_id": "our_cancel", "kind": "cancel", "arrival_index": 1, "proposer_index": 1}], "own_action_id": "our_cancel"}' > /tmp/_probe3.json && \
		$(PYTHON) scripts/methods.py run --method batch_priority_fill --input /tmp/_probe3.json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin)['result']; assert d['execution_order']==['our_cancel','aggressor'], d; assert len(d['escaped_cancels'])==1, d; print('  batch-priority probe OK: a cancel sent after an aggressive order still lands first')"
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys, json; sys.path.insert(0,'scripts'); import methods; tree=methods.event_tree_constraints([{'market_id':f'm{i}','event_id':'e1','negative_risk':True} for i in range(1,4)]); out=methods.prediction_market_consistency(markets={'m1':0.5,'m2':0.4,'m3':0.3}, partitions=tree['enforced'], settlement='atomic'); assert tree['enforced'] and out['tradable'], (tree,out); print(f'  event-tree probe OK: partition derived from metadata, breach of {out[\"max_gap\"]:.2f} clears the atomic hurdle')"
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys; sys.path.insert(0,'scripts'); import methods; r=methods.betting_eprocess([1.0]*12, null_mean=0.5, lambda_fixed=1.0, grid=0); assert r['crossed_at']==8, r; flat=methods.betting_eprocess([0.5]*60, null_mean=0.5); assert not flat['rejected'] and flat['confidence_sequence'][0] <= 0.5 <= flat['confidence_sequence'][1], flat; print(f'  anytime probe OK: crosses at observation {r[\"crossed_at\"]} under a real effect, interval holds 0.5 under none')"
	@echo ">>> Checking a venue-specific card does not leak to a venue where it is false..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py evaluate --policy decision_value --json | $(PYTHON) -c "import json,sys; rows=json.load(sys.stdin)[0]['rows']; r=[x for x in rows if x['trial_id']=='T-NEG-BATCH-ON-CONTINUOUS'][0]; assert r['abstained'], r; print('  venue scoping OK: the batch-priority card stays out of a continuous-matching context')"
	@echo ">>> Checking the analysis brief assembles and holds the rights line..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys, pathlib; sys.path.insert(0,'scripts'); import passages; b=passages.analysis_brief(pathlib.Path('.'), 'queue position and adverse selection on a batching venue'); ids=[c['concept_id'] for c in b['compiled_concepts']]; assert 'KC-BATCH-PRIORITY' in ids and 'KC-MICRO-QUEUE' in ids, ids; assert any(c['contradicted_by'] for c in b['compiled_concepts']), 'the brief must surface the contradiction'; assert b['what_would_change_the_answer'], 'a brief with no falsifiers is an opinion'; print(f'  brief OK: {len(ids)} concepts, contradiction surfaced, {len(b[\"what_would_change_the_answer\"])} falsifiers')"
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys; sys.path.insert(0,'scripts'); import passages; row={'passage_id':'x','entry_id':'e','file':'f.pdf','page':3,'use_class':'reference_only','rights_status':'all_rights_reserved','text':'secret text '*40}; gated=passages.emit_passage(row,{'secret':40},False); assert 'snippet' not in gated and gated['read_it_at']=='f.pdf p.3', gated; opened=passages.emit_passage(row,{'secret':40},True); assert opened['snippet'] and not opened['quotable'], opened; print('  passage rights gate OK: locator always, text only under licence or an explicit local override')"
	@echo ">>> Reading the whole store at once..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py assess | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert not d['orphan_methods'], d['orphan_methods']; assert not d['concepts_without_problem'], d['concepts_without_problem']; assert not d['contradiction']['uncountered_concepts'], d['contradiction']['uncountered_concepts']; assert not d['unread_single_points'], [r['anchor'] for r in d['unread_single_points']]; assert len(d['contradiction']['clusters'])>=5, d['contradiction']['clusters']; print(f'  assess OK: {len(d[\"contradiction\"][\"pairs\"])} contradiction pairs in {len(d[\"contradiction\"][\"clusters\"])} clusters, {len(d[\"complete_chain_problems\"])} problems with a complete chain, no unread anchor carrying two or more cards')"
	@echo ">>> Ranking what to compile next..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/knowledge.py compile-queue --limit 10 --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ranked'], d; assert d['queues']['human_foundation_spine'], 'spine queue empty'; assert d['minimum_problem_cover']['selected'], 'no problem cover'; print(f'  compile queue OK: {len(d[\"ranked\"])} ranked, minimum cover of {len(d[\"minimum_problem_cover\"][\"covered\"])} problems from {len(d[\"minimum_problem_cover\"][\"selected\"])} sources')"
	@echo ">>> Bootstrapping and running one policy candidate end-to-end..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/bootstrap.py > /dev/null
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) scripts/runtime.py lease --worker-id cpu-1 > /tmp/_smoke_knowledge_lease.json && \
		CID=$$($(PYTHON) -c "import json; print(json.load(open('/tmp/_smoke_knowledge_lease.json'))['candidate_id'])") && \
		DIR=$$($(PYTHON) -c "import json; print(json.load(open('/tmp/_smoke_knowledge_lease.json'))['artifact_dir'])") && \
		$(PYTHON) scripts/run_experiment.py --candidate "$$DIR/candidate.json" --output "$$DIR/result.json" && \
		$(PYTHON) -c "import json; d=json.load(open('$$DIR/result.json')); assert d['valid'], d; assert d['proxy_metrics']['methods_self_test_ok'], d; assert d['metrics']['search']['primary_metric']>0, d; print('  candidate OK: policy scored on the trial set')" && \
		$(PYTHON) scripts/runtime.py complete --candidate-id "$$CID" --result "$$DIR/result.json" --worker-id cpu-1 > /dev/null && \
		echo "  complete OK"
	@echo ">>> Checking the ledger refuses an effect estimate on an unfrozen batch..."
	@cd $(KNOWLEDGE_LAB) && $(PYTHON) -c "import sys; sys.path.insert(0,'scripts'); import ledger; e=[dict(x, frozen_batch=False) if x['event_type']=='outcome' else x for x in ledger._synthetic_events()]; r=ledger.analyze(e); assert r.get('refused'), r; ok=ledger.analyze(ledger._synthetic_events()); assert not ok.get('refused') and ok['comparisons']['treatment']['difference']==16.0, ok; print('  ledger OK: refuses unfrozen batches, computes clustered effects on matured ones')"
	@echo ">>> Verifying knowledge operator surfaces shipped..."
	@for f in scripts/knowledge.py scripts/methods.py scripts/graphops.py scripts/ledger.py knowledge/concepts.yaml knowledge/trials.yaml .claude/commands/compile-concept.md .claude/commands/evidence-packet.md .agents/skills/knowledge-compiler/SKILL.md agent_prompts/shared/knowledge_compile.md; do \
		test -f $(KNOWLEDGE_LAB)/$$f || (echo "ERROR: $$f missing from lab" && exit 1); \
	done
	@echo "  Claude commands + Codex skill + shared compile prompt + engines OK"
	@echo ""
	@echo ">>> smoke-knowledge PASSED"
	@echo "    (lab left at $(KNOWLEDGE_LAB)/ for inspection; run 'make clean-smoke-knowledge' to remove)"

smoke-corpus: clean-smoke-corpus selftest
	@echo ">>> Scaffolding quant-finance-corpus lab at $(CORPUS_LAB)..."
	@$(PYTHON) scripts/new_lab.py $(CORPUS_LAB) --profile=quant-finance-corpus > /dev/null
	@echo ">>> Running doctor preflight and Phase 0 readiness..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/operator_helper.py doctor > /dev/null
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/operator_helper.py check-readiness > /dev/null
	@echo ">>> Validating the seed bibliography..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py validate | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['ok'], d['errors']; assert d['entry_count'] > 100, f'thin seed: {d[\"entry_count\"]}'; print(f'  validate OK: {d[\"entry_count\"]} entries')"
	@echo ">>> Checking the rights gate holds at seed (evidence, or it does not clear)..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py manifest > /dev/null && $(PYTHON) -c "import json; d=json.load(open('corpus/manifest.json')); bad=[r['id'] for r in d['include'] if not (r.get('evidence') and r.get('checked_at'))]; assert not bad, f'eligible without evidence or a check date: {bad}'; assert d['include_count']>0, 'nothing cleared at all'; print(f'  gate OK: {d[\"include_count\"]} eligible, every one with an evidence URL and a check date; {d[\"hold_count\"]} held')"
	@cd $(CORPUS_LAB) && $(PYTHON) -c "import json, yaml; m=json.load(open('corpus/manifest.json')); b={e['id']: e for e in yaml.safe_load(open('corpus/bibliography.yaml'))['entries']}; inferred=[r['id'] for r in m['include'] if (b[r['id']].get('rights') or {}).get('confidence')!='confirmed']; assert not inferred, f'inferred rights reached the manifest: {inferred}'; print('  confirm gate OK: no inferred rights tag reaches the manifest')"
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py status --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['frontier_open']>0, 'seed frontier is empty'; print(f'  network OK: {d[\"frontier_open\"]} frontier targets, {d[\"bridges\"]} bridges')"
	@echo ">>> Opening an expansion round..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py round open --mode expand --limit 5 > /dev/null && \
		test -f corpus/rounds/round-001/request.md || (echo "ERROR: round brief missing" && exit 1)
	@cd $(CORPUS_LAB) && $(PYTHON) -c "import json, subprocess, sys; run=lambda *a: json.loads(subprocess.run([sys.executable,'scripts/corpus.py',*a],capture_output=True,text=True).stdout); front=run('frontier','--limit','1','--json'); queue=run('rights','--verify-queue','--limit','1','--json'); assert front and queue, 'seed frontier or verify queue is empty'; row=front[0]; target=queue[0]; json.dump({'round':1,'entries':[{'title':'Smoke Fixture: A Companion Volume','authors':['Smoke Tester'],'year':2026,'bucket':row.get('suggested_bucket') or 'market_microstructure','form':'monograph','pages':120,'priority':5,'rights':{'status':'subscription_required','confidence':'confirmed','evidence':'https://example.invalid/terms','checked_at':'2026-01-01'},'resolves':[row['label']],'refs':[{'target':'zipkin-2000-foundations-inventory-management','relation':'syllabus_with'}]},{'id':target['id'],'rights':{'status':'cc_by_nc_sa','confidence':'confirmed','evidence':'https://example.invalid/ocw','checked_at':'2026-01-01'}}]}, open('corpus/rounds/round-001/findings.yaml','w')); print('  fixture resolves: ' + row['label'][:46] + ' | clears: ' + target['id'][:34])"
	@echo ">>> Closing the round (merge, dedupe, frontier resolution)..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py round close | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['new_entries']==1, f'expected 1 new entry, got {d[\"new_entries\"]}'; assert d['updated']==1, f'expected 1 dedupe-merged update, got {d[\"updated\"]}'; assert d['frontier_resolved']>=1, 'frontier target was not closed'; assert d['eligible_pages_delta']>0, 'confirmed open licence did not clear any pages'; print(f'  merge OK: +{d[\"new_entries\"]} entry, {d[\"frontier_resolved\"]} frontier closed, +{d[\"eligible_pages_delta\"]} eligible pages')"
	@echo ">>> Verifying the manifest admits only confirmed-with-evidence entries..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py manifest | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['include']>=2, f'the confirmed licence did not clear anything: {d[\"include\"]}'; assert 'ingest_noncommercial' in d['by_use_class'], d['by_use_class']; assert d['hold']>100, 'hold list looks wrong'; print(f'  manifest OK: {d[\"include\"]} included ({d[\"by_use_class\"]}), {d[\"hold\"]} held')"
	@cd $(CORPUS_LAB) && $(PYTHON) -c "import json; d=json.load(open('corpus/manifest.json')); row=[r for r in d['hold'] if r['id']=='harris-2003-trading-exchanges'][0]; assert row['use_class']=='reference_only', row; print('  reference_only path OK: commercial textbook held out of the manifest')"
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py report > /dev/null && $(PYTHON) scripts/corpus.py graph > /dev/null && test -f corpus/REPORT.md && test -f corpus/graph.json
	@echo ">>> Checking the chapter-level reading queue..."
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py reading --limit 5 --json | $(PYTHON) -c "import json,sys; rows=json.load(sys.stdin); assert rows, 'reading queue empty'; assert all(r['unit_id']!='whole' for r in rows), 'queue should be at unit granularity'; print(f'  reading queue OK: {len(rows)} units, top target {rows[0][\"entry_id\"]}/{rows[0][\"unit_id\"]}')"
	@cd $(CORPUS_LAB) && $(PYTHON) scripts/corpus.py status --json | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d['units_declared']>=40, d['units_declared']; assert d['sources_not_decomposed']>0, 'expected undecomposed sources to be visible'; print(f'  decomposition OK: {d[\"sources_decomposed\"]} sources into {d[\"units_declared\"]} units, {d[\"sources_not_decomposed\"]} still whole-book')"
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

LAB ?= corpus-lab

web-data:
	@test -f $(LAB)/corpus/bibliography.yaml || (echo "ERROR: no corpus at $(LAB). Scaffold one: python scripts/new_lab.py $(LAB) --profile=quant-finance-corpus --profile=dxap-knowledge" && exit 1)
	@$(PYTHON) scripts/export_web.py --lab $(LAB) --out web/public/corpus.json

web: web-data
	@test -d web/node_modules || (cd web && npm install)
	@echo ">>> explorer on http://localhost:3000"
	@cd web && npm run dev
