# Implementation Audit for labrat vNext

Use this for invalid-fast and unstable near-frontier candidates.

## Read

1. `logs/handoff.md`
2. `branches.yaml`
3. `evaluation.yaml`
4. `state/frontier.json`
5. `state/candidates.jsonl`
6. `state/evaluations.jsonl`

## Job

Pick the strongest suspicious candidate and answer:

1. what family claim it was testing
2. whether the anomaly reproduces
3. the cheapest control that localizes the issue
4. whether the problem is:
   - `implementation_bug`
   - `evaluation_mismatch`
   - `scheduler_or_lowering_issue`
   - `true_dead_end`
   - `still_promising`
5. the exact next step

## Outputs

Write:

1. `logs/implementation_audit_<timestamp>.md`
2. `logs/implementation_audit_<timestamp>_patch.yaml` when the family should stay alive

The patch should either:

- add a follow-up cheap probe
- add a focused mutation axis
- revive the family after a bug fix
- or state that the family should be defunded
