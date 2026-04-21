# Workspace map

The supervisor updates this file as the lab evolves. This initial seed points at the files a cold-start supervisor needs on turn 1.

## Authoritative state

- `state/runtime.json` — step count, active phase, supervisor intent
- `state/frontier.json` — family credits, champions, audit queue, `frame_break_required`, Pareto-enabled flags
- `state/jobs.json` — queued / leased / finished jobs
- `state/workers.json` — worker pool status and per-pool lease timeouts
- `state/candidates.jsonl` — append-only candidate records (latest row per `candidate_id` wins)
- `state/evaluations.jsonl` — append-only evaluation rows with `failure_class` and `checkpoint_summary.trend`
- `state/checkpoints.jsonl` — runtime-level phase checkpoints (not per-candidate training checkpoints)
- `state/pareto.json` — Pareto rank labels when `scripts/pareto.py` has run

## Operator surface

- `AGENTS.md` — project-level instructions Codex reads first
- `CLAUDE.md` — project-level instructions Claude Code auto-loads
- `.claude/commands/` — `/next`, `/why-stuck`, `/synthesize`, `/audit-candidate`, `/frame-break`, `/consolidate`
- `.claude/settings.json` — permission allowlist for the operator loop
- `agent_prompts/` — shared phase prompts for both Codex and Claude Code
- `orchestrator.md` — supervisor phase instructions
- `coordination/prioritized_tasks.md` — the supervisor's current control intent (overwritten each synthesis cycle)
- `coordination/experiment_log.md` — one-liner worker notes, carried forward
- `coordination/implementation_log.md` — debugging and repair notes

## Design files (read once on cold start, then only when reviewing scope)

- `branches.yaml` — family definitions, cheap probes, mutation axes, crossover policy
- `evaluation.yaml` — `search_eval`, `selection_eval`, `prediction_tests`, optional `pareto_metrics`, `rerun_policy`
- `runtime.yaml` — worker pools, funding, plateau, checkpoint interval
- `research_brief.md` — mission and what good looks like
- `research_sources.md` — literature seeds
- `dead_ends.md` — pre-seeded failure modes to not rediscover

## Worker prompts

- `probe_worker.md`, `mutation_worker.md`, `crossover_worker.md`, `implementation_audit.md`, `frame_break.md`, `expansion_scout.md`, `consolidation_agent.md`, `tree_designer.md`

## Candidate artifacts

- `experiments/<family>/<candidate_id>/candidate.json` — resolved config
- `experiments/<family>/<candidate_id>/result.json` — runner output
- `experiments/<family>/<candidate_id>/checkpoints.jsonl` — optional interim series
