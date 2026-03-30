# labrat

Autoresearch explores one direction. This explores all of them and figures out which ones to fund.

Branches compete for compute budget. Productive branches earn more. Dead branches get defunded. The system converges without you.

![dashboard](docs/exampledash.png)

A recent approach we've been using at [DXRG](https://dxrg.ai) to expand autoresearch into more exploratory domains. When you're trying to get a grounding across the full surface area of a problem -- not just optimize one metric on one axis -- you need something that can run many branches simultaneously and figure out which ones are worth funding. This is that.

Extends [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) from single-agent single-metric to multi-branch market allocation across a full research tree.

No framework. No SDK. Markdown, JSON, YAML, and your existing pipeline.

## How it works

The orchestrator (the eye) reads state, picks branches, and dispatches labrats (subagents) to run experiments in parallel. A mechanical formula scores results. Budget flows to branches that produce. Repeat until convergence.

```
  orchestrator.md (the eye)
  │
  ├─ 1. Read state, select N branches by priority
  ├─ 2. Generate N experiments (one per branch, single delta)
  ├─ 3. Dispatch labrats IN PARALLEL ──────────────────┐
  │       ├── ᘛ⁐ᕐᐷ~ features: run + judge             │
  │       ├── ᘛ⁐ᕐᐷ~ model: run + judge                 │ concurrent
  │       └── ᘛ⁐ᕐᐷ~ objectives: run + judge            │
  ├─ 4. Collect results ◄──────────────────────────────┘
  ├─ 5. Score mechanically (formula, not LLM judgment)
  ├─ 6. Update state, beliefs, budget
  └─ 7. Write handoff for next cycle

  Every 5th cycle: red team (shuffled labels)
  Every 10th cycle: budget replenishment
  Stuck branches: research scout searches for new approaches
```

The AI decides **what** to try. A formula decides **if it worked**. Budget decides **what gets more compute**. Branches run in parallel. Repeat until convergence.

## Why markets

Research programs fail two ways: branches churn without converging, or the whole program over-invests in one direction. Markets solve both.

Each branch starts with compute credits. Experiments cost credits. Branches that improve earn bonus credits. Branches that don't get starved. The allocator is UCB1-inspired:

```
priority = 0.3 * expected_value + 0.4 * uncertainty + 0.3 * recency
```

High-uncertainty branches get explored early. Productive branches get revisited. Stale branches get forced. The system naturally transitions from breadth-first exploration to depth-first exploitation.

## Quick start

**1. Design your tree** with a frontier model (GPT-5.4 Pro, Claude, etc.):
```
Here is my problem, my baseline, my constraints, and 5 recent papers.
Design a multi-branch research tree with search spaces, scoring formula,
and dead ends.
```

**2. Convert to YAML** (ask Claude Code or do it yourself in 15 min):
```yaml
mission: "What you're optimizing, what the baseline is, what success looks like."

branches:
  architecture:
    initial_budget: 25
    search_space:
      - delta_key: "model.type"
        values: ["deberta-v3", "roberta", "distilbert"]
  data:
    initial_budget: 20
    search_space:
      - delta_key: "augmentation"
        values: ["back_translation", "synonym_replace"]
```

**3. Write your experiment runner** (`scripts/run_experiment.py`):
```python
def run_experiment(config):
    model = train(config)
    metrics = evaluate(model)
    return {
        "experiment_id": config["experiment_id"],
        "metrics": {"test": {"primary_metric": metrics.f1, "p_value": perm_test()}},
        "cv_folds": [{"fold": 0, "primary_metric": 0.85}, ...],
        "config": config,
    }
```

**4. Create supporting files** in `research_lab/`:
```bash
cp templates/constitution.md research_lab/    # scoring rules (customize weights)
cp templates/dead_ends.md research_lab/       # known failures (add yours)
# Also need: scripts/judge.py (scorer), scripts/run_experiment.py (your harness)
```

**5. Bootstrap and run**:
```bash
cd research_lab
python scripts/bootstrap.py        # validates files, creates state, copies dashboard
python -m http.server 8787 &       # start dashboard
```

Then in Claude Code (from the project root):
```
Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
```

For continuous operation (recommended):
```
/loop 10m Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
```

Walk away. Come back in 24 hours. Read `research_lab/logs/handoff.md`. Watch it live at `http://localhost:8787/dashboard.html`.

## What you get

- **Market allocation** -- productive branches earn compute, dead branches starve
- **Parallel labrats** -- subagents explore multiple branches per cycle concurrently
- **Live dashboard** -- score timeline, branch leaderboard, experiment verdicts, rat status indicators
- **Mechanical scoring** -- formula not LLM judgment, prevents evaluation drift over long runs
- **Single-delta experiments** -- one change per experiment, clean causal attribution
- **Red team** -- shuffled-label integrity checks every Nth cycle
- **Research scouts** -- stuck branches trigger internet search for new approaches
- **Dead ends registry** -- structured memory of what failed, saves 10-20% compute
- **Budget economics** -- credits can map to real costs (GPU hours, dollars)

## Example: NLP Sentiment on SST-5

The **[examples/nlp-sentiment/](examples/nlp-sentiment/)** directory is a fully runnable lab that classifies 5-class sentiment on the Stanford Sentiment Treebank. CPU-only, ~3 seconds per experiment.

43 cycles, 147 experiments, 5 red team checks. The market found:

| What the labrats found | Evidence |
|----------------------|---------|
| class_weight=balanced is the only thing that matters | +11% relative F1, biggest single delta |
| 5K features beats 10K and 20K | Smaller vocab reduces overfitting on 8.5K training samples |
| Bigrams capture negation | "not good" becomes a feature |
| SVM beats all tree models | Linear methods win on sparse TF-IDF |
| 9 axes are flat | max_features, sublinear_tf, trigrams, C, min_df, max_df, all trees |
| Branch winners don't always stack | Capstone < individual champion until min_df=5 was added |

3 axes that matter. 9 proven flat. Production champion: F1=0.398 (vs 0.360 baseline).

See the [full writeup](examples/nlp-sentiment/README.md) for dataset details, scoring formula, and published baseline comparisons.

## Results from internal research

55 cycles across a crypto microstructure trading program at DXRG:

| What the market found | Evidence |
|----------------------|---------|
| 12 book features = 49 features | OFI, momentum, volatility add nothing |
| Tree depth 4 = 6 = 8 | Signal is approximately linear |
| 2-day dead zone optimal | Temporal autocorrelation decays in 1-2 days |
| More training data always helps | train_frac 0.8 >> 0.6 |
| Retrained model has live alpha | +0.10 Sharpe at instant fills |
| Execution latency is the bottleneck | Edge dies at ~250ms |

9 axes proven flat. 6 axes that matter. 231/231 walk-forward windows positive. 3 deployment blockers found by the execution branch that backtest couldn't see.

## Docs

- **[Getting Started](docs/getting-started.md)** -- Detailed setup guide
- **[Architecture](docs/ARCHITECTURE.md)** -- Three layers, parallel execution, dashboard, research scouts
- **[Workplan](docs/WORKPLAN.md)** -- 5-phase plan with timeline and cost estimates
- **[Economics](docs/economics.md)** -- Abstract mode vs cost-aware mode
- **[Domains](docs/domains.md)** -- Adapting to NLP, vision, RL, trading, drug discovery
- **[Runners](docs/runners.md)** -- Claude Code, Cursor, cron+API, GitHub Actions

## File structure

```
research_lab/
├── orchestrator.md         # The eye (copy from templates/)
├── constitution.md         # Scoring formula
├── branches.yaml           # Research tree + mission statement
├── dead_ends.md            # Known failures
├── dashboard.html          # Live monitoring (serve with python -m http.server)
├── scripts/
│   ├── run_experiment.py   # YOUR eval harness wrapper
│   ├── judge.py            # Mechanical scoring
│   ├── batch_runner.py     # Burn through many cycles fast
│   └── bootstrap.py        # State initialization
├── state/
│   ├── cycle_counter.json
│   ├── branch_beliefs.json
│   ├── champions.json
│   ├── budget.json
│   ├── experiment_log.jsonl
│   └── active_agents.json  # Labrat status (dashboard reads this)
├── experiments/            # Per-branch experiment results
└── logs/
    ├── handoff.md          # What happened, what's next
    └── cycles/             # Per-cycle JSON records
```

## Credits

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch). Extended with market-based multi-branch allocation, parallel labrat agents, and live dashboards. Built with [Claude Code](https://claude.ai/claude-code) at [DXRG](https://dxrg.ai).

MIT license.
