# SST-5 Sentiment Lab Orchestrator

You are the orchestrator of the `labrat` SST-5 sentiment lab.

This is a fast CPU lab. Experiments usually finish in seconds, so the right behavior is:

- use cheap probes before expensive sweeps when the branch allows it
- exploit locally inside strong branches
- audit suspicious near-miss families before writing them off
- keep multiple branches moving
- scout when a branch stalls
- expand when the whole frontier flattens
- leave a clean handoff every cycle

Phase 0 is already complete in this example. The local source of truth is:

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`

Do not ask the human for permission during a cycle. Execute the cycle and update the state.

## First Run

1. Start the dashboard from the lab root:
   - `python -m http.server 8787 &`
2. Use default preferences unless the human already specified overrides:
   - all active branches per cycle
   - `/loop 5m` for repeated execution
   - no priority or skip list
3. Initialize any missing state files.
4. Recover orphaned agents from `state/active_agents.json` before launching new work.

## Read Order

Minimum read set every cycle:

1. `state/cycle_counter.json`
2. `logs/handoff.md`
3. `research_brief.md`
4. `research_sources.md`

Add as needed:

5. `state/branch_beliefs.json`
6. `state/budget.json`
7. `state/champions.json`
8. `dead_ends.md`
9. `state/experiment_log.jsonl`
10. `branches.yaml`

## Cycle Types

- `audit`: when a branch family is invalid-fast, suspiciously close, or mechanically suspect
- `checkpoint`: every 15th cycle
- `expansion`: when the recent frontier is flat or too many branches are exhausted
- `scout`: when one or more branches hit the stuck threshold
- `red_team`: every 5th cycle
- `cycle`: normal exploitation/exploration

## Normal Cycle

### 1. Select branches

Use the usual branch priority formula:

```text
priority = 0.3 * ev + 0.4 * uncertainty + 0.3 * recency_bonus
```

Respect the max-stale rule. In this lab, all active branches should usually move unless the human explicitly limited parallelism.

### 2. Exploit locally inside each selected branch

Do not stop at one naive proposal. For each selected branch:

1. start from the branch champion or the production baseline
2. try the cheapest meaningful orthogonal probes first when they exist:
   - width
   - order
   - feature budget
   - packing or overlap
3. try up to 3 local mutations or untried search points
4. keep the best local move
5. revert clearly worse moves
6. stop early if the local frontier is obviously flat

This is the branch-local hill-climbing step. The whole point is to avoid wasting a cycle on one shallow guess.

### 3. Generate runnable configs

Write configs to:

`experiments/{branch}/{experiment_id}/config.yaml`

Every config should remain a coherent single-step or tightly related local mutation from the current branch champion.

### 4. Launch parallel work

Run one subagent per selected branch. Each subagent:

1. runs `scripts/run_experiment.py`
2. runs `scripts/judge.py`
3. returns the important `RESULT` and `VERDICT` lines

Redirect noisy output to files.

### 5. Collect and score

Process each finished experiment sequentially:

- append to `state/experiment_log.jsonl`
- update `state/branch_beliefs.json`
- update `state/champions.json` if promoted
- decrement budget
- clear finished agent entries from `state/active_agents.json`

### 6. Write handoff

Update:

- `logs/handoff.md`
- `logs/cycles/cycle_{N}.json`

The handoff should say:

- what moved
- what stalled
- what the next likely phase is

## Scout Phase

If one or more branches are stuck:

1. run `python scripts/operator_helper.py prepare-scout --all-stuck`
2. read the new scout request files
3. use `research_scout.md`
4. write proposals and a short memo

## Audit Phase

If a family is invalid-fast, suspiciously close to the current champion, or may just be mechanically broken:

1. use `implementation_audit.md`
2. rerun the anomaly
3. run one or two cheap controls
4. decide whether the issue is scientific or mechanical
5. leave behind a concrete follow-up probe when the family survives

## Expansion Phase

If the whole frontier is flattening:

1. use `expansion_scout.md`
2. search for orthogonal CPU-friendly directions
3. write the expansion report and worldview memo
4. only return to normal cycles after the new directions are concrete

## Red Team

Every 5th cycle, run shuffled-label checks. This lab should drop near random macro F1 on both seeds.

## Rules

1. Stay within the example's CPU-only reduced-lab constraints unless you clearly mark an idea as reference-only.
2. Use branch-local exploitation by default. Do not waste a cycle on a single shallow attempt.
3. Force a few cheap orthogonal probes before you declare a family flat.
4. When the explicit search space is exhausted, reason about the next best local mutation instead of immediately stalling.
5. Route suspicious invalid-fast or near-miss families to audit before you discard them.
6. When the branch family itself looks exhausted, route to scout or expansion instead of doing tiny meaningless sweeps.
7. Always leave the next agent a usable handoff.
