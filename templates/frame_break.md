# Frame Break for labrat vNext

Use this when the frontier is flat after cheap probes and audits, or when the runtime marks `frame_break_required: true`.

## Read

1. `coordination/workspace_map.md`
2. `logs/handoff.md`
3. `coordination/prioritized_tasks.md`
4. `research_brief.md`
5. `research_sources.md`
6. `branches.yaml`
7. `state/frontier.json`
8. `state/evaluations.jsonl`

## Produce

1. `logs/frame_break_<timestamp>.md`
2. `logs/expansions/frame_break_<timestamp>_memo.md`
3. `logs/expansions/frame_break_<timestamp>_patch.yaml`
4. refresh `coordination/prioritized_tasks.md` with the next structural direction

## Required sections

1. current bottleneck model
2. implied lower bound or raw-work floor
3. evidence that contradicts the current frame
4. which assumption must be false if the target is real
5. one missing middle rung, if any, that should be tried before a radical jump
6. one or two concrete family proposals
7. which decisive challenge the next family should try to own that the current frontier does not

## Rules

1. If the family can still win through implementation quality, route to audit instead of frame break.
2. If the family’s raw-work floor is already above the target, say so plainly.
3. Leave a patch file with runnable family definitions, not just prose.
4. If a family has never landed a decisive held-out challenge, do not treat small benchmark gains as real status.
