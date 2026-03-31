# Data Splitting: Principles and Pitfalls

How to split data for training, validation, and testing in labrat experiments. These principles apply to any temporal prediction problem, not just financial markets.

---

## The Core Problem

A strategy that works on your validation set but fails on held-out data is worse than useless -- it wastes budget and creates false confidence. The most common cause: your val set is too similar to your training set.

**Observed failure modes from labrat deployments:**

| Domain | Val performance | Test performance | Root cause |
|--------|----------------|-----------------|------------|
| BTC microstructure | Sharpe 0.25 | Sharpe 0.10 | Signal decay over time |
| Crypto momentum | Sharpe 2.51 (bull) | Sharpe 0.04 (flat) | Regime-specific strategy |
| Prediction markets | Sharpe 4.82 | Sharpe 1.12 | Election-dominated val period |

In every case, the val period was an optimistic sample of the problem space. The fix is not better models. The fix is better splits.

---

## Principle 1: Split by Decision Time, Not Outcome Time

If your data has two timestamps (when a decision was made vs when the outcome resolved), split by the **decision timestamp**.

**Why**: Splitting by outcome timestamp creates a subtle leak. A decision made in January that resolves in March should be in the "January" bucket, not "March." If you split by resolution time, the January decision leaks into your March test set -- the model saw the decision context during training but you think it's being tested on it.

**Examples:**
- Prediction markets: split by `snapshot_time` (when the bet was placed), not `close_time` (when the market resolved)
- Medical diagnosis: split by `exam_date`, not `diagnosis_confirmation_date`
- Insurance claims: split by `policy_start_date`, not `claim_resolution_date`

**In labrat**: The `branches.yaml` should specify which timestamp field to use for splitting:
```yaml
production_baseline:
  config:
    data:
      split_field: "snapshot_time"  # NOT "close_time"
```

---

## Principle 2: Your Holdout Must Include Different Regimes

The single most dangerous split is "train on the first 80%, test on the last 20%." If the last 20% happens to be the same regime as training (e.g., both are bull markets, both are calm periods, both are election years), your test set tells you nothing about generalization.

**The regime test**: Before declaring your split valid, ask:
- Does the test period contain at least one regime the training period doesn't?
- Does the test period include at least one "bad" period (market downturn, seasonal trough, anomalous event)?
- If you trained on a favorable period and test on a favorable period, your results are optimistic by construction.

**Concrete approach**: Split into 3+ segments and ensure regime diversity:

```
Period A (train): 2024-Q1 to 2024-Q3  [bull market]
Period B (val):   2024-Q4 to 2025-Q1  [transition]
Period C (test):  2025-Q2 to 2025-Q4  [bear market]  <-- different regime!
```

If all three periods are the same regime, you haven't tested generalization. You've tested interpolation.

**In labrat**: Add an `assumption_audit` branch that explicitly tests for regime dependence:
```yaml
assumption_audit:
  experiment_type: "diagnostic"
  search_space:
    - delta_key: "audit_type"
      values:
        - name: "regime_holdout"
          description: "Test champion on opposite-regime holdout data"
```

---

## Principle 3: Purge Gaps Prevent Autocorrelation Leakage

Adjacent data points are correlated. A model trained on data from Monday will perform better on Tuesday's test set than on data from three months later -- not because it's a good model, but because Monday and Tuesday share the same local context.

**The fix: purge gaps (also called embargo periods)**

Insert a gap between your training data and your test data. No data from the gap is used for either training or testing. The gap size should match the decorrelation time of your data.

| Data type | Typical decorrelation | Recommended gap |
|-----------|----------------------|-----------------|
| High-frequency trading (tick) | 1-2 days | 2 days |
| Daily prices | 1-4 weeks | 30 days |
| Monthly economic indicators | 3-6 months | 6 months |
| Annual survey data | 1-2 years | 1 year |

**In labrat**: Specify the dead zone in your config:
```yaml
splits:
  dead_zone_days: 2.0  # gap between train and test
```

The BTC microstructure lab discovered that a 2-day dead zone was sufficient (1-day was too short, 3-day was identical to 2-day). This is a parameter your lab should test.

### Embargo vs Purge Gap

These are related but distinct concepts (Lopez de Prado, 2018):

**Purging** removes training observations whose label span overlaps with any test observation. If your label horizon is 60 seconds and a test observation starts at time T, purge all training observations in [T-60, T+60] because their labels overlap with the test window.

**Embargo** is an additional gap on top of purging that accounts for serial autocorrelation in features. Even after purging, a feature computed at T-61 may be highly correlated with a feature at T (within the test window) due to rolling-window calculations.

**Sizing the embargo**: max(label_horizon, longest_feature_lookback_window). If your features use a 300-second rolling window and your label is a 60-second markout, embargo >= 300 seconds. Conservative: 2x the longest autocorrelation lag in your features (measure with an ACF plot).

---

## Principle 4: Walk-Forward Validation, Not Random Splits

For temporal data, never use random cross-validation. Use walk-forward (expanding or rolling window) validation:

```
Window 1: Train [------] Test [--]
Window 2: Train [--------] Test [--]
Window 3: Train [----------] Test [--]
Window 4: Train [------------] Test [--]
```

**Expanding window**: training set grows each window. Better when more data always helps.
**Rolling window**: training set stays the same size. Better when recent data is more relevant than old data.

**The walk-forward gate**: A strategy must be positive in >50% of walk-forward windows to be considered robust. A strategy that works brilliantly in 2 windows and fails in 4 is regime-dependent.

**In labrat**: Walk-forward is a first-class concept. The orchestrator's scoring formula uses it:
```
R (robustness) = positive_windows / total_windows
G (generalization) = 1 - fold_std / fold_mean
```

If R < 0.50 (fewer than half the windows are positive), the experiment is auto-rejected by the hard gate.

---

## Principle 5: Features Must Not See the Future

Every feature must be computed from data available at decision time. This sounds obvious but is the #1 source of data leakage in practice.

**Common leaks:**
- **Normalization with full-dataset statistics**: Z-scoring features using the mean/std of the entire dataset (including test) leaks test distribution into training. Fix: compute statistics from training data only.
- **Family/group features across time**: Computing "how many items in this category" using all temporal snapshots means early items know about later items. Fix: compute per-snapshot using only data available at that point.
- **Label encoding with future data**: If your label encoder was fit on the full dataset, rare categories that only appear in test get a proper encoding in training. Fix: fit encoders on training data only.
- **Lag features without sufficient gap**: A 1-bar lag in high-frequency data may still be within the autocorrelation window. Fix: use dead zones that exceed the autocorrelation time.

**In labrat**: The constitution's hard gates should include a leakage check. The `assumption_audit` branch can run a diagnostic:
```yaml
- name: "feature_leakage_check"
  description: "Retrain with shuffled future labels. If accuracy drops to baseline, features are clean."
```

---

## Principle 6: Track Val/Test Decay Systematically

Every experiment that produces both a validation score and a test score should log the **decay ratio**:

```
decay_ratio = test_metric / val_metric
```

Track this across all experiments. The rolling average tells you about your methodology:

| Rolling decay ratio | Interpretation |
|--------------------|----------------|
| 0.90 - 1.10 | Healthy. Val predicts test well. |
| 0.70 - 0.90 | Moderate decay. Normal for noisy domains. |
| 0.50 - 0.70 | Concerning. Check for leakage or regime shift. |
| < 0.50 | Broken. Stop and fix methodology before running more experiments. |
| > 1.10 | Suspicious. Test might be easier than val (selection bias in test set). |

**In labrat**: The judge.py computes `decay_ratio` automatically and logs it. If the rolling average drops below 0.50, the dashboard shows a warning and the orchestrator triggers a methodology audit.

---

## Principle 7: Multiple Holdout Sets at Different Time Periods

One holdout set is not enough. You need at least two, from different time periods and ideally different regimes:

```
Train:     [Jan-Jun 2024]
Val:       [Jul-Sep 2024]  -- recent, probably similar regime to train
Holdout A: [Oct-Dec 2024]  -- slightly different, immediate OOS
Holdout B: [Q2 2025]       -- distant, different regime
Holdout C: [Q4 2025]       -- even more distant, stress test
```

Your champion must perform on ALL holdout sets, not just the most recent one. A strategy that works on Holdout A but fails on B and C is regime-dependent.

**In labrat**: Define multiple holdout periods:
```yaml
periods:
  train:
    start: "2024-01-01"
    end: "2024-06-30"
  discovery:
    start: "2024-07-01"
    end: "2024-09-30"
  holdout_near:
    start: "2024-10-01"
    end: "2024-12-31"
    purpose: "Immediate OOS, similar regime"
  holdout_far:
    start: "2025-04-01"
    end: "2025-06-30"
    purpose: "Distant OOS, different regime. MANUAL ONLY."
```

The `MANUAL ONLY` holdout is never touched by the automated loop. It's reserved for the final validation before deployment.

---

## Principle 8: The Bear Market Test

For any strategy that involves prediction (trading, forecasting, recommendation), always ask: "What happens when conditions are bad?"

This is not financial advice. The principle is general: your model will encounter periods where the underlying distribution shifts. If you only test during favorable conditions, you don't know if your model has genuine skill or is just riding a favorable environment.

**General version**: test on the worst 25% of your data (lowest target variable, highest volatility, most class imbalance) separately from the best 75%. If the strategy only works on the "good" subset, it's not robust.

**In labrat**: Add a diagnostic experiment:
```yaml
- name: "adverse_regime_test"
  description: "Test champion on worst-quartile data subset only"
```

---

## Labrat Integration

### Default Splits in branches.yaml

```yaml
production_baseline:
  config:
    data:
      split_field: "decision_time"  # field to split on
    splits:
      train_frac: 0.70
      val_frac: 0.15
      test_frac: 0.15
      dead_zone_days: 2.0  # purge gap between adjacent splits
    walk_forward:
      enabled: true
      min_train_days: 30
      test_window_days: 7
      dead_zone_days: 2.0
      expanding: true  # or rolling
```

### Assumption Audit Branch

```yaml
assumption_audit:
  experiment_type: "diagnostic"
  initial_budget: 10
  search_space:
    - delta_key: "audit_type"
      values:
        - name: "split_field_check"
          description: "Compare decision_time vs outcome_time splits"
        - name: "regime_holdout"
          description: "Test on opposite-regime data"
        - name: "feature_leakage"
          description: "Shuffle future labels, check feature independence"
        - name: "dead_zone_sensitivity"
          description: "Test dead_zone at 0.5d, 1d, 2d, 3d"
        - name: "adverse_regime"
          description: "Test on worst-quartile data subset"
```

### Decay Tracking in Judge

The judge automatically computes and logs `decay_ratio` for every experiment with both val and test metrics. The orchestrator monitors the rolling average and triggers a methodology audit if it drops below 0.50.

---

## Checklist: Before Running a Lab

- [ ] Split field is the decision timestamp, not the outcome timestamp
- [ ] Test period includes at least one different regime from training
- [ ] Dead zone is set (and ideally tested at multiple values)
- [ ] Walk-forward validation is enabled
- [ ] Features are computed from training data only (no full-dataset normalization)
- [ ] At least one holdout set is reserved for manual-only final validation
- [ ] Decay ratio tracking is enabled in the judge
- [ ] An assumption_audit branch is included with regime holdout and leakage checks

---

## Advanced: Combinatorial Purged Cross-Validation (CPCV)

Standard walk-forward produces one backtest path. CPCV (Lopez de Prado, 2018) produces a **distribution** of paths, giving statistical power to detect overfitting.

1. Divide data into N chronological groups (6-10 is typical)
2. For each combination of k test groups, the remaining N-k form training
3. Apply purging and embargo between each train/test boundary
4. This gives (k/N) * C(N,k) unique backtest paths

**What it gives you**: A full distribution of out-of-sample performance. If the 5th percentile is deeply negative, your strategy is fragile even if the median looks good. Target 100+ paths for a stable distribution.

**In labrat**: CPCV is optional but recommended for the final champion validation before deployment. Add it as a diagnostic experiment in the assumption_audit branch.

---

## Advanced: Preventing Preprocessing Leakage

A separate and often-missed leakage channel:

- **Normalization/scaling**: Fit the scaler on training data ONLY. Apply the frozen transform to val/test. Computing mean/std on the full dataset leaks test-set statistics.
- **Feature selection**: Select features using training data ONLY. Mutual information or importance scores computed on the full dataset bias selection toward features that happen to work on the test set.
- **Imputation**: Fit imputation parameters (median, mode, KNN neighbors) on training data ONLY.
- **Sequence generation**: For recurrent/transformer models, construct input sequences AFTER splitting. Pre-split sequence generation allows windows to straddle boundaries (confirmed by a 2025 study showing 20% RMSE inflation from this mistake).
- **Threshold tuning**: Any threshold discovered on a dataset can only be tested on a DIFFERENT dataset. Finding a threshold on data X and testing on data X is double-dipping.

---

## Advanced: Point-in-Time Feature Correctness

Every temporal prediction has at least three timestamps per observation:

- **Feature time (t_feature)**: When the features became available. A rolling 300s volatility at time T uses data from [T-300, T].
- **Prediction time (t_predict)**: When you make the prediction. At t_predict, you may only use features where t_feature <= t_predict.
- **Label resolution time (t_label)**: When the label becomes known. If predicting a 60s forward return starting at T, the label resolves at T+60.

**Rule**: At prediction time T, only use features where t_feature <= T and labels where t_label <= T for training. Feature stores (AWS SageMaker, Databricks, Feast) enforce this via "as-of" temporal joins.

**Common violations**:
- Group features (family_size, category_count) computed across ALL time snapshots instead of per-snapshot
- Rolling features where the window extends past the split boundary
- Joining feature tables on exact timestamp match instead of "most recent as of" join

---

## Sources

- Lopez de Prado (2018): Advances in Financial Machine Learning -- purging, embargo, CPCV
- [Hidden Leaks in Time Series: LSTM Leakage Study (arXiv, 2025)](https://arxiv.org/html/2512.06932v1)
- [Nature: Information Leakage in Time Series Prediction (2024)](https://www.nature.com/articles/s41598-024-80018-9)
- [Analytics Vidhya: Time Series Cross-Validation (2026)](https://www.analyticsvidhya.com/blog/2026/03/time-series-cross-validation/)
- [skfolio CombinatorialPurgedCV](https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html)
