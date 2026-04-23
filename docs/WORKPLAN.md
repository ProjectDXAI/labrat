# Workplan: Running a labrat Program

> Historical note: this workplan describes the older cycle-based labrat flow.
> `labrat` vNext now uses an async population runtime with external consistent
> evaluation. Use [getting-started.md](getting-started.md)
> and [DEEP_RESEARCH.md](DEEP_RESEARCH.md)
> for the current workflow.

## Phase 0: Problem Definition (1-2 hours, human + frontier model)

### What You Need
1. A clear problem statement with a measurable metric
2. A baseline approach that works (even if poorly)
3. An evaluation pipeline that takes a config and returns a score
4. Compute budget (how long per experiment, how many total)

### What to Do
1. Collect 3-5 recent papers relevant to your problem
2. Open a frontier model in Codex or Claude Code (GPT-5.5 in Codex when available, Claude Opus, etc.)
3. Give it your problem, baseline, constraints, and papers
4. Ask for: branch taxonomy, search spaces, scoring formula, dead ends
5. Iterate 2-3 times until the tree feels comprehensive but not bloated
6. Encode the output as `branches.yaml` and `dead_ends.md`

### Why a Frontier Model for Tree Design
The tree design is a creative, knowledge-intensive task. You want the model
with the broadest knowledge of recent literature and the strongest reasoning
about experimental design. This is a one-time cost (1-2 hours) that determines
the quality of the entire research program.

The autoresearch system itself uses a coding assistant (Claude Code, Cursor, etc.)
for execution. The frontier model is only for the initial design.

## Phase 1: Setup (30 minutes, human)

1. Copy `templates/` into your project as `research_lab/`
2. Customize `branches.yaml` (from Phase 0)
3. Customize `constitution.md` (scoring weights for your domain)
4. Write `scripts/run_experiment.py` (wrapper around YOUR eval pipeline)
5. Seed `dead_ends.md` (from Phase 0 + your own experience)
6. Run `python research_lab/scripts/bootstrap.py`

## Phase 2: Exploration (autonomous, ~24 hours)

Start the loop:
```
/loop 1h Read research_lab/orchestrator.md and execute one research cycle...
```

What happens:
- Each branch gets explored 1-2 times (breadth-first via uncertainty bonus)
- Red team check at cycle 5 validates the baseline isn't leaking
- Budget replenishment at cycle 10 rewards productive branches
- Proxy kills catch obviously bad ideas in minutes instead of hours
- The handoff document tracks progress for you to review

**Check in after 8-12 cycles.** Read `research_lab/logs/handoff.md`.
Are the branches producing meaningful variation? Is the scoring formula
discriminating well? Adjust if needed.

## Phase 3: Exploitation (autonomous, ~24 hours)

After all branches are explored:
- The allocator revisits productive branches for deeper sweeps
- Scaling curves emerge (feature count, learning rate, etc.)
- Flatness detection identifies hyperparameters that don't matter
- The capstone branch tests cross-branch winner combinations

**Check in after 20-25 cycles.** Are you seeing diminishing returns?
New experiments producing MARGINAL or REJECT verdicts consistently?
That's convergence. The lab has found the answer.

## Phase 4: Execution Calibration (optional, for deployment)

If your research feeds into a deployed system:
1. Add an `execution` branch that tests against live/production data
2. Measure the gap between research metrics and deployment metrics
3. Calibrate thresholds, gates, and configs for production constraints

This is where backtest meets reality. Our trading research found that the
model scored 0.957 on backtest but showed no alpha on 6-month-old live data.
Retraining fixed it. The execution branch found 3 deployment blockers in
5 experiments that 40 cycles of backtest optimization couldn't see.

## Phase 5: Documentation and Handoff

When the lab converges:
1. Read the final `handoff.md` for the summary
2. Review `experiment_log.jsonl` for the complete history
3. The champion per branch is your best config per axis
4. The capstone champion is your overall best config
5. Dead ends are documented -- don't re-explore them

## Timeline

| Phase | Duration | Who | Output |
|-------|----------|-----|--------|
| 0. Tree design | 1-2 hours | Human + frontier model | branches.yaml |
| 1. Setup | 30 min | Human | research_lab/ ready |
| 2. Exploration | ~24 hours | Autonomous | Branch champions |
| 3. Exploitation | ~24 hours | Autonomous | Scaling curves, capstone |
| 4. Execution | ~12 hours | Semi-autonomous | Deployment calibration |
| 5. Documentation | 1 hour | Human review | Final report |

**Total: ~50 hours, of which ~2-3 hours require human attention.**

## Cost Estimate

| Component | Cost |
|-----------|------|
| Frontier model for tree design | ~$5 (one conversation) |
| Agent interface for 50 cycles | Depends on the user's Codex or Claude Code plan |
| Compute for experiments | Depends on your domain |
| VPS for execution calibration | ~$15/month |

## Common Mistakes

1. **Tree too broad**: 10+ branches with 20+ items each = 200+ experiments.
   Start with 5-6 branches, 3-5 items each. You can always add more.

2. **Scoring formula wrong**: If the formula doesn't discriminate,
   everything scores ~0.75. Test it on 2-3 manual experiments first.

3. **No baseline**: The judge needs something to compare against.
   Run your baseline through the harness FIRST, then bootstrap.

4. **Proxy too short**: If your experiment needs 2 hours but the proxy
   runs 5 minutes, it may not be representative. Match proxy to your
   domain's minimum viable experiment time.

5. **Ignoring the handoff**: The handoff document is the lab's communication
   channel. Read it after every 5-10 cycles. It tells you if something is wrong.

6. **Skipping the execution branch**: Backtest performance ≠ deployment performance.
   If you're deploying, add an execution branch. It will find things backtest can't.
