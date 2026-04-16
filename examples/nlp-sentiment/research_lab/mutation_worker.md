# Mutation Worker

Read the candidate artifact, run the experiment, and leave `result.json`.

## Read scope

- `coordination/workspace_map.md`
- assigned `candidate.json`
- `evaluation.yaml`
- parent artifacts only if needed

## Write scope

- assigned artifact directory only
- append one concise line to `coordination/experiment_log.md`

## Steps

1. Read `coordination/workspace_map.md` first.
2. Read `candidate.json` in the assigned artifact directory.
3. Read `evaluation.yaml` so you know what metrics matter, but do not self-score authoritatively.
4. Run `python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json`.
5. Inspect the result briefly and leave a one-sentence `finding`.
6. Do not promote yourself. The runtime does that after external evaluation.
