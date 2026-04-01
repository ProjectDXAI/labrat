# labrat

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)

[**Quickstart**](#quickstart) · [**For Agents**](#for-agents) · [**Example**](#example) · [**Docs**](docs/) · [**DXRG**](https://dxrg.ai)

Turn any AI agent into an autonomous researcher. Point it at a problem, give it a budget, walk away. It designs its own experiments, kills dead branches, finds papers when it gets stuck, and tells you what actually matters.

![dashboard](docs/dash-sample.png)

147 experiments. Zero human intervention. One command.

## What this is

An autoresearch framework that goes beyond single-metric optimization. Where [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) runs one agent against one metric, labrat runs N agents across N branches simultaneously, with an economic system that routes compute to whatever is producing results.

The agent doesn't just tune hyperparameters. It explores fundamentally different approaches in parallel, scores them mechanically, defunds the losers, and doubles down on the winners. When it runs out of ideas, it searches the internet for papers and proposes new directions it hasn't tried. When it's about to declare convergence, it challenges its own assumptions first.

Built for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Works with Codex, OpenClaw, or any agent that reads markdown and runs shell commands.

Born out of work at [DXRG](https://dxrg.ai) running autonomous research programs on BTC microstructure (55 cycles, 47 experiments), prediction markets (74 experiments, 18 branches), and NLP (147 experiments, 43 cycles). Every feature exists because something went wrong in a real deployment and we built the fix.

## The autoresearch loop

```
  orchestrator
  │
  ├─ Profile the data (Step 0: what subgroups have variance?)
  ├─ Select branches by UCB1 priority
  ├─ Dispatch labrats in parallel ─────────────────┐
  │     ├── ᘛ⁐ᕐᐷ~ features: run + judge           │
  │     ├── ᘛ⁐ᕐᐷ~ model: run + judge               │ concurrent
  │     └── ᘛ⁐ᕐᐷ~ objectives: run + judge          │
  ├─ Score mechanically ◄──────────────────────────┘
  ├─ Synthesize: "what did we learn?"
  ├─ Update beliefs, budget, champions
  ├─ Check: any gates blocking good experiments?
  ├─ Check: any assumptions invalidated?
  └─ Write handoff → next cycle
```

Every 5th cycle: red team (shuffled labels, is the signal real?). Every 10th: budget replenishment. Every 20th: expansion scout searches arXiv and GitHub for approaches the lab hasn't tried. Stuck branches trigger a research scout that reads papers and proposes new experiments. At convergence: frame challenge tests assumptions before declaring done.

The tree structure is whatever you want it to be:

```
                            baseline
                          TF-IDF + LR
                               │
            ┌──────────┬───────┼───────┬──────────┐
            │          │       │       │          │
        features    model   preproc  objectives  ensemble
        budget:20  budget:20  b:15    b:15       b:10
            │          │       │       │
         bigrams     SVM    stopwords balanced    ← promoted
         trigrams    catboost  min_df   C=0.5     ← tested
         char_wb    lightgbm  max_df   C=5.0     ← rejected
         50K feat   rand.for.          C=10
            │          │       │       │
            └──────────┴───────┴───────┘
                               │
                           capstone
                     combine branch winners
```

Branches can be narrow (5 values of learning rate) or broad (entirely different algorithmic families). The allocator doesn't care. It just measures what produces and routes budget accordingly.

## When to use this

You have a baseline, a metric, multiple axes of variation, and more ideas than time to test them.

- **Architecture search** -- attention patterns, layer depths, positional encodings, activation functions. Each branch tests one axis. The allocator finds which dimensions move the needle vs which are flat.
- **Feature engineering** -- 200 features, most are noise. Branches test subsets, encodings, interactions. The allocator identifies the minimal set.
- **Trading strategy research** -- signals, execution methods, regime filters, sizing rules across walk-forward windows. The allocator separates real edge from backtest overfitting.
- **Kernel optimization** -- compiler flags, memory layouts, tiling strategies. Experiments run in seconds. The allocator burns through hundreds of configs.
- **Prompt / RAG tuning** -- chunking strategies, embedding models, reranking, prompt templates. Each branch is a pipeline axis.
- **Drug compound screening** -- molecular descriptors, fingerprint types, model architectures. Branches compete for compute based on predicted activity.

## What the autoresearcher actually does

It's not just a hyperparameter sweeper. The full v2 loop includes:

- **Data profiling** before experiments start (what subgroups have variance? what correlates?)
- **Research scouts** that search the web for papers when a branch gets stuck
- **Expansion scouts** that inject external knowledge every 20 cycles to escape local optima
- **Belief revision** that catches when a new finding invalidates previous results
- **Gate evolution** that detects when your scoring gates are blocking good experiments
- **Failure categorization** that tells you WHY experiments fail, not just that they did
- **Efficiency tracking** that measures waste rate, budget ROI, and time-to-first-promote per branch
- **Frame challenge** that questions "are we even measuring the right thing?" before convergence

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
