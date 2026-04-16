# Tree Designer for labrat vNext

Design a research runtime, not just a list of branches.

Your output must be decision complete for a fresh agent that will operate the lab without extra human choices.

## Required outputs

You must produce:

1. `branches.yaml`
2. `dead_ends.md`
3. `research_brief.md`
4. `research_sources.md`
5. `evaluation.yaml`
6. `runtime.yaml`

## Design requirements

### 1. Family graph, not branch list

`branches.yaml` must define `families:`. Each family needs:

- `description`
- `scientific_rationale`
- `resource_class`
- `funding.initial_credits`
- `cheap_probes`
- `mutation_policy`
- `crossover_policy`
- `audit` triggers
- `frame_break` triggers

The tree must include:

- at least one cheap-probe-heavy family
- at least one mutation-heavy family
- at least one crossover-capable family

### 2. Search ladder

The design must explicitly encode this ladder:

1. cheap probes
2. normal exploitation
3. implementation audit
4. frame break
5. expansion

Do not skip directly from “one family plateaued” to “invent a new worldview” unless the cheap probes and audit logic are already exhausted.

### 3. Evaluation protocol

You must define `evaluation.yaml` with:

- `search_eval`
- `selection_eval`
- `final_eval`
- fixed split or fixed seed policy
- rerun policy for suspicious wins
- invalid-fast margin
- stability tolerance

This must be external-consistent:

- workers are not authoritative for scores
- the evaluator is
- search and selection signals are separate

### 4. Runtime protocol

You must define `runtime.yaml` with:

- worker pools by resource class
- checkpoint interval
- dispatch and funding rules
- crossover probability
- max lineage concurrency
- elite archive sizes
- plateau window

### 5. Negative space

`dead_ends.md` must name:

- dead approaches
- expensive but low-value directions
- what signal would be needed to revive them

### 6. Sources

`research_sources.md` must map each family to concrete sources and say what each source contributed.

## Heuristics

1. Use funding to reflect confidence, not equal fairness.
2. Put the cheapest orthogonal questions first.
3. Give the runtime a path to combine winners across families.
4. If a family could look invalid-fast for mechanical reasons, say so in the audit triggers.
5. If a family’s raw work floor will likely miss the target, force a frame-break trigger earlier.
