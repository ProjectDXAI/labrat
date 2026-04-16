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

## Search ladder

Every serious lab should encode:

1. cheap probes
2. mutation / local exploitation
3. implementation audit
4. frame break
5. expansion

If a lab jumps directly from “plateau” to “invent a new family,” it usually wastes a lot of signal.

## External consistent evaluation

`evaluation.yaml` is the real replacement for the old constitution-style scoring file.

Use it to define:

- `search_eval`
- `selection_eval`
- `final_eval`
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
