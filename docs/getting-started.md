# Getting Started

Detailed setup guide. For the quick version, see the README.

## Step 0: Design Your Research Tree

Use a frontier model (GPT-5.4 Pro, Claude Opus, etc.) to design your tree. Give it:

1. Your problem statement and current best approach
2. Recent papers (2024-2026) on the topic (or have it find them)
3. Your constraints (compute, data, timeline)
4. What you've already tried

Ask for: branch taxonomy (5-8 branches), search spaces, scoring formula, dead ends, branch interactions.

This is the most important step. The system optimizes within the tree you define. A bad tree wastes cycles.

## Step 0.5: Establish Your Dataset

All branches must evaluate against the same dataset and benchmark.

**If you have data**: Define train/val/holdout splits. Holdout is never touched by the loop.

**If you don't**: Find one first. HuggingFace Datasets, Kaggle, Papers With Code all have benchmarks. Using a public benchmark means your results are comparable to published work.

**If you need novel data**: Make data collection the first branch. Score it on downstream task performance.

The key: every branch evaluated on the same terms.

## Step 1: Convert Frontier Model Output to YAML

The frontier model gives you prose. You need YAML. Three options:

**Option A**: Ask the same model to output YAML (paste the template schema from `templates/branches.yaml`)

**Option B**: Do it yourself in 15 min. Read the prose, map each suggestion to `delta_key` + `values`.

**Option C**: Paste into Claude Code with "convert this to labrat format."

## Step 2: Write Your Experiment Runner

The only file touching your code:

```python
# research_lab/scripts/run_experiment.py
def run_experiment(config):
    # YOUR pipeline: load data, train, evaluate
    return {
        "experiment_id": config["experiment_id"],
        "metrics": {"test": {"primary_metric": 0.87}},
        "cv_folds": [...],
        "config": config,
    }
```

## Step 2.5: Create Supporting Files

Before bootstrapping, ensure these files exist in your research_lab/:

**constitution.md** -- Your scoring rules. Copy from `templates/constitution.md` and customize:
- Set the hard gates (minimum metric, p-value threshold)
- Set the soft score weights (deployment, robustness, generalization, calibration, complexity)
- Set the D normalization target (e.g., F1/0.50 for classification)

**dead_ends.md** -- Known failures. Copy from `templates/dead_ends.md` and add entries from your frontier model's dead ends list.

**scripts/judge.py** -- Mechanical scorer. Copy from `templates/` or write your own. Must:
- Read result.json and champion.json
- Apply hard gates (auto-reject)
- Compute composite score
- Output: `VERDICT: id=X score=Y champion_score=Z delta=+/-W verdict=PROMOTE/MARGINAL/REJECT`

**scripts/run_experiment.py** -- Your experiment harness. Must:
- Accept `--config config.yaml --output-dir dir`
- Train model, evaluate, cross-validate
- Write result.json with this schema:
  ```json
  {
    "experiment_id": "name",
    "config": {...},
    "metrics": {"test": {"primary_metric": 0.87, "accuracy": 0.90, "p_value": 0.01}},
    "cv_folds": [{"fold": 0, "primary_metric": 0.85}, ...],
    "diagnostics": {"n_train": 1000, "n_features": 500, "pred_std": 0.05}
  }
  ```
- Print: `RESULT: id=X f1=Y acc=Z cv_mean=W p_value=V elapsed=Ns`

Bootstrap will validate these exist and error if missing.

## Step 3: Bootstrap, Dashboard, and Run

```bash
python research_lab/scripts/bootstrap.py

# Copy dashboard into your lab
cp labrat/templates/dashboard.html research_lab/dashboard.html

# Start the dashboard
cd research_lab && python -m http.server 8787 &
# Open http://localhost:8787/dashboard.html
```

Then in Claude Code:
```
Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
Redirect experiment output to files and grep for RESULT lines.
Update all state files in research_lab/state/.
Write handoff to research_lab/logs/handoff.md
```

The orchestrator will:
1. Ask you setup questions on the first run (parallelism, loop interval, branch priorities)
2. Select multiple branches and run them in parallel via subagents
3. Update `state/active_agents.json` so the dashboard shows live agent status
4. Score, update state, write handoff

For continuous operation:
```
/loop 10m Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
```
