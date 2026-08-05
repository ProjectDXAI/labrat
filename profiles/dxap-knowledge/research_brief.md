# Research brief — executable bibliography and retrieval policy

## What we want to learn

Given a compiled knowledge base — mechanisms, assumptions, observable signatures, deterministic methods, decision-relevance cards — **which retrieval policy puts the right thing in front of a decision, and knows when to stay quiet?**

The chain this lab serves is:

```
source -> mechanism -> assumptions -> observable signature
       -> deterministic test -> decision relevance -> realized outcome
```

A passage from a book tells an agent that order flow may contain information. A compiled concept card tells it under what assumptions that holds, which observables separate informed from mechanical flow, which tested function to run on the data actually available, over what horizon the prediction applies, what would falsify it, whether it bears on entry, sizing, exit or abstention, and which source anchors support it.

## Why this is worth running as a lab

Because the naive answer is measurably bad and the failure is invisible without a scoreboard.

Plain similarity retrieval over the same material scores a perfect hit rate on our trial set — and a precision of 0.24, zero counterevidence, and it answers **every** inapplicable context, including one timestamped before its sources were written. It looks like it is working. Every packet contains the right card, buried in four wrong ones, with nothing that would argue against any of them.

The interesting variation is therefore not "does retrieval help" but *which structural discipline is doing the work*: hard filters, decision-value re-ranking, counterevidence expansion, abstention calibration, or context economy.

## Baseline

`baseline_raw_similarity`: top-5 by text similarity, no filters, no expansion, no abstention. Every family has to beat it on precision, abstention and counterevidence — not on hit rate, which it already maxes.

## Metrics

- `search_eval` — hit rate: was the analyst's concept in the packet?
- `selection_eval` — `0.6 × precision + 0.4 × (1 − false abstention rate)`: serving mostly the right thing without going silent when something applied.
- `final_eval` — share of the diagnosed problem map the policy actually surfaced across the trial set.

Two decisive challenges, chosen because similarity scoring cannot win them:

- `non_applicability` — correct abstention on contexts where nothing applies. A nearest neighbour is always available; only structure can decide there isn't one worth serving.
- `counterevidence_coverage` — packets carrying a contradicting concept, a load-bearing assumption, or a known failure mode.

## What good looks like

- `structural_filtering` should own `non_applicability`. Nothing else can see that the required observables are absent or that the source postdates the decision.
- `decision_value_rerank` should lift precision without costing hit rate.
- `counterevidence_expansion` should own `counterevidence_coverage` and keep it at small packet sizes.
- `abstention_calibration` has to hold both ends: a policy that buys abstention accuracy with a high false-abstention rate is cheating, and `selection_eval` will price that.
- `context_economy` should match the wide policies at lower token cost, or admit that packet size was never the constraint.

## What this lab cannot tell you

This is Gate 1, offline. It measures retrieval quality against expert labels. It does **not** measure:

- **Gate 2, behaviour change.** Whether real decision traces change, and for defensible reasons, needs the production context and a *sham* arm — plausible but unrelated cards, matched for length and style — to separate knowledge from the generic effect of making the model deliberate longer.
- **Gate 3, prospective economics.** Whether it pays needs a randomized native trial with branch-isolated paper accounts, strict as-of availability, positions marked at horizon, no policy update before the batch matures, and inference clustered at the unit of randomization.

The attribution ledger (`scripts/ledger.py`) holds the schema for both, and refuses to compute an effect on unmatured outcomes or an unfrozen batch. Do not report a Gate 1 win as evidence of alpha. It is evidence that the retrieval layer is not obviously broken, which is a precondition, not a result.

## What we are not doing in this lab

- No model fine-tuning. Structured external memory first; weight adaptation only after retrieval proves incremental value.
- No graph retrieval as the live default. The graph is the research control plane and the source of counterevidence; the live data plane is filtered hybrid retrieval.
- No live self-modifying retrieval. `historical_utility` reads a posterior written by the ledger from matured, frozen batches — never from results inside the current batch.
- No cards without source anchors, and no verbatim quotes from sources whose rights do not permit them. The SERVABLE gate blocks both.
