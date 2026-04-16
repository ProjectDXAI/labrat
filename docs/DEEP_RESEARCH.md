# Deep Research with labrat vNext

The runtime is designed around three system constraints:

1. **Throughput matters**: serial search wastes good operators.
2. **Evaluation quality matters**: noisy self-reported metrics poison long runs.
3. **Operators matter**: one-shot prompts are not enough for open-ended work.

## The design pattern

Phase 0 defines:

- family graph
- evaluation protocol
- worker pool expectations
- search ladder
- dead ends and negative space

The runtime then executes steady-state asynchronous search:

- families spend credits to create descendants
- workers run descendants independently
- the evaluator scores them externally
- the frontier mints new credits only for stable progress
- decisive challenge wins mint extra status when a family lands a hard held-out test that was not already the inner search objective

## File-as-Bus continuity

The supervisor should not keep re-reading the whole lab from scratch.

Use durable artifacts as the system of record:

- `coordination/workspace_map.md` for navigation
- `coordination/prioritized_tasks.md` for concise control intent
- `coordination/implementation_log.md` for debugging and repair notes
- `coordination/experiment_log.md` for compact experiment carry-forward

This is progressive disclosure: control stays light, while detailed state remains available on demand.

## Search ladder

Every serious lab should encode:

1. cheap probes
2. mutation / local exploitation
3. implementation audit
4. frame break
5. expansion

If a lab jumps directly from “plateau” to “invent a new family,” it usually wastes a lot of signal.

## Lakatos as a heuristic

This is not a strict implementation of Lakatos, but it is a good way to think about the runtime.

A family behaves like a provisional research programme:

- probes and mutations work inside the current programme
- audit distinguishes a bad implementation from a bad direction
- frame break and expansion are what you do when local repairs have become degenerating

The useful threshold is not “did one run fail?” It is “is this family still paying for more attention?” Lakatos's shorthand for that distinction is that a programme [“is progressive if it is both theoretically and empirically progressive, and degenerating if it is not”](https://plato.stanford.edu/archives/fall2020/entries/lakatos/).

The practical version inside `labrat` is stricter than “benchmark score went up.” A strong family should also win a decisive held-out challenge that was not already baked into the local hill-climb. That is the closest runtime analogue to a novel, risky prediction.

## External consistent evaluation

`evaluation.yaml` is the real replacement for the old constitution-style scoring file.

Use it to define:

- `search_eval`
- `selection_eval`
- `final_eval`
- `prediction_tests`
- fixed splits or fixed seeds
- rerun policy
- invalid-fast thresholds

This does not make the lab secure against a hostile actor by default. It does make the evaluation contract consistent and external to the worker.

## Async steady-state search

The runtime is not cycle-based.

- the supervisor tops up the queue
- workers lease jobs when free
- completed candidates are rerun or promoted without waiting for a global barrier

This is what makes the funding loop useful at scale instead of just tidy on paper.

## References and provenance

These ideas did not come from nowhere, and the repo should say that plainly.

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) is the clearest immediate ancestor for the agent-run experiment loop pattern.
- [AIRA_2](https://arxiv.org/abs/2603.26499) is the strongest direct influence on the population-runtime direction: throughput, evaluation quality, and operator quality as systems problems.
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018) is the source for the File-as-Bus and progressive-disclosure refinements added here.
- [Lakatos](https://plato.stanford.edu/archives/fall2020/entries/lakatos/) is included only as a heuristic for progressive versus degenerating local search, not as a literal implementation claim.
