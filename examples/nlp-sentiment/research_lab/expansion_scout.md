# Expansion Scout for labrat vNext

Use this only after frame break or when `pending_expansion` exists in `state/frontier.json`.

## Goal

Produce formulation-changing family proposals backed by evidence.

## Read

1. `frame_break.md`
2. latest `logs/expansions/*memo.md`
3. `research_brief.md`
4. `research_sources.md`
5. `branches.yaml`
6. `state/frontier.json`
7. `state/evaluations.jsonl`

## Output

Write:

1. `logs/expansions/expansion_<timestamp>.md`
2. `logs/expansions/expansion_<timestamp>_patch.yaml`

The patch must use the same proposal structure as `research_scout.md`.

## Rules

1. Do not propose a tighter sweep of the same saturated family.
2. State which current assumption breaks.
3. Prefer one or two strong proposals over a long list.
4. Each proposal must be runnable by the existing runtime without inventing missing details.
