# Autonomy: running labrat with Claude Code as a multi-turn supervisor

The runtime is designed to be operated by a coding agent (Opus 4.7 is the intended supervisor, Codex and other frontier models work too). This doc covers three things that turn a single-turn supervisor into a multi-turn autonomous one: the permission allowlist, the `/loop` cadence, and the stop criteria.

## Permission allowlist

Claude Code prompts for each bash invocation by default. For autonomous multi-turn operation the user (not the agent) should add a narrow allowlist at the lab root:

```json
{
  "permissions": {
    "allow": [
      "Bash(python scripts/runtime.py:*)",
      "Bash(python scripts/operator_helper.py:*)",
      "Bash(python scripts/evaluator.py:*)",
      "Bash(python scripts/pareto.py:*)",
      "Bash(python scripts/run_experiment.py:*)",
      "Bash(python scripts/research_scout.py:*)",
      "Bash(python scripts/bootstrap.py)",
      "Bash(python -m http.server:*)",
      "Bash(mkdir:experiments/*)",
      "Bash(mkdir:logs/*)"
    ]
  }
}
```

Save as `<lab_root>/.claude/settings.json`. The agent will not write this file for you — permission allowlists are a user decision, not an agent one.

Destructive operations (`rm`, `git push`, arbitrary shell) should continue to prompt even with this allowlist in place. If you find yourself wanting to broaden the allowlist further, think about what that auto-approves before you add it.

## `/loop` cadence

For runs that span hours or days, use Claude Code's built-in loop:

```
/loop 5m /next
```

The interval matters:

- **60s–270s** — stays inside Claude Code's prompt-cache window. Right for active work where candidates finish quickly and you want tight feedback.
- **270s–1800s** — one cache miss amortises over a longer wait. Right for medium-length candidates or when the queue often has idle time.
- **1800s–3600s** — once-per-half-hour check-ins. Right for overnight runs and candidates that genuinely train a model.

**Don't pick exactly 300s.** That's the worst-of-both: you pay the cache miss without amortising it over a meaningful wait. Either drop to 270s (stay cached) or go to 1200s+ (amortise the miss).

Default for synthetic runs: 120–180s. Default for runs with real training: 1200–1800s.

## Stop criteria

Inside the supervisor loop, Claude should surface to the user (return control, write a note to `logs/handoff.md`) when any of these fire:

- `state/frontier.json.frame_break_required: true` **and** `remaining_cheap_probes: 0` across families — the current frame is degenerate.
- The same family has produced `failure_class` ∈ {`arch`, `data`} three times in a row — a structural bug, not a sweep issue.
- A runtime command returns an error whose cause isn't obvious from the state files.
- More than ~20 dispatch cycles pass with no promotion — the search space is effectively exhausted.
- The user explicitly asked for a checkpoint.

Surfacing is not giving up. State the observation, point at the state file rows that triggered it, and propose one of: audit, frame break, expansion, or stop.

## Autonomous loop shape inside one invocation

A single Claude Code turn in supervisor mode should do as much work as the state file permits:

1. Reap stale leases.
2. Inspect runtime + synthesize recent evaluations.
3. Overwrite `coordination/prioritized_tasks.md` with the new control intent.
4. Dispatch if the queue is thinner than the number of workers.
5. Lease → run → complete each remaining queued job until the pool is saturated or the queue is empty.
6. Recompute Pareto if `pareto_metrics` is declared.
7. Return control.

The `/loop` wrapper picks this up again at the next interval. Between turns, nothing is running — state on disk is all the memory the supervisor needs.

## Cold-start recovery

If Claude Code is invoked fresh with no session context:

1. `python scripts/operator_helper.py status` — one-call orientation.
2. Read `coordination/workspace_map.md` — lab file layout.
3. Read `coordination/prioritized_tasks.md` — previous supervisor's control intent.
4. Invoke `/next` and follow the phase prompt.

If any of those first three files don't exist, the lab hasn't bootstrapped yet. Run `python scripts/bootstrap.py` first.
