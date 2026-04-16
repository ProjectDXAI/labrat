# Research Profiles

Profiles let `new_lab.py` scaffold a *working* lab for a specific research workload, not just a set of `LABRAT_PLACEHOLDER` stubs. Someone arriving with a research goal in mind should be able to clone, pick a profile, and reach their first real candidate in about five minutes.

## What's in the base vs. what's in a profile

Every lab — profile or not — gets:

- the runtime scripts (`runtime.py`, `evaluator.py`, `operator_helper.py`, `bootstrap.py`, `lab_core.py`, `pareto.py`, `research_scout.py`)
- the worker prompt files (`orchestrator.md`, `mutation_worker.md`, `crossover_worker.md`, `probe_worker.md`, `implementation_audit.md`, `frame_break.md`, `expansion_scout.md`, `tree_designer.md`, `consolidation_agent.md`)
- the phase-prompt directory under `agent_prompts/`
- a generic `CLAUDE.md` at the lab root
- `.claude/commands/{next, why-stuck, audit-candidate, frame-break, consolidate, synthesize}.md` — Claude Code slash commands that wrap the common operator actions
- the dashboard (`dashboard.html`)
- placeholder Phase 0 files (`branches.yaml`, `evaluation.yaml`, etc.) that the user must fill in when no profile is selected

A **profile** additionally overlays:

- filled Phase 0 files (`branches.yaml`, `evaluation.yaml`, `runtime.yaml`, `research_brief.md`, `research_sources.md`, `dead_ends.md`) — no `LABRAT_PLACEHOLDER` left
- a working `scripts/run_experiment.py` that honours the result contract
- seed data under `data/` when the workload needs it
- optional `requirements.txt` for domain-specific dependencies
- optional overrides for `CLAUDE.md` or any `.claude/commands/*.md` when the profile wants workload-specific guidance

The base files and the profile's files merge via `shutil.copytree(..., dirs_exist_ok=True)`. Profile files win when both exist. This lets a profile add workload context without re-stating everything the base already covers.

## Available profiles

| Profile | Workload | Status |
|---|---|---|
| `transformer-arch` | Tiny character-level transformer architecture search, with held-out-distribution decisive challenges. CPU-runnable in synthetic mode; PyTorch opt-in for real training. | shipped |
| `world-model` | Latent-dynamics model with environment-rollout decisive challenges. | follow-up PR |
| `multi-dataset` | Multi-dataset mixing with leave-one-dataset-out decisive challenges. | follow-up PR |

## Using a profile

```bash
python scripts/new_lab.py my_transformer_search --profile=transformer-arch
cd my_transformer_search
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
```

From there Claude Code users can type `/next` (the profile ships the slash commands) or manually invoke `python scripts/operator_helper.py next-prompt --runner claude --phase auto`.

## Authoring a new profile

A profile is a directory under `profiles/<name>/` with any subset of these files:

```
profiles/<name>/
  branches.yaml              # fully filled, no LABRAT_PLACEHOLDER
  evaluation.yaml            # includes at least one decisive prediction_test
  runtime.yaml               # pool resource_class chosen for the workload
  research_brief.md          # why this lab exists, what good looks like
  research_sources.md        # literature seeds, including what to avoid rediscovering
  dead_ends.md               # pre-seeded dead ends; prevents the search from rediscovering them
  requirements.txt           # optional; extra deps beyond the top-level requirements.txt
  scripts/run_experiment.py  # working runner that honours the result.json contract
  data/                      # seed datasets, corpora, etc.
  coordination/              # optional seed workspace map
  CLAUDE.md                  # optional override of the base lab-root CLAUDE.md
  .claude/commands/          # optional overrides or additions to the base slash commands
```

Minimum viable: the six Phase 0 files plus a `run_experiment.py`. `CLAUDE.md` and `.claude/commands/` are only needed when you want to *override* the generic base versions — every lab already ships with them.

### Contract for `run_experiment.py`

Invoked as:

```
python scripts/run_experiment.py --candidate <candidate.json> --output <artifact_dir>/result.json
```

Must write `result.json` with:

- `candidate_id`
- `valid` (bool)
- `metrics.search.primary_metric`, `metrics.selection.primary_metric`, `metrics.final.primary_metric` (as dictated by `evaluation.yaml`)
- decisive-challenge metrics under `metrics.challenges.<name>.primary_metric`
- optional `failure_class` in `{overfit, nan, oom, unstable, data, arch, other}` (auto-inferred if omitted — see [LONG_HORIZON.md](LONG_HORIZON.md))
- optional `finding` (one sentence)
- optional `resource_floor`
- optional `proxy_metrics`

May also append interim checkpoints to `<artifact_dir>/checkpoints.jsonl` — see [LONG_HORIZON.md](LONG_HORIZON.md) for the shape.

### Synthetic-first principle

A profile should default to a mode that runs without heavy dependencies (no `torch`, no `jax`, no GPU). This keeps clone-and-run functional on a bare laptop and makes `make smoke-transformer`-style end-to-end checks cheap. Real training can be opt-in via a `training.mode` field or similar per-profile config gate.

### Dead ends

Always seed `dead_ends.md` with failure modes you already know about. A profile that lets the lab waste its first ten cycles rediscovering "dropout above 0.1 hurts on tiny corpora" is a profile that wastes compute.
