# Scoring: SST-5 Sentiment Classification

## Hard Gates
- Macro F1 > 0.20 (above 5-class random)
- Permutation p-value < 0.10
- CV: >50% of folds above baseline

## Score
```
S = 0.40 * F1_normalized + 0.25 * robustness + 0.20 * generalization + 0.10 * calibration - 0.05 * complexity
```

F1 normalized against 0.50 (strong baseline target). Robustness = fraction of CV folds above baseline. Generalization = 1 - CV coefficient of variation.
