# SST-5 Example Expansion Scout

Use the standard expansion protocol, but search for orthogonal directions that still respect the example's reduced constraints.

Read:

1. `logs/handoff.md`
2. `research_brief.md`
3. `research_sources.md`
4. `dead_ends.md`
5. `branches.yaml`

Look for:

- CPU-friendly representation changes
- small-data sentiment tricks that the current sparse baseline cannot express
- lightweight distillation or embedding paths that could still be made runnable

Write:

- the full report to `logs/expansion_scout_cycle_N.md`
- the short worldview memo to `logs/expansions/expansion_cycle_N_memo.md`

Do not propose heavy GPU-only branches for this example's runnable loop unless you explicitly mark them as reference-only and out of scope for the reduced lab.
