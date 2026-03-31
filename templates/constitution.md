# Scoring Constitution

Customize this for your domain. The judge.py script implements these rules.

## Hard Gates (auto-reject if ANY fail)

- Primary metric above random baseline (e.g., F1 > 0.20 for 5-class)
- Statistical significance: permutation test p-value <= 0.10
- Model not collapsed: prediction std > 0.001
- Cross-validation: >50% of folds above baseline

## Soft Score Formula

```
composite = W_D * D + W_R * R + W_G * G + W_I * I + W_C * C - W_K * K
```

| Component | What it measures | How to compute | Default weight |
|-----------|-----------------|----------------|---------------|
| D (deployment) | How good is the primary metric? | clip(metric / target, 0, 1.5) | 0.35 |
| R (robustness) | Does it work across folds? | positive_folds / total_folds | 0.20 |
| G (generalization) | Is it stable across folds? | 1 - clip(fold_std / fold_mean, 0, 2) / 2 | 0.15 |
| I (information gain) | Is it different from champion? | 1 - rank_corr(preds, champion_preds) | 0.10 |
| C (calibration) | Are predictions well-calibrated? | See calibration section below | 0.10 |
| K (complexity) | Is the model simple? | normalized_complexity (0-1) | -0.05 |

### Changes from v1

- **I (information gain)** is now active. It measures whether the new experiment's predictions are genuinely different from the champion's. A PROMOTE with I=0 means "same model, different wrapper" and should be flagged. Requires saving champion predictions to `state/champion_preds.npy`.
- **C (calibration)** is now computed per domain (see below) instead of defaulting to 0.5.
- **D weight** reduced from 0.40 to 0.35 to make room for I. If you don't implement I, add its weight back to D.

### Calibration (C) by Domain

**Classification**: Expected Calibration Error (ECE).
```python
C = 1.0 - min(1.0, ECE / 0.20)
# ECE = avg |confidence - accuracy| per bin (10 bins)
```

**Regression / Trading**: Prediction interval calibration.
```python
# What fraction of actuals fall within predicted confidence intervals?
coverage_80 = fraction_within_80pct_interval
C = 1.0 - abs(coverage_80 - 0.80) / 0.80
```

**Prediction markets / Pricing**: Brier score decomposition.
```python
C = 1.0 - min(1.0, reliability_component / 0.05)
```

**Default** (if you can't compute calibration): Set C = 0.5 and reduce W_C to 0.05.

## Per-Branch Scoring Override

Branches can override the default weights in `branches.yaml`:

```yaml
execution:
  scoring:
    primary_metric: "phantom_sharpe_50ms"  # override primary metric
    weights: {D: 0.50, R: 0.20, G: 0.15, I: 0.10, C: 0.00, K: -0.05}
    target: 0.10  # normalization target for D
```

The judge should check for branch-specific scoring before using defaults.

## Effect Size Gate (new)

In addition to composite score comparison, compute **Cohen's d** between the new experiment's fold scores and the champion's fold scores:

```python
d = (mean_new - mean_champion) / pooled_std
```

- d > 0.2: Meaningful improvement, supports PROMOTE
- 0.05 < d < 0.2: Small effect, MARGINAL even if composite says PROMOTE
- d < 0.05: Negligible effect, REJECT even if composite is slightly higher

This prevents promoting experiments that win by numerical noise.

## Verdict Thresholds

- **PROMOTE**: composite >= champion_score AND effect_size > 0.05
- **MARGINAL**: within 0.05 of champion AND score >= 0.30, OR composite >= champion but effect_size < 0.05
- **REJECT**: below champion - 0.05

## Red Team

Every 5th cycle: run a negative control. The specific method depends on domain:

**Signal-shuffle red team** (default): Randomly permute the signal labels (which items to act on), keeping outcomes fixed. If the strategy is still profitable, the signal is noise.

**Label-shuffle red team** (classification): Train on shuffled labels. Primary metric must drop to random baseline.

**Bootstrap red team** (trading): Shuffle trade timestamps to destroy temporal structure. If Sharpe survives, the edge is structural (e.g., always-long bias), not predictive.

Use diverse seeds: `seed = hash(f"red_team_{cycle}_{domain}") % 2**31` for independence.

## Customization

Adjust weights, thresholds, and the D normalization target for your domain:
- NLP classification: D = F1 / 0.50, baseline = 1/n_classes
- Regression: D = 1 - clip(RMSE / baseline_RMSE, 0, 1.5)
- Trading: D = clip(sharpe / target_sharpe, 0, 1.5)
- Prediction markets: D = clip(sharpe / 2.0, 0, 1.5), use signal-shuffle red team

## Val/Test Decay Tracking (new)

Track the ratio of test performance to validation performance for every PROMOTE:

```
decay_ratio = test_metric / val_metric
```

If the rolling average decay_ratio drops below 0.50 (test is less than half of val), flag a **systematic methodology problem**: look-ahead bias, data leakage, or regime shift. The scoring formula should not be trusted until the root cause is found.

Log decay_ratio in experiment_log.jsonl for every experiment that has both val and test metrics.
