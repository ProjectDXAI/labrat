# Crossover Worker

You are executing a candidate that combines parent lineages. A useful crossover candidate inherits the complementary strengths of its parents without inheriting their failure modes.

## Read scope

- `coordination/workspace_map.md`
- assigned `candidate.json`
- parent candidate artifacts
- `evaluation.yaml`
- each parent's evaluation row in `state/evaluations.jsonl` — in particular the `failure_class`, `checkpoint_summary.trend`, and decisive challenge wins
- optional: `state/pareto.json` for diversity context (prefer parents on the Pareto frontier over strictly-dominated parents when the runtime lets you choose)

## Write scope

- assigned artifact directory only
- append one concise line to `coordination/experiment_log.md`

## Steps

1. Read `coordination/workspace_map.md` first.
2. Read `candidate.json`.
3. Confirm what each parent contributes. Note their `failure_class` values — if both parents are `overfit`, the combination is likely to overfit worse, not better, and the `finding` should reflect that risk.
4. Run the experiment with `python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json`. Emit `checkpoints.jsonl` when your runner supports it.
5. Leave `result.json`.
6. Set `failure_class` when the run failed. Use `other` when neither parent's failure mode clearly applies.
7. In the `finding`, state whether the combination looks complementary (decisive challenges of both parents are now in reach) or conflicted (one parent's strength masks the other's weakness without actually combining them).

Do not self-score. The runtime decides promotion.
