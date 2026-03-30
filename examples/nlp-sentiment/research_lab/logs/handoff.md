# Handoff

## Cycles 1-43: Full Lab Run

43 cycles, 147 experiments, 5 red team checks (all PASS), 3 budget replenishments, 10 research scout alerts.

### Production Champion
**capstone_champ_5k_c25** (composite=0.8128, F1=0.3983)
TF-IDF bigrams + LogisticRegression(C=1.0, class_weight="balanced") + min_df=5 + max_features=5000

### Branch Champions (sorted by score)

| Branch | Champion | F1 | Score | Experiments |
|--------|----------|----|-------|-------------|
| capstone | champ_5k_c25 | 0.3983 | 0.8128 | 22 |
| ensemble | voting_bal_c25 | 0.4014 | 0.8096 | 10 |
| objectives | bal_bigram_mindf5_c18 | 0.3945 | 0.8048 | 15 |
| features | 5k_c16 | 0.3640 | 0.7854 | 13 |
| preprocessing | stop_5k_c15 | 0.3621 | 0.7834 | 11 |
| model | svm_bigram_c14 | 0.3611 | 0.7780 | 15 |

### What the Market Found

**Axes that matter:**
1. class_weight=balanced (+0.10 F1, biggest single delta)
2. bigrams / ngram_max=2 (+0.05 F1)
3. max_features=5000 (LESS is MORE on small datasets)
4. min_df=5 (filter rare terms)
5. Soft voting ensemble (LR+SVM+LR at different C values)

**Axes that are flat:** max_features>10K, sublinear_tf, trigrams, char_wb, max_df, C regularization (0.1-10.0), all tree models

**Key finding:** 5K features outperforms 10K and 20K. On a training set of 8.5K samples, a smaller vocabulary reduces overfitting. The production champion uses 5K features with min_df=5, aggressively pruning the vocabulary.

**Ensemble insight:** Soft voting with balanced weights (F1=0.4014) has the highest raw F1 of any experiment, but its composite score (0.8096) is slightly below the capstone champion (0.8128) due to higher complexity penalty.

### Methodology Notes
- Permutation test on training data is biased for balanced logistic regression (memorizes training set)
- Several experiments with F1>0.39 were killed by p-value gate despite strong CV results
- Research scout flagged features, objectives, model, ensemble, capstone as stuck at various points

### Budget Remaining
features=37, model=37, preprocessing=39, objectives=31, ensemble=28, capstone=4

### Red Team History
Cycles 5, 10, 15, 20, 25, 30, 35, 40: all PASS (shuffled F1 < 0.20)
