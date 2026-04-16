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
