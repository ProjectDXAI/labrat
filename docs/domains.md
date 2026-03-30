# Domain Adaptation

| Domain | Primary Metric | Typical Branches | Red Team |
|--------|---------------|-----------------|----------|
| NLP | F1, accuracy, BLEU | architecture, data, objectives, hyperparams | Shuffled labels |
| Vision | mAP, FID, accuracy | backbone, augmentation, resolution, loss | Random crops |
| RL | Episode return | architecture, reward, exploration, schedule | Random actions |
| Trading | Sharpe, IC | features, model, sampling, execution | Shuffled labels |
| Drug discovery | Binding affinity | molecular representation, scoring, search | Decoy molecules |
| Recommendation | NDCG, CTR | embedding, architecture, sampling, features | Random recs |

## Scoring Formula Weights by Domain

**Classification**: Weight F1/accuracy highest (0.40), robustness second (0.25).

**Trading**: Weight deployment Sharpe highest (0.40), walk-forward consistency second (0.25).

**Generative**: Weight human-eval proxy highest, calibration/diversity second.

**RL**: Weight mean episode return highest, variance penalty second.

Customize `constitution.md` weights for your domain. The default (0.40 deployment + 0.25 robustness + 0.15 generalization + 0.10 calibration + 0.10 novelty - 0.05 complexity) works for most supervised learning tasks.
