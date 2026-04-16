Read:

1. `orchestrator.md`
2. `state/runtime.json`
3. `state/frontier.json`
4. `state/jobs.json`
5. `state/workers.json`

Then:

- reap stale leases
- synthesize the last ~10 evaluations in `state/evaluations.jsonl` (dominant `failure_class`, `checkpoint_summary.trend`, closest decisive challenge) before dispatching
- top up the queue if needed
- keep workers busy
- defer scoring to the runtime
- route suspicious candidates to audit
