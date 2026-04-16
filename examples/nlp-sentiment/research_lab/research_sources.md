# Research Sources

## src_001
- source: "Operational sentiment systems frequently get their cheapest gains from feature-space choices before heavier model changes."
- why it matters: motivates a dedicated cheap-probe family for text representation.
- linked families:
  - text_representation

## src_002
- source: "Linear SVM and logistic regression remain strong small-data text baselines; Naive Bayes is a useful low-complexity comparator."
- why it matters: motivates a classifier family that can mutate locally without changing the whole pipeline.
- linked families:
  - classifier_search

## src_003
- source: "Feature improvements and classifier improvements often stack, but calibration only pays off once the frontier is stable enough."
- why it matters: motivates a crossover family instead of treating calibration as a standalone first-wave search axis.
- linked families:
  - fusion_frontier

## Negative space
- source: "Large-model and retrieval-heavy paths are intentionally excluded from this example."
- what it ruled out: no hosted APIs, no GPU-only models, no complex retrieval system in the reference lab.
