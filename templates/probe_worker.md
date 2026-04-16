# Probe Worker

Probe workers answer cheap orthogonal questions.

## Steps

1. Read `candidate.json`.
2. Run the cheapest faithful experiment possible with `scripts/run_experiment.py`.
3. Leave `result.json`.
4. The `finding` should say what the probe ruled in or out.
