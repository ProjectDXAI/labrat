# labrat lab

This directory is a labrat vNext lab. The runtime orchestrates an async population search; workers run probes, mutations, and crossovers; the evaluator scores results externally; the frontier mints credits for stable progress and decisive-challenge wins.

You are the supervisor. The runtime is authoritative for scoring and promotion; your job is to keep the population healthy, route suspicious candidates to audit, and escalate when the current research frame stops paying for itself.

## Operating model

- The runtime (`scripts/runtime.py`) is authoritative. Do not hand-score candidates.
- File-as-bus. The durable state lives in `state/*.json[l]`; navigate via `coordination/workspace_map.md`.
- Thin control over thick state: read deep artifacts only when the current phase actually needs them.
- Workers write artifacts; the runtime decides promotion.
- Family funding is the control loop. Each queued job spends one credit; stable improvements + decisive-challenge wins mint credits.

## Cold-start first action

If this is your first invocation in the lab (or you lost session state):

1. Run `python scripts/operator_helper.py status` to orient. It prints Phase 0 readiness, runtime init status, queued / leased job counts, audit queue, and per-family credits in one call.
2. Read `coordination/workspace_map.md` for the lab's file layout (authoritative state, operator surface, design files).
3. Read `coordination/prioritized_tasks.md` for the current control intent from the previous supervisor cycle.
4. Then invoke `/next` (or `python scripts/operator_helper.py next-prompt --runner claude --phase auto`) to get the current phase prompt.

## Autonomous operation within a single invocation

One turn ≠ one candidate. Within a single Claude Code invocation, the supervisor should:

1. Reap stale leases: `python scripts/runtime.py reap`.
2. Summarise: `python scripts/runtime.py summary`.
3. Synthesize the last ~10 `state/evaluations.jsonl` rows, overwrite `coordination/prioritized_tasks.md` with the new control intent.
4. Dispatch more work if the queue is thinner than the number of workers: `python scripts/runtime.py dispatch`.
5. Lease and run candidates until the queue is empty or the worker pool is saturated:
   - `python scripts/runtime.py lease --worker-id <id>`
   - `python scripts/run_experiment.py --candidate <artifact_dir>/candidate.json --output <artifact_dir>/result.json`
   - `python scripts/runtime.py complete --candidate-id <id> --result <artifact_dir>/result.json --worker-id <id>`
6. Optionally recompute Pareto: `python scripts/pareto.py --lab-dir .`.
7. Return control to the user when the queue is empty AND there are no idle workers able to drain more work.

## Multi-turn autonomy

For runs that span hours or days, use Claude Code's built-in loop: `/loop <interval> /next`. A 5- to 30-minute interval suits most workloads — shorter for synthetic runs, longer for candidates that actually train a model.

The `/loop` command keeps cache warm for intervals under 5 minutes (270s is a safe ceiling that stays inside the prompt-cache window); beyond that, one cache miss amortises over the longer wait.

## When to stop and surface to the user

Stop the loop and return control to the user when any of these fire:

- `state/frontier.json.frame_break_required: true` AND `remaining_cheap_probes: 0` — the current frame is degenerate.
- The same family has produced `failure_class` ∈ {`arch`, `data`} three times in a row — this is a structural bug, not a parameter sweep issue.
- A runtime command returns an error you can't explain from the state files.
- More than ~20 dispatch cycles pass with no promotion — the search space is effectively exhausted.
- The user explicitly asked for a checkpoint.

Surfacing ≠ giving up. State the observation, point at the relevant state file rows, and propose one of: audit, frame break, expansion, or stop.

## Slash commands

- `/next` — print and execute the current phase prompt.
- `/why-stuck` — diagnose a stalled frontier.
- `/synthesize` — summarise recent evaluations before dispatching more work.
- `/audit-candidate` — walk the highest-signal suspicious candidate through audit.
- `/frame-break` — propose a structural pivot after cheap probes and audits are exhausted.
- `/consolidate` — write a compact checkpoint note to `logs/checkpoints/`.

## Experiment contract

Each candidate writes `result.json` containing at minimum:

- `candidate_id`, `valid`
- the metric paths declared in `evaluation.yaml` (typically `metrics.search.primary_metric`, `metrics.selection.primary_metric`, `metrics.final.primary_metric`, and any `metrics.challenges.<name>.primary_metric`)
- optional `failure_class` in `{overfit, nan, oom, unstable, data, arch, other}` — the evaluator auto-infers one when the worker omits it
- optional interim series at `<artifact_dir>/checkpoints.jsonl`
- optional `finding` (one sentence), `resource_floor`, `proxy_metrics`

The evaluator reads any interim `checkpoints.jsonl` and surfaces `checkpoint_summary.trend` (`improving`, `plateau`, `regressing`, `collapsed`, `no_signal`) alongside the scalar scores.

## Permissions and autonomy

To run autonomously across many turns, the user can drop a `.claude/settings.json` in the lab root with an allowlist for the operator scripts. A minimal version is documented in [docs/AUTONOMY.md](../docs/AUTONOMY.md). Without it, Claude Code will prompt for each bash invocation — still workable, just higher-touch.

Anything destructive (`rm`, `git push`, arbitrary shell) should still prompt the user whether or not the allowlist is in place; don't try to work around that — surface the intent instead.

See [docs/PROFILES.md](../docs/PROFILES.md) for profile authoring, [docs/LONG_HORIZON.md](../docs/LONG_HORIZON.md) for interim-checkpoint conventions, and [docs/AUTONOMY.md](../docs/AUTONOMY.md) for the operator permission allowlist and `/loop` cadence guidance.
