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
4. **Operator prompts**
   - `orchestrator.md`
   - worker prompts
   - audit / frame-break / expansion prompts
5. **UI**
   - static dashboard fed directly by runtime state

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

## Promotion path

1. worker writes `result.json`
2. runtime calls `evaluator.py`
3. evaluator returns `search_eval`, `selection_eval`, `final_eval`, and validity
4. runtime may queue reruns
5. only stable candidates promote
6. family credits mint only after promotion

## Family funding

Funding is now attached to families in a shared population.

- each dispatch spends one credit
- promotion mints credits
- stable promotion mints more
- crossover or frame-break spawn can earn novelty credit

That keeps the funding loop, but it now funds descendants rather than isolated branch loops.
