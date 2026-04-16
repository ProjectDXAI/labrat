# labrat lab

This directory is a labrat vNext lab. The runtime orchestrates an async population search; workers run probes, mutations, and crossovers; the evaluator scores results externally; the frontier mints credits for stable progress and decisive-challenge wins.

## Operating model

- The runtime (`scripts/runtime.py`) is authoritative. Do not hand-score candidates.
- File-as-bus. The durable state lives in `state/*.json[l]`; navigate via `coordination/workspace_map.md` when it exists.
- Thin control over thick state: read deep artifacts only when the current phase actually needs them.
- Workers write artifacts; the runtime decides promotion.

## Day-to-day loop

Use the slash commands instead of memorizing CLI args. They all resolve to the same `python scripts/operator_helper.py next-prompt` invocation you'd otherwise type by hand.

- `/next` — get the next operator prompt for the current phase.
- `/why-stuck` — inspect audit / plateau state when the frontier is not moving.
- `/audit-candidate` — walk the highest-signal suspicious candidate through the audit worker.
- `/frame-break` — propose a structural pivot once cheap probes and audits have been exhausted.
- `/consolidate` — write a compact checkpoint summary to `logs/checkpoints/`.
- `/synthesize` — synthesize what the recent evaluations say before dispatching more work.

## Experiment contract

Each candidate writes `result.json` containing at minimum:

- `candidate_id`, `valid`
- the metric paths declared in `evaluation.yaml` (typically `metrics.search.primary_metric`, `metrics.selection.primary_metric`, `metrics.final.primary_metric`, and any `metrics.challenges.<name>.primary_metric`)
- optional `failure_class` in `{overfit, nan, oom, unstable, data, arch, other}` — the evaluator auto-infers one when the worker omits it
- optional interim series at `<artifact_dir>/checkpoints.jsonl`
- optional `finding` (one sentence), `resource_floor`, `proxy_metrics`

The evaluator reads any interim `checkpoints.jsonl` and surfaces `checkpoint_summary.trend` (`improving`, `plateau`, `regressing`, `collapsed`, `no_signal`) alongside the scalar scores.

## What the supervisor reads from state

- `state/runtime.json`, `state/frontier.json`, `state/jobs.json`, `state/workers.json` — always.
- `state/evaluations.jsonl` — recent rows, especially `failure_class` and `checkpoint_summary.trend`.
- `state/pareto.json` — when `evaluation.yaml` declares `pareto_metrics` and `scripts/pareto.py` has run. Pareto is a *label*, not a comparator — the promotion gate stays scalar.

See [docs/PROFILES.md](../docs/PROFILES.md) for profile authoring and [docs/LONG_HORIZON.md](../docs/LONG_HORIZON.md) for the interim-checkpoint and long-running-job conventions.
