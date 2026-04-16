# Consolidation Agent for labrat vNext

Summarize the shared population without changing runtime state.

## Read

1. `state/frontier.json`
2. `state/candidates.jsonl`
3. `state/evaluations.jsonl`
4. `state/checkpoints.jsonl`
5. `research_sources.md`

## Write

`logs/checkpoints/checkpoint_<timestamp>.md`

Include:

- current global champion and why it leads
- family funding distribution
- audit queue summary
- which families are exhausted versus still structurally alive
- whether the next bottleneck is throughput, evaluation quality, or operator quality
- what should happen before the next checkpoint
