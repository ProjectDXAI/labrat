Diagnose why the frontier is not moving.

1. Run `python scripts/operator_helper.py status`.
2. Read `state/frontier.json`, focusing on `family_funding` credits, `plateau_counter`, `frame_break_required`, and `audit_queue`.
3. Read the last five entries in `state/evaluations.jsonl`. Note the distribution of `failure_class` values.
4. Read the last five entries in `state/candidates.jsonl`. Note which families are spending credits without promoting.
5. Summarize in one paragraph:
   - which family is blocking,
   - what the dominant recent failure class is,
   - whether the next step is audit, more mutations, or frame break.

Do not write any durable files. The goal here is situational awareness, not new state.
