Write a compact checkpoint summary of the current frontier.

1. Read `consolidation_agent.md`.
2. Read `state/frontier.json`, the last twenty entries of `state/candidates.jsonl`, and `state/evaluations.jsonl`.
3. Read the dominant `failure_class` distribution in the last twenty evaluations.
4. Write `logs/checkpoints/checkpoint_<timestamp>.md` including:
   - current global champion + the family funding concentration,
   - which families have actually won decisive challenges,
   - the dominant failure_class and what it suggests,
   - the next bottleneck (throughput, evaluation quality, operator quality, or scope).

Keep the checkpoint short and durable. The supervisor will use this file the next time it reads the workspace.
