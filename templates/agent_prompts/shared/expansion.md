# Phase: Expansion Scout

Search outside the current frame when the whole frontier is flattening.

## Read first

1. `expansion_scout.md`
2. `research_brief.md`
3. `research_sources.md`
4. `dead_ends.md`
5. `logs/handoff.md`

## Your job

- start from the latest frame-break conclusion if one exists
- identify the negative space around the current tree
- propose a branch ladder when helpful: cheap orthogonal probes first, then formulation changes
- search for orthogonal approaches the existing branches could not discover on their own
- propose 2-3 strong new branches or new search-space entries
- leave a short memo that explains what changed in the lab's worldview
- write a machine-readable patch file for any proposed new branch family
- update `state/cycle_counter.json` so `last_transition` becomes `expansion`

## Output standard

- proposals are source-backed and concrete
- new directions are orthogonal, not just tighter knob sweeps
- at least one proposal tests the broken assumption identified in frame-break mode when the frontier gap remains large
- the patch file is sufficient for a later agent to merge accepted branches without guessing structure
- the memo explains why the previous frame was insufficient
