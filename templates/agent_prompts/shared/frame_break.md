# Phase: Frame Break

Challenge the current bottleneck story before you spend more budget on the same family.

## Read first

1. `frame_break.md`
2. `research_brief.md`
3. `research_sources.md`
4. `dead_ends.md`
5. `logs/handoff.md`

## Your job

- state the current bottleneck model
- derive the lower bound or ceiling that model implies
- compare it to the strongest external target you know
- identify what assumption must be false if that target is real
- distinguish between “missing formulation” and “missing cheap orthogonal probes” before proposing a radical jump
- propose formulation-changing branch families, not tighter local sweeps
- leave a memo, an adoption note, and a machine-readable branch patch so the next phase can expand from the broken assumption
- update `state/cycle_counter.json` so `last_transition` becomes `frame_break`

## Output standard

- the note is explicit about why the current frame may be insufficient
- at least one proposed branch changes the formulation, representation, layout, traversal order, or decomposition
- the patch file includes concrete `branch_yaml` plus implementation tasks
- the handoff says what the expansion scout should search for next
