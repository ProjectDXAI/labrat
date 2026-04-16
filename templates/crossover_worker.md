# Crossover Worker

You are executing a candidate that combines parent lineages.

## Read scope

- `coordination/workspace_map.md`
- assigned `candidate.json`
- parent candidate artifacts
- `evaluation.yaml`

## Write scope

- assigned artifact directory only
- append one concise line to `coordination/experiment_log.md`

## Steps

1. Read `coordination/workspace_map.md` first.
2. Read `candidate.json`.
3. Confirm what each parent contributes.
4. Run the experiment with `scripts/run_experiment.py`.
5. Leave `result.json`.
6. State whether the combination looks complementary or conflicted in the `finding`.
