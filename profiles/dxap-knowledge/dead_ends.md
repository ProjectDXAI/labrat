# Known dead ends — executable bibliography

Do not spend credits here unless a cheap probe convincingly contradicts the entry.

## Raw passage RAG as the primary layer

Already measured on this trial set: perfect hit rate, precision 0.24, zero counterevidence, and it answers every inapplicable context including one dated before its sources existed. It stays in the lab as the baseline arm and as an experimental control. It is not a candidate for the live path.

## Graph retrieval as the live default

The graph is the research control plane — discovery, assumptions, contradictions, community structure — and the source of the one-hop counterevidence expansion. Making it the default live retrieval mechanism pulls in irrelevant neighbourhoods and adds latency for multi-hop capability that a decision context rarely needs. `expand_hops` above one is a dead end until a trial shows a decision that needs it.

## Fine-tuning before retrieval is measured

Continued pretraining on finance material is not a candidate in this lab, and should not be a candidate anywhere until the gates identify which knowledge families actually change behaviour and improve net outcomes. Otherwise the spend teaches the model a large amount of material without knowing whether it became more capable, more active, more expensive — or more profitable.

## Self-modifying retrieval inside a batch

Updating `historical_utility` from results in the current rollout batch contaminates the comparison it is supposed to inform. The ledger refuses to compute an effect on an unfrozen batch for this reason, and `knowledge.py` only reads a posterior that the ledger wrote from matured outcomes.

## Cards without counterevidence

A concept card with no contradicting concept and no alternative explanation fails the SERVABLE gate. This is not a style preference: a knowledge layer that can only confirm will confirm whatever the agent already wanted to do, and it will do so with citations attached.

## Decision-relevance cards that state rules

"Close after giving back a third of maximum favourable excursion" is a rule with a book stapled to it. The card should state the operator and the comparison — estimate the conditional probability of a further favourable excursion given the state, compare continuation value against execution and opportunity cost — and let the agent decide. The validator lints for unconditional directive language.

## Hypotheses without a cost model

An ex-ante prediction with no cost model is not a testable trading claim, and validation rejects it. Most apparent short-horizon edges disappear into the round-trip floor; a hypothesis that cannot say what it must clear cannot be evaluated.

## Treating a Gate 1 win as alpha

Retrieval quality against expert labels is a precondition, not a result. Behaviour change needs Gate 2 with a sham arm; economics needs Gate 3, prospective, randomized, clustered, with matured outcomes. Reporting an offline hit rate as evidence that the corpus makes money is the specific failure this lab exists to avoid.
