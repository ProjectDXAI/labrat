# Mutation Worker

Read the candidate artifact, run the experiment, and leave `result.json`. A good mutation worker reports *why* a run failed, not just *that* it failed — that signal feeds the supervisor's next credit-allocation decision.

## Read scope

- `coordination/workspace_map.md`
- assigned `candidate.json`
- `evaluation.yaml`
- sibling and parent signal (light touch, only what you need):
  - the parent candidate's row in `state/evaluations.jsonl` (use `parent_ids` from `candidate.json`) — look for `failure_class`, `checkpoint_summary.trend`, and the last `search_eval`
  - optional: `state/pareto.json` if it exists — tells you how diverse your family's champion set already is
- parent artifacts only if the evaluations summary is not enough

## Write scope

- assigned artifact directory only
- append one concise line to `coordination/experiment_log.md`

## Steps

1. Read `coordination/workspace_map.md` first.
2. Read `candidate.json`.
3. Read the parent's evaluation row to see whether the lineage is `improving`, `plateau`, `regressing`, or `collapsed`, and whether its last run had a `failure_class`. If the parent crashed with `nan` or `arch`, expect the same risk in this candidate.
4. Read `evaluation.yaml` so you know what metrics matter, but do not self-score authoritatively.
5. Run `python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json`. Emit `checkpoints.jsonl` in the artifact directory during training when your runner supports it.
6. When the run finishes, inspect `result.json` briefly and leave a one-sentence `finding`.
7. If the run failed, set `failure_class` in `result.json` to one of: `overfit | nan | oom | unstable | data | arch | other`. The evaluator auto-infers one if you omit it, but your in-context classification is more accurate than a post-hoc regex.
8. Do not promote yourself. The runtime decides promotion after external evaluation.

## What to notice in the parent row

- `failure_class: nan` → this lineage is pushing the optimizer to instability. Consider whether the mutation axes should include LR/warmup rather than width/depth.
- `failure_class: overfit` → the training distribution is fit but held-out regresses. The next mutation should favour smaller width or shorter steps, not more depth.
- `checkpoint_summary.trend: collapsed` → training goes well then falls apart late. Interim checkpoint metrics will tell the supervisor to shorten `steps` or lower `lr`.
- `checkpoint_summary.trend: plateau` → more of the same won't help. The supervisor is likely to route to audit or frame break; your job is still to run this mutation faithfully.

Stay narrow and artifact-oriented. The mutation worker is not an ideation surface.
