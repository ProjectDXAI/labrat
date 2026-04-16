# Long-Horizon Research on labrat

Transformers, world models, and multi-dataset mixing share a common challenge: a single run takes much longer than the tiny-classifier experiments the base runtime was designed for. This doc collects the conventions that keep labrat's file-as-bus runtime working with long-horizon candidates.

## Interim checkpoints: `checkpoints.jsonl`

Workers may append to `<artifact_dir>/checkpoints.jsonl` during training. Each line is a JSON object with at least:

```json
{"step": 100, "search_eval": 0.42, "loss": 1.83, "valid": true}
```

Optional fields:

- `holdout_eval` — held-out or decisive-challenge proxy at this step
- `note` — free-text hint ("loss became non-finite", "plateau"...)

The evaluator (`scripts/evaluator.py`) reads this file when present and surfaces:

- `checkpoint_summary.trend` in `{improving, plateau, regressing, collapsed, no_signal}`
- `checkpoint_summary.first_mean` and `last_mean` (for crude curve shape)
- `checkpoint_summary.last_valid` and `last_step`

The runtime's decision tree remains scalar — promotion still gates on `selection_eval` and stability. The interim series is additive context for the supervisor's synthesis step and for the mutation_worker reading sibling rows.

### Why bother

Without interim checkpoints, a transformer run that collapses to NaN at step 400 out of 500 looks identical to one that never started. With them, the supervisor can read `checkpoint_summary.trend: collapsed` and propose a mutation targeting learning rate or warmup — instead of wasting the next credit on the same collapse.

## `failure_class` contract

Every `result.json` may carry an explicit `failure_class` string. The canonical set:

| Value | Meaning | Typical remediation axis |
|---|---|---|
| `overfit` | training distribution fit but held-out regresses | smaller width, fewer steps, more regularization |
| `nan` | loss became non-finite | lower LR, longer warmup, gradient clipping |
| `oom` | hardware exhausted | smaller batch, smaller d_model |
| `unstable` | valid-looking training that collapses late | shorter training, checkpoint-based model selection |
| `data` | training data shorter than block_size, missing file, etc. | data axis; do not expand the mutation family until resolved |
| `arch` | architectural mismatch (heads not dividing d_model, etc.) | axis constraints in `branches.yaml` |
| `other` | none of the above | supervisor chooses |

When a worker omits `failure_class`, the evaluator auto-infers one by pattern-matching on `metrics.error` and by reading the checkpoint trend. An explicit value from the worker is always preferred because the worker has the most context.

### How the supervisor uses it

The supervisor's synthesis step reads the distribution of `failure_class` values across the last ~10 evaluations. A family producing mostly `overfit` is a different signal from one producing mostly `nan` — and the prompt guidance in `mutation_worker.md` / `crossover_worker.md` instructs workers to read the parent's `failure_class` before running.

## Per-pool lease timeouts

`runtime.yaml` supports per-pool `lease_timeout_seconds` and `heartbeat_timeout_seconds`. The default is 1800s / 900s, sufficient for medium-length classifier runs. For long-horizon workloads, add a dedicated pool:

```yaml
workers:
  pools:
    - resource_class: "cpu"
      slots: 2
      lease_timeout_seconds: 1800
      heartbeat_timeout_seconds: 600
    - resource_class: "gpu"
      slots: 1
      lease_timeout_seconds: 43200   # 12 hours
      heartbeat_timeout_seconds: 1800
```

A family in `branches.yaml` can then declare `resource_class: "gpu"` and the runtime will only lease those candidates to the gpu pool. A job that exceeds the lease is reaped and re-queued, so pick the timeout generously for long runs — 12 hours is cheap; the compute cost of reaping a 10-hour run mid-training is not.

## Soft stability for high-variance training

The default promotion gate requires `relative_std ≤ 0.05` across at least `min_reruns_for_promotion` runs (default 2). For neural-network training on small data, variance between seeds can exceed this even when the underlying architecture is real. Relax with:

```yaml
rerun_policy:
  min_reruns_for_promotion: 2
  max_relative_std: 0.12
  suspicious_improvement_margin: 0.01
  invalid_fast_margin: 0.02
```

`max_relative_std: 0.12` is a reasonable starting point for tiny transformer training. Go higher only if you have a real reason — a wide gate lets the supervisor promote lucky runs.

If your workload has structural high variance that doesn't relax with more seeds, consider a checkpoint-based selection criterion instead: emit interim holdout metrics, and treat the *best* intermediate checkpoint as the candidate's score, not the final step. This is still on labrat's roadmap; until then, relax `max_relative_std` with eyes open.

## Synthetic-first runners

Every long-horizon profile should ship a synthetic `run_experiment.py` that runs the full runtime loop without a real training framework. This is how `make smoke` exercises the end-to-end path (scaffold → bootstrap → dispatch → evaluate → consolidate) without depending on torch / jax / a GPU being present. Real training is the user's responsibility: they replace `scripts/run_experiment.py` with their own runner that honours the same result + `checkpoints.jsonl` contract.

Profile authors should design their synthetic runner so that:

- the three canonical metrics (`search`, `selection`, `final`) respect the config axes,
- the decisive-challenge metrics reward the right shape (e.g., a family that would overfit produces a lower `holdout_generalization` score),
- `checkpoints.jsonl` contains enough intermediate steps that `checkpoint_summary.trend` can distinguish `improving` from `plateau`,
- failure modes (`nan`, `unstable`) occur for the configurations that would actually exhibit them, so the supervisor synthesis step has meaningful signal to classify.

## Compute economics reminder

Credits in `runtime.yaml:funding` are dimensionless by default. For workloads where real compute dollars matter, map `cost_per_experiment` (in `economics.md`) to a real budget and enforce it outside the runtime — the runtime's credit gate is a research-direction allocator, not a billing gate.
