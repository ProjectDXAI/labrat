# Research brief — tiny transformer architecture search

## What we want to learn

Can a small character-level transformer (a few hundred thousand parameters, CPU-trainable in under a minute) generalize from one text distribution to a genre-shifted held-out distribution? If so, which axes of the architecture (depth, width, heads) carry the generalization, and which axes matter only for fitting the training distribution?

## Why this is worth running as a lab

On a tiny corpus, the easiest wins come from either overfitting the training distribution or doing the opposite — staying so small the model can't learn anything useful. Both failure modes look fine on standard validation loss. Only a held-out distribution-shifted challenge reveals whether a family is actually discovering transferable structure. That maps cleanly onto labrat's decisive-challenge mechanism.

## Baseline

A 2-layer, 2-head, d_model=32 character transformer trained for 100 steps with LR=3e-3 on `data/train_corpus.txt`. Evaluated on three splits:

1. `search` — a held-out fraction of the training corpus (in-distribution).
2. `selection` — a different held-out fraction, used for promotion.
3. `final` — a sealed slice, used for the final_eval metric.

Plus two decisive held-out challenges:

1. `holdout_generalization` — perplexity on `data/holdout_corpus.txt` (a different text distribution).
2. `holdout_stability` — agreement between intermediate-checkpoint held-out perplexity and final-checkpoint held-out perplexity, to catch families that spike then collapse.

## What good looks like

A family should earn credits for:

- lifting `selection_eval` (in-distribution generalization),
- *and* winning `holdout_generalization` over the baseline,
- *and* not regressing on `holdout_stability`.

A family that only improves `search_eval` (training-distribution fit) without winning any held-out challenge is probably overfitting. The prediction_tests will catch it.

## What we are not doing in this lab

- No large-model training. This is a tiny-corpus, CPU-budget lab.
- No pretraining from external checkpoints.
- No benchmark leaderboards. The decisive challenges are *this lab's* held-out corpora, not GLUE / WMT / LLM benchmarks.
- No architecture exotica that requires custom kernels. GELU / ReLU / SiLU activations, scaled dot-product attention, LayerNorm — that's the palette.

## Modes

`scripts/run_experiment.py` in this profile has two modes, selected by `candidate.resolved_config.training.mode`:

- `"synthetic"` (default in the baseline) — stdlib-only surrogate that produces realistic-shape metrics and a checkpoint series from the config. Lets the runtime loop, evaluator, mutation worker, and Pareto helper all be exercised with no torch install. This is how `make smoke PROFILE=transformer-arch` verifies the end-to-end path.
- `"real"` — pure-PyTorch character-level tiny transformer with manual training loop. Uncomment `torch>=2.0` in `requirements.txt`, install it, then flip the baseline's `training.mode` to `"real"` (or override it per-family in `branches.yaml`). Same result contract, same interim checkpoint format; the runtime does not know which mode produced a candidate.

Switch to real mode only after you are confident the search space in `branches.yaml` is worth real compute. Synthetic first, real second.
