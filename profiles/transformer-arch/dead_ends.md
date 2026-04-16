# Known dead ends — tiny transformer architecture search

Do not re-explore these unless a cheap probe convincingly contradicts them.

## Scaling width without depth

Raising `d_model` past 128 on this corpus has repeatedly produced a memorization regime: `search_eval` spikes, `holdout_generalization` regresses. If a probe shows this pattern on a wider model, mark it invalid-fast and do not budget a deeper sweep along that axis.

## Excessive warmup

`warmup_steps > 25` on a 100-step training run means most of the LR schedule is under-trained. This is a dead end for the transformer lab. The `optimizer_search` family caps warmup at 25 in its mutation axes.

## Dropout as a first resort

On character-level tiny-corpus training, dropout above 0.1 consistently hurts both training-distribution fit and held-out perplexity. Do not add dropout probes until the base family is structurally healthy.

## Removing LayerNorm

Attempted once in an earlier run. Loss diverges within the first ten steps. Mark as `failure_class: nan` if any worker tries it.

## Token-level embeddings

This is a character-level lab. Token-level embeddings require a tokenizer, which becomes its own search axis and blows the scope of this lab. If a frame_break is triggered, consider it separately — do not fold it into the existing families.
