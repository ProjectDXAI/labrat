# Mutation Worker

Read the candidate artifact, run the experiment, and leave `result.json`.

## Steps

1. Read `candidate.json` in the assigned artifact directory.
2. Read `evaluation.yaml` so you know what metrics matter, but do not self-score authoritatively.
3. Run `python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json`.
4. Inspect the result briefly and leave a one-sentence `finding`.
5. Do not promote yourself. The runtime does that after external evaluation.
