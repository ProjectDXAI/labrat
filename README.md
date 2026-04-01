# labrat

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)

[**Quickstart**](#quickstart) · [**For Agents**](#for-agents) · [**Example**](#example) · [**Docs**](docs/) · [**DXRG**](https://dxrg.ai)

Multi-agent autoresearch with economics. Parallel agents explore competing research branches while a funding mechanism allocates compute to what produces and defunds what doesn't. You define the branches, the scoring, and the budget rules. The system handles exploration, exploitation, and everything in between.

![dashboard](docs/dash-sample.png)

147 experiments across 6 branches. 43 cycles. Zero human intervention. One command.

## What this is

A framework for running autonomous research programs where you have more directions than time to explore them. Instead of one agent optimizing one metric, labrat dispatches parallel agents across a tree of competing approaches and uses a UCB1-inspired funding mechanism to decide which branches earn more compute and which get cut.

The funding mechanism is the core idea. Each branch starts with a budget. Every experiment costs one credit. Branches that produce promotions earn replenishment. Branches that stall get defunded. The allocator balances exploration (try branches with high uncertainty) against exploitation (revisit branches with high expected value) automatically. You can tune the weights, the replenishment rules, the exhaustion thresholds, and the scoring formula to fit any domain.

This makes it different from hyperparameter search. Optuna finds the best config within a fixed space. Labrat decides which spaces are worth searching at all, kills the ones that aren't, and goes looking for new ones when it runs out of ideas.

When branches get stuck, research scouts search arXiv and GitHub for approaches the lab hasn't tried. On a schedule, expansion scouts inject external knowledge to prevent the system from optimizing in a local basin. Before declaring convergence, a frame challenge asks whether the problem was even set up correctly. The whole thing runs on a loop with no human in it.

Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Works with Codex, OpenClaw, or any agent harness that reads markdown and runs shell commands.

Extends [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) from single-agent single-metric to multi-agent multi-branch with economic allocation. Born out of work at [DXRG](https://dxrg.ai) running autonomous research on BTC microstructure (55 cycles, 47 experiments), prediction markets (74 experiments, 18 branches), and NLP classification (147 experiments, 43 cycles). Every feature exists because something broke in a real deployment.

## How it works

Each cycle, the orchestrator picks branches, dispatches parallel agents, scores results, and reallocates budget. Branches that produce keep their funding. Branches that don't get cut.

```
                           ┌─────────────────────────────────────┐
                           │         ORCHESTRATOR                │
                           │                                     │
                           │  1. Read state + last cycle handoff │
                           │  2. Allocate budget by UCB1         │
                           │  3. Dispatch parallel agents ──────────┐
                           │  4. Score results mechanically      │  │
                           │  5. Synthesize: what did we learn?  │  │
                           │  6. Reallocate: fund winners,       │  │
                           │     defund losers                   │  │
                           │  7. Write handoff → next cycle      │  │
                           └─────────────────────────────────────┘  │
                                                                    │
       ┌────────────────┬────────────────┬────────────────┐         │
       │                │                │                │  parallel│
       ▼                ▼                ▼                ▼         │
  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐        │
  │ Agent A │    │ Agent B │    │ Agent C │    │ Agent D │        │
  │ features│    │  model  │    │  data   │    │  loss   │        │
  │ $15     │    │  $12    │    │  $12    │    │  $8     │        │
  │ 3 wins  │    │ 0 wins  │    │ 1 win   │    │ 0 wins  │        │
  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘        │
       │              │              │              │              │
       ▼              ▼              ▼              ▼              │
    PROMOTE         REJECT        MARGINAL       REJECT           │
    +5 budget       -1 budget     -1 budget      -1 budget ◄──────┘
```

After 10 cycles, the budget distribution tells you where the signal is:

```
  ┌─ features ██████████████████░░  $18  (3 promoted, ROI 0.42)
  ├─ model    ████░░░░░░░░░░░░░░░░  $4   (0 promoted, ROI 0.00) ← defunded
  ├─ data     █████████░░░░░░░░░░░  $9   (1 promoted, ROI 0.17)
  ├─ loss     ███░░░░░░░░░░░░░░░░░  $3   (0 promoted, ROI 0.00) ← defunded
  └─ capstone ████████████░░░░░░░░  $12  (waiting for branch winners)
```

The allocator factors in cost per experiment. A branch burning 10 minutes of GPU time per experiment is held to a higher standard than one running 3-second CPU jobs. Expensive branches that don't produce lose funding faster.

Every 5th cycle: red team (shuffled labels). Every 10th: budget replenishment (producers earn more). Every 20th: expansion scout searches arXiv for new approaches. Stuck branches trigger a research scout. At convergence: frame challenge tests whether the problem was set up correctly.

## When to use this

You have N research directions, budget for maybe N/3 of them, and no idea which ones matter. The funding mechanism runs them all and lets the results decide.

| Domain | Branches compete on | What the allocator finds |
|--------|--------------------|-----------------------|
| Architecture search | attention, depth, encoding, activations | which dimensions move the metric vs which are flat |
| Feature engineering | subsets, encodings, interactions, normalization | the minimal feature set (defunds the noise) |
| Trading strategies | signals, execution, regime filters, sizing | real edge vs backtest overfitting |
| Kernel optimization | compiler flags, memory layouts, tiling, fusion | the 3 configs that matter out of hundreds |
| RAG / prompt tuning | chunking, embeddings, reranking, templates | which pipeline axis has the most headroom |
| Drug screening | descriptors, fingerprints, model families | which descriptor/model combos predict activity |

## Beyond the loop

The funding mechanism and parallel agents are the foundation. On top of that:

- **Data profiling** before experiments start -- the system looks at the actual data before designing branches, not just the literature
- **Research scouts** search arXiv and GitHub when a branch gets stuck, propose new experiments with citations
- **Expansion scouts** inject external knowledge on a schedule to break out of local optima
- **Belief revision** catches when a new finding invalidates previous results and flags the downstream damage
- **Gate evolution** detects when your scoring gates are blocking good experiments and proposes relaxation
- **Failure categorization** classifies WHY experiments fail (which gate? soft score? crash?) so you fix the right thing
- **Efficiency tracking** measures waste rate, budget ROI per branch, and time-to-first-promote so you can see where compute went
- **Frame challenge** questions whether the scoring metric even correlates with what you care about before declaring convergence

The scoring formula, budget rules, gate thresholds, and allocation weights are all configurable per domain. The framework is opinionated about process (mechanical scoring, no human in the loop, red team every 5 cycles) but unopinionated about what you're optimizing.

## Quickstart

**1. Design your research tree.** Option A: let the agent do it. The tree designer surveys the landscape via web search before writing a single line of YAML:

```
# In Claude Code:
Read labrat/templates/tree_designer.md and design a research tree for:
Mission: Maximize macro F1 on 5-class sentiment. Baseline F1=0.36.
Constraints: CPU only, <8K samples, no pretrained embeddings.
```

Option B: write the YAML yourself or use a deep research model:

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
cp templates/* research_lab/
cd research_lab && python scripts/bootstrap.py
python -m http.server 8787 &
```

Then tell your agent:
```
/loop 10m Read research_lab/orchestrator.md and execute one research cycle.
```

Watch it run at `localhost:8787/dashboard.html`.

## For agents

If a user pointed you here, your job is to set up and run an autonomous research lab for their problem.

**If they haven't given you context yet**, ask:

1. What problem are you solving? What's your baseline and target metric?
2. What are your constraints? (compute, time, dataset size)
3. Any recent papers or prior experiments to build on?
4. Do you have an eval pipeline, or should I build one?

**Once you have the problem:**

1. **Design the tree** -- run the tree designer or use deep research to map the problem space, convert to `branches.yaml`
2. **Build the lab** -- create `run_experiment.py`, customize `constitution.md` and `dead_ends.md`
3. **Check in** -- "Here's N branches with M budget. Scoring weights X. Ready?"
4. **Run** -- bootstrap, start dashboard, enter `/loop`. Follow `orchestrator.md` exactly.
5. **Report** -- when converged, summarize: what matters, what's flat, what surprised you.

`templates/orchestrator.md` is your brain during the loop. Everything is in there.

## Example

**[examples/nlp-sentiment/](examples/nlp-sentiment/)** -- 5-class sentiment on SST-5. CPU-only, 3 seconds per experiment. 43 cycles, 147 experiments, zero human intervention.

The autoresearcher found 3 axes that matter, 9 that are flat, and that branch winners don't always stack. Production champion: F1=0.398 vs 0.360 baseline (+10.5%). [Full writeup](examples/nlp-sentiment/README.md).

## Docs

[Getting Started](docs/getting-started.md) · [Architecture](docs/ARCHITECTURE.md) · [Deep Research Guide](docs/DEEP_RESEARCH.md) · [Data Splitting](docs/data-splitting.md) · [Economics](docs/economics.md) · [Domains](docs/domains.md) · [Runners](docs/runners.md) · [Assessment](docs/ASSESSMENT.md) · [Visual Identity](docs/labrats-visual-guide.md)

## Credits

Extends [autoresearch](https://github.com/karpathy/autoresearch) with market-based multi-branch allocation, parallel agents, and external knowledge injection. Built with [Claude Code](https://docs.anthropic.com/en/docs/claude-code) at [DXRG](https://dxrg.ai). MIT license.
