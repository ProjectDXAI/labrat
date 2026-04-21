Walk the highest-signal suspicious candidate through an implementation audit.

1. Read `state/frontier.json.audit_queue` and `state/frontier.json.invalid_fast_candidates`.
2. Pick the candidate with the highest `search_eval` among the suspicious set. Read its record from `state/candidates.jsonl` and its evaluation from `state/evaluations.jsonl`, plus any `checkpoints.jsonl` under its `artifact_dir`.
3. Read `implementation_audit.md`.
4. Decide: is this a real bug, a real regression, or a misclassification?
5. Leave an audit note under `logs/audits/<candidate_id>.md` and, if the candidate should re-enter the frontier, clear it from `audit_queue` with the appropriate runtime command.

Do not change scores. The runtime is authoritative.
