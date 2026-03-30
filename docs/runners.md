# Running on Different Systems

## Claude Code (Primary)

**Single cycle:**
```
Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
Redirect experiment output to files and grep for RESULT lines.
Update all state files in research_lab/state/.
Write handoff to research_lab/logs/handoff.md
```

**Looped:**
```
/loop 10m Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
Redirect experiment output to files and grep for RESULT lines.
Update all state files in research_lab/state/.
Write handoff to research_lab/logs/handoff.md
```

### Parallel Branch Execution

Claude Code supports the `Agent` tool for launching concurrent subagents. The orchestrator uses this to run one experiment per branch simultaneously:

```
# The orchestrator does this automatically:
Agent(name="features-branch", prompt="Run experiment ...", mode="bypassPermissions")
Agent(name="model-branch", prompt="Run experiment ...", mode="bypassPermissions")
Agent(name="objectives-branch", prompt="Run experiment ...", mode="bypassPermissions")
```

All agents launch in one message and run concurrently. The orchestrator collects results and updates state sequentially. This is 3-5x faster than sequential execution.

### Dashboard

The orchestrator starts a dashboard server on first run:
```bash
cd research_lab && python -m http.server 8787 &
```
Open http://localhost:8787/dashboard.html to watch experiments in real-time. Shows live agent indicators, budget bars, experiment verdicts, and the current handoff.

Native `/loop` command handles scheduling. The orchestrator.md IS the agent.

### Choosing Your Loop Interval

Run one experiment manually and time it. Then:

| Experiment time | Loop interval | Rationale |
|----------------|---------------|-----------|
| < 30 seconds | `/loop 5m` | Burn through fast, 4 experiments per tick |
| 30s - 5 min | `/loop 10m` | One full batch per tick |
| 5 - 30 min | `/loop 30m` | Allow completion + state update |
| 30 min - 2 hr | `/loop 1h` | One experiment per tick |
| 2+ hr | `/loop 2h` | Avoid wasted polling |

The orchestrator starts experiments, checks if previous ones finished, scores results, and dispatches new work each tick. Shorter intervals mean faster convergence but more orchestrator overhead.

## Cursor / Windsurf

Open `orchestrator.md`, tell the assistant to follow the instructions. For recurring:
```bash
while true; do cursor-cli "Read research_lab/orchestrator.md and execute one cycle"; sleep 3600; done
```

## Headless (cron + Anthropic API)

```python
# run_one_cycle.py
import anthropic

client = anthropic.Anthropic()
orchestrator = open("research_lab/orchestrator.md").read()

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=8000,
    system=orchestrator,
    messages=[{"role": "user", "content": "Execute one research cycle."}],
    tools=[...],  # file read/write/bash tools
)
```

Cron: `0 * * * * cd /project && python run_one_cycle.py >> lab.log 2>&1`

## GitHub Actions

```yaml
name: Research Cycle
on:
  schedule:
    - cron: '0 * * * *'
jobs:
  cycle:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python run_one_cycle.py
      - run: |
          git add research_lab/state/ research_lab/logs/
          git commit -m "Lab cycle $(cat research_lab/state/cycle_counter.json | jq .cycle)"
          git push
```

## Any System That Can

1. Read markdown files
2. Execute shell commands
3. Write JSON/YAML files
4. Follow multi-step instructions

That's the entire requirement.
