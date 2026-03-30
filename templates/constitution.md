# Scoring Constitution

Customize this for your domain. The judge.py script implements these rules.

## Hard Gates (auto-reject if ANY fail)

- Primary metric above random baseline (e.g., F1 > 0.20 for 5-class)
- Statistical significance: permutation test p-value <= 0.10
- Model not collapsed: prediction std > 0.001
- Cross-validation: >50% of folds above baseline

## Soft Score Formula

```
composite = W_D * D + W_R * R + W_G * G + W_C * C - W_K * K
```

| Component | What it measures | How to compute | Suggested weight |
|-----------|-----------------|----------------|-----------------|
| D (deployment) | How good is the primary metric? | clip(metric / target, 0, 1.5) | 0.40 |
| R (robustness) | Does it work across folds? | positive_folds / total_folds | 0.25 |
| G (generalization) | Is it stable across folds? | 1 - clip(fold_std / fold_mean, 0, 2) / 2 | 0.20 |
| C (calibration) | Are predictions well-calibrated? | domain-specific (default 0.5) | 0.10 |
| K (complexity) | Is the model simple? | normalized_complexity (0-1) | -0.05 |

## Verdict Thresholds

- **PROMOTE**: composite >= champion_score
- **MARGINAL**: within 0.03 of champion AND score >= 0.30
- **REJECT**: below champion - 0.03

## Red Team

Every 5th cycle: train on shuffled labels. Primary metric must drop to random baseline level.

## Customization

Adjust weights, thresholds, and the D normalization target for your domain:
- NLP classification: D = F1 / 0.50, baseline = 1/n_classes
- Regression: D = 1 - clip(RMSE / baseline_RMSE, 0, 1.5)
- Trading: D = clip(sharpe / 0.20, 0, 1.5)
