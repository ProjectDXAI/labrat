# SST-5 Frame Break

You are interrupting local optimization in the flagship example lab.

This is not normal scouting. Your job is to challenge the current bottleneck story before more budget is spent on the same family.

## Read first

1. `logs/handoff.md`
2. `research_brief.md`
3. `research_sources.md`
4. `state/champions.json`
5. `state/experiment_log.jsonl`
6. `branches.yaml`
7. `dead_ends.md`

## Your job

1. State the current bottleneck model.
2. Derive the rough lower bound or ceiling that model implies.
3. Compare it to the strongest external target you know.
4. Identify what assumption must be false if that target is real.
5. Say whether the lab skipped any cheap orthogonal probes first.
6. Propose 2-3 formulation-changing branch families.
7. Leave concrete runnable proposals, not just prose.

## Output files

Write:

1. `logs/frame_break_cycle_N.md`
2. `logs/expansions/frame_break_cycle_N_memo.md`
3. `logs/expansions/frame_break_cycle_N_patch.yaml`
4. update `logs/handoff.md`

## Rules

1. Do not propose another tight sweep of the same family.
2. If the current best is still far from a credible target, say the frontier is structurally incomplete.
3. Say explicitly whether the next step should be a cheap probe, an implementation audit, or a full formulation change.
