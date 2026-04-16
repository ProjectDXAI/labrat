# Research sources — tiny transformer architecture search

These are pointers we seeded the lab with. The supervisor and research_scout may add more as the lab runs.

## Core building blocks

- Vaswani et al., "Attention is All You Need" (2017) — https://arxiv.org/abs/1706.03762. Reference for self-attention + positional encoding.
- Karpathy, nanoGPT — https://github.com/karpathy/nanoGPT. Our baseline is a heavily trimmed nanoGPT-style block.
- TinyShakespeare corpus — https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt. Our `data/train_corpus.txt` is derived from a short public-domain passage in that spirit.

## Why character-level on tiny data

Character-level modeling removes the tokenizer as a search variable and lets the search focus on architecture axes. A tiny corpus keeps runs CPU-fast and exposes overfitting quickly, which is exactly the failure mode the decisive challenges are designed to catch.

## Relevant prior findings to avoid rediscovering

- Raw scaling of width without depth tends to overfit tiny corpora before it generalizes.
- LR schedules with excessive warmup waste budget on tiny models.
- Dropout helps much later than intuition suggests on character-level tasks.

These are seeded in `dead_ends.md` so the supervisor can skip them unless probes show otherwise.

## What the research_scout should fetch if activated

If the frame_break phase fires, the research_scout should look for:

- recent work on small-model generalization under distribution shift,
- attention variants (e.g., multi-query / grouped-query) that change the generalization-per-parameter curve,
- regularization approaches specific to tiny-corpus training (not large-scale pretraining).
