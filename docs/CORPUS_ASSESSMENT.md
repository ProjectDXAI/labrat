# What the corpus now claims, and where it argues with itself

Generated structure comes from `knowledge.py assess`; the reading of it is judgment and is marked as such. Run it yourself:

```bash
python scripts/knowledge.py assess --markdown --out ASSESSMENT.md
```

43 concepts, 22 method bindings, 19 hypotheses, 39 decision cards, 15 diagnosed problems. 63% of concepts rest on a source unit someone opened.

## The structural result worth having first

**Nothing load-bearing is unchecked.** Every anchor supporting two or more cards has been read. No method is bound to nothing, no concept floats free of a problem, and no card carries neither a contradicting card nor an alternative explanation. Those are the four ways this kind of store rots quietly, and none of them is happening.

That is a statement about the shape of the collection, not about whether any particular claim is true.

## Eight live disagreements

The corpus contains 18 contradiction pairs across 26 concepts, in 8 clusters. These are not defects. A cluster is a question the corpus has two defensible answers to, and each one is a research programme rather than a bug to be resolved by picking a side.

| Cluster | The question underneath it |
|---|---|
| `KC-EXEC-AC` ↔ `KC-IMPACT-CONFLATION` ↔ `KC-IMPACT-SQRT` ↔ `KC-INFO-KYLE` | **What is price impact and how does it scale?** Linear in signed volume over an interval, or concave in metaorder size? Both are measured, on different objects, and the corpus was conflating them until Tóth forced the distinction. |
| `KC-CRITICALITY-SCALING` ↔ `KC-HAWKES-CRITICALITY` ↔ `KC-REFLEXIVITY-DRIFT` ↔ `KC-VOLATILITY-CASCADE` | **Is near-critical order flow real or an estimator artifact?** Jaisson and Rosenbaum say criticality is the regime that generates the macroscopic volatility dynamics. Hardiman says the estimate lands near one because short windows and exponential kernels put it there. Both readings fit the same number. |
| `KC-CFMM-ORACLE` ↔ `KC-ORACLE-LAG` ↔ `KC-PRED-LIQUIDITY-MOVE` ↔ `KC-PRED-LMSR` ↔ `KC-XMKT-CONSISTENCY` | **What does a quoted price mean?** A belief, a liquidity state, an incentive equilibrium, or a stale average. Five cards give four answers and each is right about a different venue mechanism. |
| `KC-EARLY-WARNING-FRAGILITY` ↔ `KC-REAL-DRIFT` ↔ `KC-REGIME-PERSISTENCE` ↔ `KC-STOP-CONTINUATION` | **Can a regime change be seen before it matters?** Critical slowing down says sometimes, with a false-positive rate that is the binding constraint. Real concept drift says the informative monitor needs matured outcomes and is therefore structurally late. |
| `KC-COUNTERPARTY-INFO` ↔ `KC-MICRO-MECHANICAL-FLOW` ↔ `KC-MICRO-OFI` | **Does flow carry information, or is that an artifact of who is trading?** |
| `KC-BATCH-PRIORITY` ↔ `KC-MICRO-QUEUE` | **Does queue position mean anything here?** Continuous-time priority says a late cancel loses. The venue's batch hierarchy says it wins. The contradiction is venue-specific and both cards are scoped by `market_types` so retrieval cannot serve the wrong one. |
| `KC-DOUBLY-ROBUST` ↔ `KC-OFFLINE-SHIFT` | **Can logged data answer a counterfactual?** One says extrapolation dressed as measurement. The other says yes if either the reward model or the propensities are good. Both are correct and the disagreement is about how much coverage there is. |
| `KC-EVENT-TREE-CONSTRAINTS` ↔ `KC-JUDGMENT-AGGREGATION` | **Is an incoherent event tree an opportunity or a structural artifact?** A partition that fails to sum to one is arbitrage, unless the legs are priced by disjoint populations, in which case List and Pettit say incoherence is what aggregation does. |

*(Judgment: the fourth and eighth are the two I would spend on first. Both are testable on data we already have, and both change what a live agent should do rather than only what a paper would say.)*

## What can actually be acted on

A problem is served only when some concept covering it has a bound method, a hypothesis with a cost model, **and** a decision card. Thirteen of fifteen problems have at least one complete chain.

Two do not, and they are not the thin ones:

| Problem | Concepts | Complete chains | What is missing |
|---|---|---|---|
| `PB-INVENTORY-FUNDING` | 5 | **0** | Five concepts touch it, none has all three. Funding and inventory are the most continuously present cost on a perpetual venue and nothing here reaches a decision. |
| `PB-STALE-PROBABILITY` | 7 | **0** | Seven concepts, four hypotheses, five decision cards, and no single concept carries all three. The prediction-market workstream's core problem is covered broadly and served by nothing. |

*(Judgment: this is the most actionable finding in the assessment. Both look healthy by any count-based measure and neither can be acted on. Breadth of coverage is not the same as a path from a source to a decision, and only reading the store as a whole shows the difference.)*

## Where the confidence is not earned

Sixteen cards carry confidence at or above 0.6 with no anchor anyone has opened, including the four highest-confidence cards in the store. That is not a claim they are wrong. It is a claim that their confidence is a memory of the literature rather than a reading of it, and that distinction is exactly what the provenance line exists to keep visible.

The concentration is telling: they are almost all the microstructure and execution canon — Kyle, Almgren-Chriss, the cost floor, recursive filtering, CUSUM. That material is paywalled, which is why it is unread, which is why the most confident part of the corpus is the least verified part. The arXiv harvest fixed this for the parts that had preprints. What remains is genuinely behind a paywall.

## Distribution, and what it says

| Workstream | Concepts |
|---|---|
| cross-cutting | 32 |
| `hyperliquid_l4` | 6 |
| `dxap_agents` | 3 |
| `polymarket` | 2 |

*(Judgment: the skew is honest but worth naming. Three quarters of the corpus is general machinery and a quarter is venue-specific. That is the right ratio for transferable knowledge and the wrong one for a trading system, and it explains why the two unserved problems above are both venue-specific.)*

Half the concepts are `implemented` and half are `specified`. The implemented half is where the closed-form self-tests live; the specified half is where the reasoning lives and nothing runs.

## What would change this picture

- **Reading the paywalled microstructure canon.** It would move sixteen high-confidence cards from remembered to read, and it is blocked on acquisition rather than on effort.
- **Completing the two dead chains.** Neither needs new sources. `PB-INVENTORY-FUNDING` and `PB-STALE-PROBABILITY` both have concepts and both need one card carrying method, hypothesis and decision together.
- **Running any method against the warehouse.** Twenty-three methods, 27 closed-form checks, zero contact with real data. Every claim above is about the shape of an argument, not about a market.
