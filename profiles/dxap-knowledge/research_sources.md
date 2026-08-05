# Research sources

This lab consumes the corpus lab's output. Scaffold both profiles together:

```bash
labrat new my_dxap --profile=quant-finance-corpus --profile=dxap-knowledge
```

`knowledge/` holds the compiled objects; `corpus/` holds the bibliography they anchor to. Source ids in `source_passage_ids` resolve against `corpus/bibliography.yaml`, and the SERVABLE gate fails a card that cites something not in it.

## What is compiled here

| Store | Contents |
|---|---|
| `knowledge/problems.yaml` | The problem map: diagnosed agent failure modes, grouped into four verticals. Everything else is ranked by proximity to these. |
| `knowledge/concepts.yaml` | 16 concept cards across the four verticals, each with mechanism, assumptions, observables, expected signature, failure modes, counterevidence and source anchors. |
| `knowledge/hypotheses.yaml` | 8 hypothesis cards: what each concept predicts ex ante, its null, the operator that measures it, the cost model, and what would kill it. |
| `knowledge/methods.yaml` | 8 bindings from concepts to versioned implementations in `scripts/methods.py`, pinned by version so a numerical change fails validation. |
| `knowledge/decision_relevance.yaml` | 18 cards mapping concepts to decision types, each carrying both supporting and opposing evidence. |
| `knowledge/trials.yaml` | 14 labelled decision contexts, 4 of them inapplicable on purpose. |
| `knowledge/policies.yaml` | The retrieval arms, including the `raw_similarity` control. |

## Provenance and its limits

The concept cards are **our own account** of each mechanism, written from working knowledge of the sources and anchored to them at chapter or section level. They are not extracted text, and the anchors have not been page-verified. Treat them as a seed of the right shape rather than a checked compilation:

- Anchors point at plausible chapters or sections. Verify against the physical source before citing one externally.
- No card carries a verbatim quote. Most of the anchored sources are `reference_only` in the corpus, and the gate would reject a quote from them.
- Confidence values are analyst priors, not measured track records. `historical_utility` shrinks them toward 0.5 until the ledger has matured outcomes to replace them.

## The four verticals

1. **Execution, adverse selection and fee drag** — order flow imbalance, queue position, Kyle's lambda, concave impact, optimal execution, inventory-skewed quoting, and the cost floor a signal must clear.
2. **Optimal stopping, exits and giveback** — continuation value against exit value, and the persistence argument that contradicts it.
3. **Information arrival and structural change** — recursive filtering, sequential change detection, and gradual absorption of catalysts.
4. **Prediction-market and cross-market probability formation** — scoring-rule pricing, liquidity moves masquerading as belief updates, and cost-adjusted cross-venue consistency.

## Where the next cards should come from

The corpus lab's `compile-queue` ranks this for you:

```bash
python scripts/knowledge.py compile-queue --limit 25
```

It seeds a personalized PageRank on the problem map, so a source is ranked by proximity to a problem we actually have — plus mechanistic density, likely pretraining scarcity (an access-friction proxy, never an observation), cross-bucket bridge value, and non-redundancy with what is already compiled. It emits the reading queues at chapter level, not as a flat book list, and reports the minimum set of sources covering the problem map.

Known gaps in the seed, in rough priority order:

- Nothing compiled yet for funding-rate mechanics on perpetuals, which touches three problems.
- Queue-position concepts are specified but unimplemented; the fill-probability method is the obvious next tool.
- Absorption has no method binding, so it can inform reasoning but cannot be measured.
- No concepts yet from the queueing or information-theory buckets, despite both being mapped in the corpus.
