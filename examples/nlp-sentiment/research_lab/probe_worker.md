# Probe Worker

Probe workers answer cheap orthogonal questions.

## Read scope

- `coordination/workspace_map.md`
- assigned `candidate.json`
- `evaluation.yaml`

## Write scope

- assigned artifact directory only
- append one concise line to `coordination/experiment_log.md`

## Steps

1. Read `coordination/workspace_map.md` before opening deeper files.
2. Read `candidate.json`.
3. Run the cheapest faithful experiment possible with `scripts/run_experiment.py`.
4. Leave `result.json`.
5. The `finding` should say what the probe ruled in or out.
