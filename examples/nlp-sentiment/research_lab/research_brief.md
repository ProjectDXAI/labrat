# Research Brief

Mission:
Maximize macro F1 on a five-class sentiment dataset using only CPU-friendly sklearn pipelines.

Baseline:
Word unigram TF-IDF plus logistic regression.

Target:
Beat the baseline on both search and held-out selection splits without relying on noisy one-off wins.

Constraints:
- CPU only
- local fixed dataset file
- fast enough for repeated reruns
- no model self-reporting of canonical scores

Search ladder:
1. cheap probes on text representation and classifier choice
2. mutation around the best local family
3. implementation audit for invalid-fast or unstable near-miss candidates
4. frame break if both families plateau
5. expansion if a frame-break memo says the current families are structurally incomplete

Family graph summary:
- `text_representation` asks what the model sees.
- `classifier_search` asks how the decision boundary should be fit.
- `fusion_frontier` combines winners from the first two families and calibrates them.
