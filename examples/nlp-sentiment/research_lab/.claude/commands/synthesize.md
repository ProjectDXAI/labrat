Synthesize what the recent evaluations mean before dispatching more work. This step closes the gap between "config sweeper" and "research agent."

1. Read the last ten entries in `state/evaluations.jsonl` and their corresponding records in `state/candidates.jsonl`.
2. Note the distribution of `failure_class` values and the Pareto context if `state/pareto.json` exists.
3. Answer three questions in one compact paragraph each:
   - What did we learn from the last ten evaluations that is not already in `coordination/prioritized_tasks.md`?
   - Does this change which family should earn the next credit mint?
   - Which decisive challenge is the next credible unlock, and which family is closest to winning it?
4. Write your synthesis to `coordination/prioritized_tasks.md`, overwriting the prior content.

Do not dispatch new work in this step. The supervisor does that next.
