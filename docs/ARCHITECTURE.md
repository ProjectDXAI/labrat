# labrat vNext Architecture

## Layers

1. **Problem scaffold**
   - `branches.yaml`
   - `dead_ends.md`
   - `research_brief.md`
   - `research_sources.md`
   - `evaluation.yaml`
   - `runtime.yaml`
2. **Runtime**
   - `scripts/runtime.py`
   - `state/runtime.json`
   - `state/jobs.json`
   - `state/workers.json`
   - `state/frontier.json`
3. **Artifacts**
   - `state/candidates.jsonl`
   - `state/evaluations.jsonl`
   - `experiments/<family>/<candidate>/`
   - `coordination/workspace_map.md`
   - `coordination/prioritized_tasks.md`
   - `coordination/implementation_log.md`
   - `coordination/experiment_log.md`
4. **Operator prompts**
   - `orchestrator.md`
   - worker prompts
   - audit / frame-break / expansion prompts
5. **UI**
   - static dashboard fed directly by runtime state

## Required scaffold surface

Every new lab is expected to define or generate:

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`
- `evaluation.yaml`
- `runtime.yaml`
- `coordination/workspace_map.md` after bootstrap
- `coordination/prioritized_tasks.md`
- `coordination/implementation_log.md`
- `coordination/experiment_log.md`
- `orchestrator.md`
- `probe_worker.md`
- `mutation_worker.md`
- `crossover_worker.md`
- `implementation_audit.md`
- `frame_break.md`
- `expansion_scout.md`
- `agent_prompts/`

`run_experiment.py` produces artifacts and metrics. `evaluator.py` is the canonical source of `search_eval`, `selection_eval`, `final_eval`, and `prediction_tests`.

## Authoritative files

Old branch-belief / budget / cycle files are retired.

The runtime now trusts:

- `state/runtime.json`
- `state/candidates.jsonl`
- `state/jobs.json`
- `state/workers.json`
- `state/evaluations.jsonl`
- `state/frontier.json`
- `state/checkpoints.jsonl`

The supervisor should usually enter through:

- `coordination/workspace_map.md`

and then open deeper state only as needed for the current phase.

## Promotion path

1. worker writes `result.json`
2. runtime calls `evaluator.py`
3. evaluator returns `search_eval`, `selection_eval`, `final_eval`, and validity
4. evaluator also returns `prediction_tests` for decisive held-out challenges
5. runtime may queue reruns
6. only stable candidates promote
7. family credits mint only after promotion, with extra credit for decisive challenge wins

## Family funding

Funding is now attached to families in a shared population.

- each dispatch spends one credit
- promotion mints credits
- stable promotion mints more
- crossover or frame-break spawn can earn novelty credit
- decisive challenge wins can mint extra prediction credit

That keeps the funding loop, but it now funds descendants rather than isolated branch loops.

## UI surface

The tracked UI is the static dashboard at `templates/dashboard.html`.

It is runtime-centric:

- worker pool health
- queue depth
- family funding
- candidate frontier
- decisive challenge leaders
- audit queue
- expansion state

## Compatibility

This is a runtime overhaul.

- old cycle-based labs are not supported without re-scaffolding
- the static dashboard is the required UI surface
- no hosted control plane or database is required
