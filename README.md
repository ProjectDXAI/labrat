# labrat

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/ProjectDXAI/labrat?style=flat&color=black)](https://github.com/ProjectDXAI/labrat/stargazers)

[**Quickstart**](#quickstart) · [**For Agents**](#for-agents) · [**Example**](#example) · [**Docs**](docs/) · [**DXRG**](https://dxrg.ai)

Autonomous research lab that explores multi-branch research trees in parallel. An economic funding mechanism prioritizes across competing trajectories -- productive branches earn more compute, dead branches get defunded. The system converges on what works without manual steering.

![dashboard](docs/dash-sample.png)

Extends [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) from single-agent single-metric to multi-branch market allocation. Born out of work at [DXRG](https://dxrg.ai) to push autoresearch into broader, more exploratory domains where you need to map the full surface area of a problem before committing to a direction.

Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Works with Codex, OpenClaw, or any agent that reads markdown and runs shell commands.

## How it works

Your agent harness (Claude Code, Codex, etc.) acts as the orchestrator -- the monolith that watches everything, allocates budget, and judges results. It dispatches labrats (subagents) to explore branches in parallel. Each experiment changes one thing. A formula scores results. Budget flows to what produces. The loop runs until convergence.

```
  orchestrator.md
  │
  ├─ Select branches by priority (UCB1-inspired)
  ├─ Dispatch labrats in parallel ─────────────────┐
  │     ├── ᘛ⁐ᕐᐷ~ features: run + judge           │
  │     ├── ᘛ⁐ᕐᐷ~ model: run + judge               │ concurrent
  │     └── ᘛ⁐ᕐᐷ~ objectives: run + judge          │
  ├─ Collect + score mechanically ◄────────────────┘
  ├─ Update beliefs, budget, champions
  └─ Write handoff → next cycle
```

Every 5th cycle: red team (shuffled labels). Every 10th: budget replenishment. Stuck branches trigger a research scout that searches for new approaches.

## Quickstart

**1. Design your research tree** using a deep research model (GPT-5.4 Pro, Claude with extended thinking, or similar). Give it your problem, baseline, and constraints. Ask for branches, search spaces, scoring formula, and dead ends. Convert to YAML:

```yaml
mission: "Maximize macro F1 on 5-class sentiment. Baseline F1=0.36."

branches:
  model:
    initial_budget: 25
    search_space:
      - delta_key: "model.type"
        values: ["svm", "catboost", "random_forest"]
  features:
    initial_budget: 20
    search_space:
      - delta_key: "features.ngram_max"
        values: [2, 3]
```

**2. Write your experiment runner** -- thin wrapper around your eval pipeline:

```python
# research_lab/scripts/run_experiment.py
def run_experiment(config):
    model = train(config)
    return {"metrics": {"test": {"primary_metric": evaluate(model).f1}}, ...}
```

**3. Bootstrap and loop:**

```bash
cp templates/* research_lab/          # orchestrator, constitution, dead_ends
cd research_lab && python scripts/bootstrap.py
python -m http.server 8787 &          # dashboard
```

Then tell your agent:
```
/loop 10m Read research_lab/orchestrator.md and execute one research cycle.
```

Watch it live at `localhost:8787/dashboard.html`.

## For agents

If a user pointed you here, your job is to set up and run a research lab for their problem.

**If they haven't given you context yet**, ask:

1. What problem are you solving? What's your baseline and target metric?
2. What are your constraints? (compute, time, dataset size)
3. Any recent papers or prior experiments to build on?
4. Do you have an eval pipeline, or should I build one?

**Once you have the problem:**

1. **Design the tree** -- use a deep research model to map the problem space, convert to `branches.yaml`
2. **Build the lab** -- create `run_experiment.py`, customize `constitution.md` and `dead_ends.md`
3. **Check in** -- "Here's N branches with M budget. Scoring weights X. Ready?"
4. **Run** -- bootstrap, start dashboard, enter `/loop`. Follow `orchestrator.md` exactly.
5. **Report** -- when converged, summarize: what matters, what's flat, what surprised you.

`templates/orchestrator.md` is your brain during the loop. Everything is in there.

## Example

**[examples/nlp-sentiment/](examples/nlp-sentiment/)** -- 5-class sentiment on SST-5. CPU-only, 3 seconds per experiment. 43 cycles, 147 experiments.

The market found 3 axes that matter, 9 that are flat, and that branch winners don't always stack. Production champion: F1=0.398 vs 0.360 baseline. [Full writeup](examples/nlp-sentiment/README.md).

## Docs

[Getting Started](docs/getting-started.md) · [Architecture](docs/ARCHITECTURE.md) · [Economics](docs/economics.md) · [Domains](docs/domains.md) · [Runners](docs/runners.md) · [Visual Identity](docs/labrats-visual-guide.md)

## Credits

Extends [autoresearch](https://github.com/karpathy/autoresearch) with market-based multi-branch allocation and parallel agents. Built with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) at [DXRG](https://dxrg.ai). MIT license.
