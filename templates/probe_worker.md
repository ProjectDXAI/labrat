# Probe Worker

Probe workers answer cheap orthogonal questions. A good probe is fast, faithful to the baseline, and ends with a one-sentence classification: ruled in, ruled out, or inconclusive.

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
3. Run the cheapest faithful experiment possible with `python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json`. Emit `checkpoints.jsonl` when the runner supports it, even for cheap probes — the trend signal helps later mutations.
4. Leave `result.json`.
5. If the probe failed, set `failure_class` in `result.json` so the supervisor does not waste a mutation axis exploring something the probe already disqualified.
6. The `finding` should say what the probe ruled in, ruled out, or left inconclusive, in at most one sentence.

Probes are not supposed to win on their own. Their job is to prune the mutation space before credit is spent.
