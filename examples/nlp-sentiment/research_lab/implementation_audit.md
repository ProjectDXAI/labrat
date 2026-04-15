# SST-5 Implementation Audit

You are auditing a suspicious frontier family in the flagship example lab.

This phase exists for a specific failure mode: a branch looks surprisingly close, oddly flaky, or invalid-fast, and the lab needs to know whether the problem is mechanical or scientific before discarding the family.

## Read first

1. `logs/handoff.md`
2. `state/champions.json`
3. `state/experiment_log.jsonl`
4. `branches.yaml`
5. `research_brief.md`
6. `research_sources.md`
7. `dead_ends.md`

## Your job

1. Pick one suspicious branch family.
2. State why it still looks promising.
3. Reproduce the anomaly.
4. Run one or two cheap controls.
5. Classify the failure:
   - `implementation_bug`
   - `evaluation_mismatch`
   - `scheduler_or_lowering_issue`
   - `true_dead_end`
   - `still_promising_needs_more_probes`
6. Leave the exact next action.

## Output files

Write:

1. `logs/implementation_audit_cycle_N.md`
2. optionally `logs/implementation_audit_cycle_N_patch.yaml`
3. update `logs/handoff.md`

## Rules

1. Use the cheapest discriminating controls first.
2. Be explicit about whether the issue is mechanical or scientific.
3. If the family survives, leave a concrete next probe instead of prose only.
4. If the family dies, say why it dies and what would need to change for it to revive.
