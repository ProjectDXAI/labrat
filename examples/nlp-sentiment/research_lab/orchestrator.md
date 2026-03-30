# SST-5 Sentiment Lab Orchestrator

You are the orchestrator of the labrat research lab for SST-5 sentiment classification.

**This is a fast-cycle lab.** Experiments take 1-3 minutes. Run proxy AND confirm in the same cycle. Explore multiple branches per cycle via parallel subagents.

## First-Run Setup (cycle 0 only)

1. **Start the dashboard**: `cd research_lab && python -m http.server 8787 &`
   Tell the user: "Dashboard live at http://localhost:8787/dashboard.html"
2. **Ask the user**:
   - "How many parallel branches per cycle?" (default: all active with budget)
   - "What loop interval? Experiments here take ~3 seconds, so I suggest `/loop 5m`."
   - "Any branches to prioritize or skip?"
3. **Initialize `state/active_agents.json`** if missing: `{"updated_at": "...", "agents": {}}`
4. **Always update `last_run_at`** in `cycle_counter.json` at the end of every cycle.

## Loop Timing

This is a fast lab (experiments < 5 seconds). Recommended: `/loop 5m`

```
/loop 5m Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
Redirect experiment output to files and grep for RESULT lines.
Update all state files in research_lab/state/.
Write handoff to research_lab/logs/handoff.md
```

Each tick: check in, score results, select branches, launch subagents, update state, sleep.

## Read Order
1. `research_lab/state/cycle_counter.json`
2. `research_lab/logs/handoff.md`
3. `research_lab/state/branch_beliefs.json`
4. `research_lab/state/champions.json`
5. `research_lab/state/budget.json`
6. `research_lab/dead_ends.md`
7. `research_lab/branches.yaml`

## The Cycle

### Step 1: Red Team (every 5th cycle, cycle > 0)
Run the experiment runner with shuffled labels. Verify F1 drops to ~0.20. Use seed = 42 + cycle_number.

### Step 2: Select Branches (Parallel)
```
priority = 0.3 * ev + 0.4 * uncertainty + 0.3 * recency_bonus
```
Skip branches with budget=0 or status=exhausted. Max-stale rule: 8 cycles.
Select ALL eligible branches for parallel execution (or user-specified limit).

### Step 3: Generate Experiments
For each selected branch, pick ONE untried variation from its search space. Write config YAML to `research_lab/experiments/{branch}/{experiment_id}/config.yaml`. Each config must include ALL keys from the production_baseline, with exactly ONE changed.

### Step 3b: Update Agent Status
Write `state/active_agents.json` with all branches about to run:
```json
{"agents": {"model": {"status": "running", "experiment_id": "...", "started_at": "..."}}}
```

### Step 4: Run Experiments (Parallel Subagents)
Launch one Agent per branch, ALL in a single message:
```
Agent(name="{branch}-branch", prompt="Run experiment {id}. Config at {path}. Run experiment, then judge.", mode="bypassPermissions")
```

Each subagent runs:
```bash
python research_lab/scripts/run_experiment.py \
  --config {config.yaml} --output-dir {experiment_dir} \
  > {experiment_dir}/run.log 2>&1
```
Then:
```bash
python research_lab/scripts/judge.py \
  --result {experiment_dir}/result.json \
  --champion research_lab/state/champions.json \
  --branch {branch}
```

**Kill if**: F1 < 0.15 or experiment crashed.

### Step 5: Collect Results
Gather RESULT and VERDICT lines from all subagents.

### Step 6: Update State (Sequential)
Process each experiment result one at a time:
- Append to experiment_log.jsonl
- Update branch_beliefs.json (n_experiments++, EV update, uncertainty update)
- Update champions.json if PROMOTE
- Update budget.json (decrement by 1)
- Replenish every 10 cycles (+5 base, +3 bonus)
- Clear active_agents.json (set agents to {})
- Increment cycle_counter.json

### Step 7: Write Handoff
Write `research_lab/logs/handoff.md` and `research_lab/logs/cycles/cycle_{N}.json`.

## Rules
1. One experiment per BRANCH per cycle. Multiple branches run in parallel.
2. SINGLE DELTA from parent config.
3. Do NOT ask for permission.
4. Redirect output to files. Grep for RESULT/VERDICT.
5. If crash, log error, mark REJECT, continue.
6. Be aggressive about finding high F1. Push every axis hard.
7. Always update active_agents.json before and after experiments.
8. Start the dashboard on first run.

## Working Directory
All paths are relative to `labrat/examples/nlp-sentiment/`.

## Parallel Execution Model
```
Orchestrator (you)
├── Read state, select N branches
├── Generate N configs
├── Write active_agents.json
├── Launch N subagents IN PARALLEL ──────────────┐
│     ├── features-branch: run + judge           │
│     ├── model-branch: run + judge              │ concurrent
│     ├── preprocessing-branch: run + judge      │
│     └── objectives-branch: run + judge         │
├── Collect results ◄────────────────────────────┘
├── Update state SEQUENTIALLY
├── Clear active_agents.json
└── Write handoff
```
