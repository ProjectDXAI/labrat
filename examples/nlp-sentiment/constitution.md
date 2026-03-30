# Scoring Constitution

From GPT-5.4 Pro research tree design. Hard latency gate + weighted composite.

## Hard Gate

Reject if `p95_latency_ms > 100` on batch=1 with realistic ticket lengths.
No exceptions. This is a production constraint, not a soft preference.

## Soft Score Formula

```
Cal = 0.6 * (1 - min(ECE, 0.10) / 0.10) + 0.4 * (1 - min(Brier, 0.25) / 0.25)
Lat = 1.0 if p95_latency_ms <= 100, else exp(-(p95_latency_ms - 100) / 40)

Score = 0.20 * Accuracy + 0.40 * MacroF1 + 0.25 * Cal + 0.15 * Lat
```

## Weight Rationale

- **MacroF1 (0.40)**: Largest weight. Support labels are imbalanced. Accuracy
  is easy to game by predicting the majority class. F1 forces performance
  across all 5 sentiment classes.
- **Calibration (0.25)**: Explicit because recent uncertainty work shows
  reliability can improve without serving cost, and production customer-service
  systems need trustworthy confidence scores for routing.
- **Accuracy (0.20)**: Standard headline metric. Lower weight than F1
  because of class imbalance.
- **Latency (0.15)**: Continuous penalty above 100ms p95. Production
  failures show up in the tail, so p95 matters more than mean.

## Additional Hard Gates

- Accuracy > 80% (above trivial baseline for 5 classes)
- Permutation test p-value < 0.10
- Model not collapsed (prediction entropy > 0.5 bits)
- Cross-validation: >50% of folds improve over baseline

## Side Metrics (Tracked, Not Scored)

- Negative/frustrated-ticket F1 (the class that matters most operationally)
- NLL (for model comparison)
- AURC / risk-coverage (for abstention analysis)
- Predictive set size (for conformal prediction experiments)
- QWK (for ordinal sentiment experiments)

## Verdict Thresholds

- `score >= champion_score`: PROMOTE
- `score >= champion_score - 0.03 AND score >= 0.50`: MARGINAL
- Otherwise: REJECT

Tighter threshold (0.03 vs default 0.05) because F1 improvements of 0.5%
are meaningful in this domain.
