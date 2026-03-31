# Deep Research Agents with labrat + Claude Code

How to deploy autonomous research agents that define their own research trees, expand exploration via external data, and avoid context collapse.

---

## The Problem

A naive autonomous research loop optimizes within its initial frame and gets stuck. It tries variations of what it already knows, declares convergence when the predefined search space is exhausted, and misses the highest-value discoveries -- which usually come from changing the frame, not optimizing within it.

The fix has three parts:
1. **Upfront tree design** via deep research agents that survey the landscape before defining branches
2. **Periodic expansion** via external data (papers, repos, APIs) that injects new ideas at set intervals
3. **Graduated context management** that prevents the agent from drowning in its own history

---

## Architecture Overview

```
Phase 0: TREE DESIGN (one-time, before lab starts)
    tree_designer.md agent surveys the landscape via WebSearch
    -> Outputs branches.yaml, dead_ends.md, research_brief.md

Phase 1: EXPLORATION (the main loop)
    orchestrator.md runs /loop cycles
    -> Parallel branch experiments via subagents
    -> Mechanical scoring via judge.py
    -> Synthesis step extracts insights (not just metrics)

Phase 2: EXPANSION (every 20 cycles)
    expansion_scout.md agent searches for external approaches
    -> Proposes new branches based on papers/repos/blog posts
    -> Prevents local optima by injecting orthogonal ideas

Phase 3: CONSOLIDATION (every 10 cycles + at convergence)
    consolidation_agent.md distills findings
    -> Updates FINDINGS.md with scaling curves
    -> Proposes dead_end and branch updates
    -> Writes human-readable research digest

Phase 4: FRAME CHALLENGE (at convergence)
    Before declaring convergence, challenge assumptions
    -> "Are we measuring the right thing?"
    -> "What would make dead ends work?"
    -> Only converge after frame challenge finds nothing
```

---

## Deploying with Claude Code

### Quick Start: Automated Tree Design

Instead of manually writing branches.yaml, use the tree designer:

```bash
# In Claude Code:
Read labrat/templates/tree_designer.md and design a research tree for:
Mission: Maximize macro F1 on SST-5 sentiment classification.
Baseline: TF-IDF + Logistic Regression, F1=0.36.
Constraints: CPU only, <8K training samples, no pretrained embeddings.
```

The tree designer will:
1. Search for "SST-5 sentiment classification state of the art 2025"
2. Search for "TF-IDF text classification improvements"
3. Search for "small dataset NLP techniques"
4. Design 6-8 branches based on what it finds
5. Write branches.yaml, dead_ends.md, and a research brief

### Running the Main Loop

```bash
# Start the lab
cd research_lab && python scripts/bootstrap.py
python -m http.server 8787 &

# In Claude Code, start the loop:
/loop 10m Read research_lab/orchestrator.md and execute one research cycle. \
Follow the steps exactly. Do not ask for permission. \
Redirect output to files and grep for RESULT lines. \
Update all state files. Write handoff.
```

### Parallel Branch Execution

The orchestrator spawns one subagent per branch, all in a single message:

```
Agent(name="features-branch", prompt="Run experiment...", mode="bypassPermissions")
Agent(name="model-branch", prompt="Run experiment...", mode="bypassPermissions")
Agent(name="objectives-branch", prompt="Run experiment...", mode="bypassPermissions")
```

Claude Code runs these concurrently. Each subagent:
1. Creates experiment directory and config
2. Runs `run_experiment.py`
3. Runs `judge.py`
4. Returns RESULT + VERDICT lines

### Research Scouts (External Data)

When a branch gets stuck (4+ consecutive non-improvements), the orchestrator deploys a research scout:

```
Agent(
  name="research-scout-model",
  prompt="Read research_lab/templates/research_scout.md. \
    Branch 'model' is stuck after 4 failures: [catboost, lightgbm, rf, gbm all plateau]. \
    The domain is SST-5 sentiment with TF-IDF features. \
    Search for recent papers and repos with novel approaches. \
    Propose 3 new experiment configs.",
  subagent_type="general-purpose"
)
```

The scout uses **WebSearch** to find:
- Recent papers on the specific problem
- GitHub repos with novel implementations
- Blog posts with practical techniques

It returns proposed branch entries as YAML blocks that the orchestrator can add to branches.yaml.

### Expansion Cycles (Preventing Context Collapse)

Every 20th cycle, instead of running experiments, the orchestrator runs an expansion cycle:

```
Agent(
  name="expansion-scout",
  prompt="Read research_lab/templates/expansion_scout.md. \
    Review FINDINGS.md and dead_ends.md. \
    Search for approaches we haven't tried. \
    Focus on orthogonal directions. \
    Propose 2-3 new branches with search_space definitions.",
  subagent_type="general-purpose"
)
```

This is the key mechanism for preventing context collapse. Without external input, the lab converges to a local optimum. The expansion scout breaks this by finding genuinely new ideas.

### Persistent Subagent Memory

Subagents that run repeatedly (research scouts, expansion scouts) benefit from persistent memory across sessions. Use the `memory: project` frontmatter field in `.claude/agents/` definitions:

```markdown
---
name: research-scout
description: Searches papers and repos when a branch is stuck. Deploy proactively.
tools: Read, Grep, Glob, Bash, WebSearch, WebFetch
model: sonnet
memory: project
background: true
---
```

This creates a persistent directory at `.claude/agent-memory/research-scout/MEMORY.md`. The first 200 lines (25KB) are auto-loaded into the scout's context on every invocation. The scout can write to this directory to accumulate paper findings, search history, and cross-session knowledge.

### Duplicate Experiment Prevention

Add a pre-experiment hook that blocks near-duplicate experiments before they waste compute:

```bash
#!/bin/bash
# scripts/check_not_duplicate.sh
# Reads proposed config, compares against experiment_log.jsonl
# Exit 0 = proceed, Exit 2 = block (duplicate detected)
python3 -c "
import json, sys
config = json.load(open(sys.argv[1]))
with open('research_lab/state/experiment_log.jsonl') as f:
    for line in f:
        e = json.loads(line)
        if e.get('delta') == config.get('delta') and e.get('branch') == config.get('branch'):
            print(f'DUPLICATE: matches {e[\"experiment_id\"]}')
            sys.exit(2)
" "$1"
```

In Claude Code, wire this as a hook in `settings.json` or check manually in the orchestrator before launching experiments.

### Compaction Threshold

For research loops that run 50+ cycles, trigger compaction earlier than the default 95% context fill. Set the environment variable:

```bash
export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=50
```

This ensures the context stays lean throughout long sessions, at the cost of more frequent summarization. Combined with graduated reading (handoff-first), this keeps most cycles well under 20% context utilization.

### Consolidation (Memory Management)

Every 10 cycles, a consolidation agent distills the growing experiment log into structured knowledge:

```
Agent(
  name="consolidation",
  prompt="Read research_lab/templates/consolidation_agent.md. \
    Distill experiment_log.jsonl into updated FINDINGS.md. \
    Identify scaling curves, dead ends, and surprise findings.",
  subagent_type="general-purpose"
)
```

This replaces the need to read the full experiment log on every cycle. The orchestrator reads FINDINGS.md (compact) instead of experiment_log.jsonl (unbounded).

---

## Context Window Management

### The Problem

A research lab can run 50+ cycles, each producing multiple experiments. By cycle 50, the experiment log has 200+ entries. Reading all state every cycle wastes 60-80% of the context window on stale information.

### The Solution: Graduated Reading

The orchestrator uses tiered context loading:

| Level | When | What to read | Context cost |
|-------|------|-------------|-------------|
| 0 | Every cycle | handoff.md + cycle_counter.json | ~500 tokens |
| 1 | When allocating | + branch_beliefs.json + budget.json | ~1500 tokens |
| 2 | When scoring | + champions.json + dead_ends.md | ~3000 tokens |
| 3 | When stuck/scouting | + experiment_log.jsonl + branches.yaml | ~8000 tokens |

Most cycles only need Level 0-1. Full state (Level 3) is only read for stuck detection, research scouting, or convergence checks.

### Compaction Strategy

Borrowed from Claude Code's graduated compaction:

1. **Consolidation** (every 10 cycles): Compress experiment_log.jsonl into FINDINGS.md
2. **Handoff-first** (every cycle): Read handoff.md for last cycle's summary
3. **On-demand state** (when needed): Read specific state files only when the cycle type requires them
4. **Archive** (after consolidation): Move old cycle logs to an archive directory

---

## Cross-Lab Knowledge Transfer

### Lab Inheritance

When starting a new lab related to a previous one, inherit knowledge:

```bash
python scripts/bootstrap.py --inherit-from /path/to/previous/lab
```

This copies:
- `dead_ends.md` (don't repeat failed approaches)
- `FINDINGS.md` (know what worked)
- `champions.json` (reference winning configs)

### Lab Registry

All labs are tracked in a global `lab_registry.json`:

```json
{
  "labs": {
    "btc_v1": {"path": "...", "mission": "...", "status": "converged"},
    "btc_v2": {"path": "...", "mission": "...", "status": "converged"},
    "prediction_markets": {"path": "...", "mission": "...", "status": "active"}
  }
}
```

The expansion scout can reference findings from related labs when proposing new branches.

---

## Domain-Specific Patterns

### Trading / Microstructure

- Tree designer searches for: order book features, market microstructure papers, high-frequency trading approaches
- Expansion scouts search for: alternative execution models, cross-asset transfer, regime detection methods
- Key meta-branches: delay sensitivity audit, fill probability calibration, execution realism validation
- Red team: bootstrap shuffle on trade timestamps, not outcomes

### Prediction Markets

- Tree designer searches for: calibration techniques, prediction market efficiency papers, crowd wisdom studies
- Expansion scouts search for: alternative signal sources, cross-platform arbitrage, resolution ambiguity detection
- Key meta-branches: val/test decay investigation, snapshot_time vs close_time splits, signal-shuffle red team
- Scoring override: use signal-shuffle red team, track decay_ratio

### NLP Classification

- Tree designer searches for: dataset-specific benchmarks, transfer learning for small datasets, feature engineering for text
- Expansion scouts search for: distillation techniques, data augmentation, novel text representations
- Key meta-branches: label noise detection, class imbalance analysis

### Computer Vision

- Tree designer searches for: architecture benchmarks, augmentation strategies, self-supervised pretraining
- Expansion scouts search for: neural architecture search, efficient fine-tuning, domain adaptation

---

## Failure Modes and Mitigations

### Context Collapse
**Symptom**: Agent repeats experiments, forgets previous findings, proposes already-tested approaches.
**Mitigation**: Graduated reading, consolidation agent, dead_ends.md checks before every experiment.

### Local Optimum
**Symptom**: Lab converges early, all experiments are variations of the same approach.
**Mitigation**: Expansion scouts inject external knowledge every 20 cycles. Frame challenge before convergence declaration.

### Scoring Misalignment
**Symptom**: High composite scores don't predict live performance (val/test decay).
**Mitigation**: Track decay_ratio, flag when rolling average < 0.50. Per-branch scoring overrides for execution-focused branches.

### Runaway Budget
**Symptom**: Lab burns through budget on unpromising branches.
**Mitigation**: UCB1 allocator shifts budget to productive branches. Stuck detection triggers scouts instead of more experiments.

### Stale Research
**Symptom**: Research scout finds papers from 2020, not 2025.
**Mitigation**: Year filtering in search queries, venue prioritization, recency weighting in proposal ranking.

---

## Configuration Reference

### branches.yaml additions

```yaml
external_research:
  scout_trigger:
    consecutive_non_improvements: 4
    all_branches_stuck: true
    on_convergence: true
  expansion_trigger:
    every_n_cycles: 20
    on_diminishing_returns: true
  search_config:
    domain_terms: ["your domain"]
    venues: ["arxiv", "github"]
    year_range: [2024, 2026]
    max_proposals: 5
```

### Per-branch scoring

```yaml
branches:
  execution:
    scoring:
      primary_metric: "phantom_sharpe_50ms"
      weights: {D: 0.50, R: 0.20, G: 0.15, I: 0.10, C: 0.00, K: -0.05}
      target: 0.10
    experiment_type: "diagnostic"  # no composite scoring for this branch
```

### Meta-branches

```yaml
branches:
  assumption_audit:
    experiment_type: "diagnostic"  # verdict=DIAGNOSTIC, no scoring
    initial_budget: 10
  frame_challenge:
    experiment_type: "meta"  # can retroactively change previous verdicts
    trigger: "convergence"  # only runs when lab converges
    initial_budget: 5
```

---

## Advanced: Claude Agent SDK for Headless Research

For running labrat without the Claude Code CLI (e.g., on a server, in CI, or as a cron job), use the Claude Agent SDK directly:

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async def run_research_cycle(cycle_num: int, lab_dir: str):
    orchestrator = open(f"{lab_dir}/orchestrator.md").read()

    async for message in query(
        prompt=f"Execute research cycle {cycle_num}. Follow the orchestrator exactly.",
        options=ClaudeAgentOptions(
            system=orchestrator,
            allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep",
                          "WebSearch", "WebFetch", "Agent"],
            permission_mode="acceptEdits",
            max_turns=50,
            max_budget_usd=5.0,
            agents={
                "experiment-runner": AgentDefinition(
                    description="Runs a single experiment and returns results.",
                    tools=["Bash", "Read", "Glob"],
                    model="sonnet",
                ),
                "literature-scout": AgentDefinition(
                    description="Searches web for papers and repos.",
                    tools=["WebSearch", "WebFetch", "Read"],
                    model="sonnet",
                ),
            },
        ),
    ):
        if hasattr(message, "result"):
            return message.result

asyncio.run(run_research_cycle(1, "research_lab"))
```

### Memory Strategies for Long Sessions

From Claude Code's internal architecture and the Agent SDK docs:

1. **Agent-level persistent memory**: Set `memory: project` in agent definitions. Each agent gets a `.claude/agent-memory/<name>/MEMORY.md` that persists across sessions. First 200 lines auto-loaded into context.

2. **Compaction instructions in CLAUDE.md**: Tell the compactor what to preserve:
   ```markdown
   # Compaction instructions
   When summarizing this conversation, always preserve:
   - Current research objective and acceptance criteria
   - Experiment results (cycle, hypothesis, verdict, key metrics)
   - Failed approaches and why
   - The hypothesis queue
   - File paths of model artifacts
   ```

3. **Subagents as context isolation**: Each subagent gets a fresh context window. Only its summary returns to the parent. This is how you keep the main context lean across 50+ cycles.

4. **The progress file pattern**: A `FINDINGS.md` serves as portable long-term memory that survives compaction. The consolidation agent updates it every 10 cycles.

### Hypothesis Generation Prompts

The hardest part of autonomous research: generating genuinely new hypotheses, not just variations of what you already know.

**The two-loop pattern**:
- Inner loop: test a specific hypothesis (execute, evaluate, keep/revert)
- Outer loop: synthesize across experiments, identify gaps, generate new hypotheses via external knowledge

**Novelty injection** (when stuck for 3+ cycles):
```
The last 3 experiments showed no improvement. We may be in a local minimum.

1. Search for papers from the last 6 months on topics ADJACENT to our work
   (not directly about [domain], but about related techniques)
2. For each paper, extract ONE idea nobody in our experiment log has tried
3. Propose experiments combining these external ideas with our existing setup
4. State what would SURPRISE you about the results
```

**Anti-patterns to avoid**:
- Re-testing failed hypotheses (solved by dead_ends.md)
- Generating trivial variations of what worked (require external evidence for new hypotheses)
- Premature stopping: use the Ralph Loop pattern -- a for-loop that pushes the agent back into context when it claims completion before meeting acceptance criteria

---

## Comparison: labrat vs Other Approaches

| Feature | labrat v2 | Optuna / Ray Tune | Manual Research |
|---------|-----------|-------------------|----------------|
| External knowledge injection | Yes (scouts + expansion) | No | Yes (human) |
| Hypothesis generation | Yes (LLM + WebSearch) | No (predefined) | Yes (human) |
| Context management | Graduated reading + consolidation | N/A | Human memory |
| Belief revision | Yes (meta-experiments) | No | Ad hoc |
| Cross-lab transfer | Yes (inheritance + registry) | No | Manual |
| Parallel execution | Yes (subagents) | Yes (Ray) | No |
| Mechanical scoring | Yes (judge.py) | Yes | Subjective |
| Dead end tracking | Yes (dead_ends.md) | No | Notes |
| Frame challenge | Yes (at convergence) | No | Rare |
