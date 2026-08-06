# Executable bibliography

The corpus engine ([docs/CORPUS.md](CORPUS.md)) answers *what exists and what may we use*. This layer answers *what does it claim, how would we test it, what would falsify it, and which of it applies to the decision in front of us right now*.

```
source -> mechanism -> assumptions -> observable signature
       -> deterministic test -> decision relevance -> realized outcome
```

That chain is materially different from putting books in a vector database. A passage tells an agent that order flow may contain information. A compiled concept card tells it under what assumptions that holds, which observables separate informed from mechanical flow, which tested function to run on the data actually available, over what horizon the prediction applies, what would falsify it, whether it bears on entry, sizing, exit or abstention, and which source anchors support it.

## The architecture in one line

**Graph for discovering material → compiler for turning it into falsifiable concepts → filtered retrieval for selecting relevant ones → deterministic tools for calculating evidence → an attribution ledger for learning whether it paid.**

Retrieval is one component, not the approach:

| Layer | Role | Where it lives |
|---|---|---|
| Bibliographic graph | Discover sources, traverse relationships | `corpus.py`, `graphops.py` — offline |
| Concept compiler | Mechanisms, assumptions, tests, failure modes | `knowledge.py` — offline |
| Structured concept retrieval | Deliver mechanisms with counterevidence | `knowledge.py retrieve` — online |
| Deterministic methods | Apply the mathematics to current data | `methods.py` — online, called not re-derived |
| Attribution ledger | Learn what actually changed a decision, and whether it paid | `ledger.py` — offline, post-maturity |
| Raw passage retrieval | Quote source material | the `raw_similarity` arm — experimental control only |

The graph is the research control plane. The live data plane is metadata-filtered retrieval with a one-hop expansion for counterevidence — not graph traversal, which pulls in irrelevant neighbourhoods and costs latency a decision context rarely recovers.

## The object model

### Concept card

What a mechanism claims, in our own words, anchored to a source.

```yaml
concept_id: KC-MICRO-OFI
canonical_name: "Order flow imbalance as a short-horizon price predictor"
mechanism: "Price at the top of book moves when one side's queue is depleted relative to the other…"
assumptions: ["Top-of-book updates observed without material gaps", …]
market_types: [clob_equities, clob_futures, clob_crypto, perp_dex]
relevant_horizons: [tick, seconds, minutes]
required_observables: [l1_book]              # becomes a hard retrieval filter
expected_empirical_signature: "Roughly linear relation between interval OFI and mid-price change…"
alternative_explanations: ["Mechanical or hedging flow produces the same imbalance with no information"]
known_failure_modes: ["Spoofed quotes inflate queue changes", …]
contradicting_concept_ids: [KC-MICRO-MECHANICAL-FLOW]
source_passage_ids: ["cont-2014-price-impact-order-book-events#s2-3"]
implementation_status: implemented
confidence: 0.7
problem_ids: [PB-ADVERSE-ENTRY, PB-COST-DRAG]
```

### Hypothesis card

What makes the concept testable here: market context, causal story, ex-ante prediction, null, measurement operator, eligible universe, decision-timestamp rule, outcome horizons, **cost model**, invalidation conditions. A prediction without a cost model is rejected — it is not a testable trading claim.

### Method object

A binding from a concept to a versioned, tested implementation in `methods.py`. The version is pinned: if the implementation changes version, validation fails until someone re-verifies the card. A silent numerical change under a stable card is how a knowledge base quietly becomes wrong.

Twenty-three implementations, each with a closed-form self-test. Every one declares its as-of contract — what it is allowed to see relative to the decision timestamp — and its known numerical failure modes.

The self-tests are closed-form on purpose: a test that checks a number against a previously recorded number only detects change, while a test that checks it against a derivation detects error. Some of them are the mathematics itself:

- `doubly_robust_value` — a reward model biased by a constant 10 leaves the estimate **exactly** unbiased while the direct method carries the whole 10. That is the double-robustness property, not an approximation of it.
- `betting_eprocess` — mean capital over every equiprobable null path is exactly 1, at every sequence length. That is Ville's inequality's premise, checked directly rather than assumed.
- `cascade_forecast` — the total-descendants factor 1/(1−n) recovered exactly, amplification exactly 2 at n = 0.5.
- `path_signature` — the exact Lévy area of the unit triangle, unchanged under reparametrization.
- `molchan_error_diagram` — a constant score scores loss exactly 1.0, the no-skill line.
- `_ols` — a planted four-parameter model recovered to 1e-9, and a collinear design refused rather than solved.

Where an exact test is not available the check says what it does verify instead. `har_realized_volatility` cannot recover planted coefficients from a self-generated series, because any stable linear recursion converges to a fixed point at which the daily, weekly and monthly aggregates become collinear and the coefficients stop being identified. So the exactness is tested on `_ols` and the HAR check verifies structure: the daily loading dominates, a constant series is refused, horizon ordering is validated.

### Decision-relevance card

Connects a concept to a decision type without turning a claim into a strategy. Both halves required: what would support the action, and what would argue against it.

> **Wrong:** "Close the position after it gives back a third of its maximum favourable excursion."
>
> **Right:** "Estimate the conditional probability of a further favourable excursion given drawdown from MFE, flow innovation, spread, time since catalyst and regime. Compare continuation value against execution and opportunity cost."

The source generates a question and an operator, not an unearned rule. The validator lints for unconditional directive language.

### The SERVABLE gate

A card is retrievable only when it has every required field, at least one contradicting concept or alternative explanation, source anchors that resolve to non-excluded bibliography entries, no verbatim quote from a source whose rights forbid it, and — if it claims an implementation — a method binding at the registered version.

The counterevidence requirement is structural, not stylistic. A retrieval layer that can only confirm will confirm whatever the agent already wanted to do, with citations attached.

## Retrieval

```bash
python scripts/knowledge.py retrieve --context ctx.json --policy decision_value --markdown
```

1. **Hard filters first.** Market type, horizon, required observables actually available, source published as of the decision timestamp, decision type, retirement status, latency budget. This is where a 2025 book is kept out of a 2024 decision.
2. **Lexical scoring** (BM25 over card fields, name and observables boosted) — one term, not the ranking.
3. **Decision-value re-rank.**

   ```
   R(c|x) = relevance × evidence availability × falsifiability × historical utility
            − latency − context cost
   ```

   Multiplicative, so a near-zero term kills the card: a concept nothing would falsify, or one we cannot compute evidence for with the tools on hand, is worth less than its word overlap suggests. `historical utility` reads a posterior the ledger wrote from matured outcomes; with no evidence it returns the author's confidence shrunk toward 0.5, so prestige cannot masquerade as track record.
4. **Diversity** via MMR, because five restatements of one mechanism cost the same context as five different ones.
5. **Abstain** below threshold. Abstention is a result.
6. **One-hop counterevidence**: a contradicting concept, an alternative explanation, a failure mode, a load-bearing assumption. With `require_counterevidence`, a packet that cannot carry any is not served at all.

The output is an evidence packet — a few hundred tokens of mechanism, assumptions, signature, methods to run, decision relevance and counterevidence — not forty pages of textbook.

## Measuring whether it works: three gates

### Gate 1 — does the corpus add capability?

Not a trading test. Arms: closed-book, raw passage retrieval, compiled cards, compiled cards plus tools. Hold out complete authors or books, never random passages, or near-duplicate leakage inflates every number.

The **offline half runs in this repo**: `knowledge.py evaluate` scores retrieval policies against a labelled trial set of decision contexts, including contexts where the honest answer is that nothing applies. On the shipped seed:

| Policy | hit | precision | correct abstention | counterevidence | tokens |
|---|---|---|---|---|---|
| `raw_similarity` | 1.00 | 0.23 | 0.00 | 0.00 | 3.55k |
| `filtered_only` | 1.00 | 0.80 | 1.00 | 0.00 | 1.12k |
| `decision_value` | 0.94 | 1.00 | 1.00 | 0.80 | 0.76k |
| `conservative_abstain` | 0.50 | 1.00 | 1.00 | 0.75 | 0.81k |

Plain similarity retrieval has a perfect hit rate and answers *every* inapplicable context, including one timestamped before its sources were written. It looks like it is working. That is the point of the control arm.

The other half of Gate 1 — mathematical interpretation, assumption identification, diagnostic selection, recognizing non-applicability, transfer to a real trace, counterexample detection — needs a model in the loop and lives outside this repo.

### Robustness: does the policy survive the trial set being wrong?

A policy tuned to fourteen hand-written contexts can score perfectly and still be useless, because the trial set is a description of the world rather than the world. `knowledge.py stress` re-runs every trial under five perturbations:

| Perturbation | Question | Scored as |
|---|---|---|
| `lexical_drift` | The same decision, worded differently | retention |
| `observable_dropout` | An observable the gold concept needs is gone | **compliance** — serving it anyway is a violation |
| `tool_loss` | The methods are unavailable | retention (degrade, don't switch off) |
| `distractors` | Cards with heavy word overlap and the wrong market and horizon | retention |
| `near_duplicates` | A restatement of the gold card | retention (diversity should suppress it) |

Two of these do not ask the same question as the others: after `observable_dropout` the correct answer *changed*, so abstaining is a pass and serving is a fail. Scoring it as retention would penalize the right behaviour.

`integrity_violations` are label-independent hard errors: a served card whose observables are absent, whose market does not match, or whose horizon does not match. These are wrong whatever the trial expected.

On the shipped seed:

| Policy | robustness | worst case | violations | note |
|---|---|---|---|---|
| `decision_value` | **0.95** | 0.95 (tool loss) | 0 | degrades rather than switching off |
| `decision_value_wide` | 0.81 | 0.81 (near-duplicates) | 0 | serves duplicate restatements |
| `filtered_only` | 0.75 | 0.75 | 0 | no diversity control |
| `raw_similarity` | 0.00 | — | **656** | recommends calculations on data that is not there |
| `conservative_abstain` | 0.00 | 0.00 (tool loss) | 0 | silently switches itself off when tools vanish |

The last row is the finding worth having: an over-cautious threshold looks safe on clean trials and removes the knowledge layer entirely the moment the environment degrades — indistinguishable, from the outside, from having no corpus at all.

`robustness` is the lab's third decisive challenge, so the population search selects for policies that hold up rather than policies that fit the labels.

### Gate 2 — does it change behaviour, for defensible reasons?

Exact production contexts from real decision traces, with real tool outputs. Arms: baseline, **sham retrieval** (plausible but unrelated cards, matched for length and style), raw passages, compiled cards, compiled cards plus tools.

The sham arm is not optional. Without it, any measured change may be the generic effect of making the model deliberate longer.

Measure tool calls, evidence quality, factual and source errors, unsupported assumptions, action differences, sizing differences, turnover, calibration, and whether the retrieved concept was actually applicable. This is a behavioural intervention, not economic causality — fixed historical contexts cannot reproduce path-dependent consequences of orders, fills, memory and subsequent states.

### Gate 3 — does it improve prospective ROI?

A randomized native trial: same prompt template, same model, same research children and tools, branch-isolated paper accounts, independent memory and triggers, strict as-of availability, positions marked to market at horizon, **no policy or retrieval update before the batch matures**.

Randomize at the rollout or branch-day level. Decisions within an account path are not independent, and inference must be clustered at the unit of randomization — thousands of wakes are not thousands of observations.

`ledger.py` implements this side:

```bash
python scripts/ledger.py assign --units branches.json --arm baseline --arm treatment --seed dxap-2026
python scripts/ledger.py ladder                 # offered -> ... -> economically beneficial
python scripts/ledger.py analyze --cluster-field branch_id --control-arm baseline
python scripts/ledger.py utility                # writes the retrieval re-ranking posterior
```

`analyze` **refuses** to compute an effect on unmatured outcomes or an unfrozen batch. That refusal is the module's main job: an effect estimated mid-batch, then fed back into retrieval, is exactly the artifact the ledger exists to prevent.

## The attribution ladder

Self-reported "I used the source" is not evidence. The ledger counts each rung separately:

```
offered -> served -> inspected -> semantically used -> tool-changing
        -> behaviour-changing -> economically beneficial
```

Only the last rung requires matured outcomes, and only a randomized comparison licenses the word "beneficial". A card that is offered a thousand times, opened twice and never changes a decision is not knowledge the agent has — it is context the agent pays for.

## Frontier bets: where an advanced-mathematics import might pay

`knowledge/frontier_bets.yaml` holds ranked *hypotheses about where to look* — mathematical imports that could pay if they transfer. They are not findings and nothing in the file has been tested on our data. Each bet must name the object being imported, the diagnosed problem it attacks, a sharp prediction, a falsifier, the minimum data, and the first computation to run; `knowledge.py bets` refuses a bet that is missing any of them, cites a source not in the bibliography, or names a `first_computation` with no implementation.

```
V = payoff x sqrt(novelty) x testability x maturity - effort
```

Novelty is square-rooted deliberately: being first is worth something, but a novel idea nobody can test is worth less than a known one that can be refuted this week. Maturity multiplies rather than adds — a bet that needs new mathematics before it can be tried is a research programme, not a bet.

Four of the eleven ship with their first computation already implemented in `methods.py`, so they can be refuted the day data arrives:

| Bet | Import | First computation |
|---|---|---|
| `FB-CRITICALITY` | Hawkes branching ratio as a live fragility state variable | `hawkes_branching_ratio` — recovered from count dispersion via the Fano identity, n = 1 − F^(−1/2) |
| `FB-JOINT-BOUNDS` | Fréchet–Hoeffding and martingale optimal transport bounds across correlated prediction markets | `prediction_market_consistency` — conjunction, implication and partition breaches, cost-gated per leg |
| `FB-SIGNATURE` | Path signatures; the Lévy area between price and flow as a clock-free lead-lag measure | `path_signature` — level-2 iterated integrals, invariant to time reparametrization |
| `FB-IRREVERSIBILITY` | Entropy production and time-reversal asymmetry as a screen for where structure exists | `time_irreversibility` — ordinal-pattern divergence between forward and reversed series |

The file also records what is deliberately *not* a bet — topological data analysis, quantum portfolio optimization, deterministic chaos prediction, fractal-market narratives, agent-based simulation as evidence — with the reason, so the same suggestions do not get relitigated every quarter.

## Exploratory extensions: proposing new work, only from what was read

`knowledge/exploratory_extensions.yaml` proposes work that would be *new* — extending a line of research into our domain rather than importing it. One rule makes it different from the bets file, and it is enforced rather than encouraged:

> **Every extension must cite a corpus unit whose `read_status` is `read` or `compiled`.** An extension grounded in a source nobody has opened is refused by `knowledge extensions`.

The cheapest way to invent a research programme is to imagine what a paper probably says. The gate exists because that failure is invisible from the outside — the proposal reads exactly the same either way.

Each entry names what the source leaves open *in its own terms*, what specific advantage we have that the original authors lacked, the claim that would be new if it held, and the first experiment that could kill it. Scoring adds one term to the bets formula:

```
V = payoff x sqrt(novelty) x testability x maturity - effort - already_done_risk
```

because a novel-work proposal fails most often by being unoriginal rather than by being wrong.

Fifteen of the eighteen now name a first computation that exists, up from six, because the workstream methods above were written to be the first step of the proposals that had none. Three still do not: `EXT-ORDER-COUNT-QUEUE`, `EXT-LVR-DISCRETE` and `EXT-VENUE-LAG-NULL`. Their scores were left alone. Writing an implementation and then raising the score of the proposal it serves would let the ranking reward whatever happened to get built, which is backwards.

### What reading changed

The first pass of primary reading revised three bets and produced nine extensions. Two of the revisions were corrections to my own claims:

- **`FB-CRITICALITY`'s prediction was wrong as written.** Hardiman, Bercot and Bouchaud measure the branching ratio fluctuating about one across fourteen years of E-mini data, and demonstrate that the published claim of *rising* reflexivity is an artifact of fitting exponential kernels on thirty-minute windows. What moves is the correlation timescale. The bet survived; its prediction was rewritten, and the surviving question became `EXT-CRITICAL-SCALE`.
- **`FB-NONHERMITIAN` was less novel than scored.** Time-lagged correlation matrices have already been treated as asymmetric random matrices. Novelty cut from 5 to 3; the residual opening — validating the null against a mechanically known lag — became `EXT-VENUE-LAG-NULL`.
- **`FB-IRREVERSIBILITY` was strengthened.** Flanagan and Lacasa find every series they measure is irreversible and essentially uncorrelated with volatility, and state the irreversibility-to-predictability link as an open question. The prediction was refined from presence to rank, and closing their open question with a decision ledger became the top-ranked extension.

Reading also changed two implementations. `time_irreversibility` gained the surrogate null that the source method treats as essential, and `hawkes_branching_ratio` gained a scale profile and a warning, because the published failure mode is exactly the one a window-based estimator walks into. Both are version 1.1.0, which forced their method cards to be re-verified — the version pin doing its job.

`knowledge status` reports provenance plainly: how many cards are anchored to a unit someone opened, and how many rest on unread anchors. At the time of writing that is 22 of 35. The bottleneck was never effort: the seed cards cite the canon, the canon is paywalled, and provenance was blocked on acquisition. The arXiv harvest reached the preprint versions of several of them, and reading those grounded cards that had sat on unread anchors for four releases. Seeding a store from working knowledge is legitimate; leaving it that way silently is not.

## The workstreams, and closing the gaps they opened

Reading the venue documentation and our own ingest schema added four problems to the map — batch type-priority, phantom depth, logical arbitrage under atomic settlement, and agent attribution — and then left them uncovered. `knowledge status` said so plainly: four problems with no servable concept. Five cards and five methods close them, each anchored to a unit someone actually opened rather than to a remembered result.

| Problem | Concept | Method | What it computes |
|---|---|---|---|
| `PB-BATCH-PRIORITY` | `KC-BATCH-PRIORITY` | `batch_priority_fill` | Execution order under the venue's type hierarchy against the arrival-time counterfactual, and the cancels that beat an aggressive order which arrived first |
| `PB-PHANTOM-LIQUIDITY` | `KC-PHANTOM-DEPTH` | `depth_realization` | Executable fraction at levels a sweep passed through, and the slippage attributable to the shortfall |
| `PB-LOGICAL-ARB` | `KC-EVENT-TREE-CONSTRAINTS` | `event_tree_constraints` | The partition set derived from event metadata, split into what the token layer enforces and what it leaves free |
| `PB-AGENT-ATTRIBUTION` | `KC-ANYTIME-ATTRIBUTION` | `betting_eprocess` | A capital process and confidence sequence that survive continuous peeking |
| `PB-ADVERSE-ENTRY` (second channel) | `KC-COUNTERPARTY-INFO` | `counterparty_markout` | Shrunk per-address mark-out, and whether the ranking persists out of sample |

Three of these use observables the published literature has not had. Counterparty addresses on every fill turn trade classification from an inference problem into a lookup. Order counts per book level distinguish a level held by one large order from an equally deep level held by twenty small ones. A documented intra-batch ordering rule replaces the continuous-time priority that every order-book model assumes.

`KC-BATCH-PRIORITY` contradicts `KC-MICRO-QUEUE` outright, and that is the point: continuous-time queue position says a late cancel loses, and on a batching venue it wins. Both cards are servable, scoped by `market_types`, and the trial `T-NEG-BATCH-ON-CONTINUOUS` checks that the batching card stays out of a continuous-matching context — a case a retriever matching on queueing vocabulary gets exactly backwards.

`betting_eprocess` sits beside `ledger.py analyze` rather than replacing it. The ledger is fixed-sample, clustered, and refuses to run before the batch freezes; that is what to read once outcomes have matured. The e-process is what to read while they are still accumulating and someone is looking every day anyway. Its guarantee is Ville's inequality: under the null the capital process is a non-negative martingale with mean one, so the chance it *ever* reaches 1/α is at most α, at any stopping time the observer likes. The self-test checks that property directly by averaging the capital over every equiprobable null path.

## Pulling the corpus into analysis work

`knowledge.py retrieve` answers a *decision*: a structured context with a market, a horizon, available observables and a decision type. That is the live path and it is deliberately narrow.

Analysis work has a different shape. You have a question in prose, and you want the corpus pulled into whatever you are working on.

```bash
python scripts/passages.py index                                    # extract and index what we hold
python scripts/passages.py brief --question "..." --markdown
python scripts/passages.py search --query "..." [--quote-local]
```

A brief comes back in the order it should be read:

1. **What we have compiled** — the concept cards that bear on the question, each with the assumptions it needs, the card that contradicts it, and its source anchors. This comes first because a card carries assumptions and failure modes and a passage carries neither.
2. **What would change the answer** — the union of the failure modes across those cards. A brief with no falsifiers is an opinion.
3. **In the sources** — ranked passages with exact locators, subject to the rights gate below.
4. **Read next** — unread units in sources we already hold.
5. **Catalogued, relevant, not on disk** — what to go and get.
6. **Open questions on the same ground** — matching frontier bets and extensions, with their first computation if one exists.

### Passages are subordinate to concepts, on purpose

A nearest passage is selected because its words resemble the query, not because its mechanism applies. So passages appear as evidence anchors under a compiled claim and as a reading queue, never as the answer. This is the same distinction the `raw_similarity` control arm exists to measure: on the shipped trial set it has a perfect hit rate and precision 0.23, and it answers every inapplicable context.

The brief reports its own coverage in the header — passages indexed, sources held, catalogue size — so it is visible when the passage layer has nothing to offer and the compiled layer is carrying the whole answer. Right now that reads *3,540 passages from 32 sources held locally, out of 405 catalogued*, because the microstructure canon is almost entirely paywalled and the material we can hold is skewed toward open courseware and preprints.

### The rights gate is on output, not on indexing

Everything we legitimately hold gets indexed, so search can find it. What may be *emitted* depends on the use class:

| Use class | What a result carries |
|---|---|
| `ingest_*` | Locator plus a snippet of the text |
| `reference_only`, `needs_review` | Locator, the terms that matched and their counts, and where to open it — never the sentence |
| `excluded` | Not indexed at all |

The second row is the load-bearing one. A brief is written to be carried into an analysis, and from there into memos and artifacts. Text that may not be redistributed must not ride along inside it. `--quote-local` overrides this for personal reading and says so in a banner; it changes what is printed, not what the licence permits, and the `quotable` flag on every result stays false.

Corpus-wide vocabulary is floored out of the ranking. A term carried by more than a quarter of passages cannot discriminate between them, and in a corpus that is entirely about order books, words like "orders" and "position" clear any generic stopword list while still being noise. When every word in a question is corpus-wide, the brief returns no passages and says why rather than ranking on page length.

## What the adjacent disciplines actually changed

Fifty-one entries in `adjacent_disciplines` were an argued reading list and nothing more: no units, no cards, nothing retrieval could serve. Seven of them are held on disk, so those were read and compiled. Two of the transfers corrected something this repo was already doing wrong.

**Probability gain is not an objective.** Helmstetter and Sornette state it plainly: gain is maximised as alarm time goes to zero, so optimising it selects a rule that almost never fires and predicts almost nothing. They use the Molchan error diagram instead — alarm fraction plus missed fraction, with a Poisson benchmark sitting at exactly 1.0 so skill is absolute rather than relative. Their ETAS results land at 0.6 to 0.9 with the minimum near a 10% alarm fraction.

That is the diagnosis of a failure already visible in our own stress table. `conservative_abstain` scores perfectly on clean trials and 0.00 robustness under tool loss, because a threshold tuned on how right it is when it fires selects silence. `molchan_error_diagram` is now in the registry, and `KC-ALARM-LOSS` says to report the loss first and the gain second.

**Forecasting a self-exciting stream from observed events under-predicts it.** Activity over any horizon beyond the immediate is dominated by events triggered by events that have not happened yet. The correction is exact for a subcritical branching process: total descendants of one event is 1/(1−n), so a first-generation forecast is short by that factor. `cascade_forecast` implements it, and the card carries the source's own qualification — the naive forecast is wrong in level while its *relative* evolution carries nearly the same information, so for a decision that only needs the direction of activity the correction buys nothing and costs a parameter.

**Collective incoherence does not imply anyone is wrong.** List and Pettit's Theorem 1 shows no aggregation rule yields complete, consistent, deductively closed collective judgments under universal domain, anonymity and systematicity — and it holds *even when every individual judgment set is itself coherent*. Each proposition attracts its own majority and the majorities diverge. A prediction market is an aggregation rule of exactly that kind, and each leg of an event attracts its own population. `KC-JUDGMENT-AGGREGATION` contradicts `KC-EVENT-TREE-CONSTRAINTS` deliberately: one says a partition breach is an opportunity, the other says it may be a structural artifact of who is trading which leg.

The escape route the theorem names is convergence, which makes this testable on data nobody else has. Coherence should track *participant overlap across legs*, and both venues publish addresses. `HY-COHERENCE-OVERLAP` states it: breach magnitude falls with Jaccard overlap of the address sets pricing each leg.

### A correction the reading forced

Tóth et al distinguish three quantities that are all called price impact:

| Measure | Aggregates over | Exponent |
|---|---|---|
| Immediate impact of one market order of size *q* | a single order | ≈ 0.2, or logarithmic |
| Interval price change against interval order imbalance | many participants' orders | → linear as the interval grows |
| Total impact of a metaorder of size *Q* | one participant's decision | 0.4 to 0.7 (the square-root law) |

They say plainly that many authors unduly identify the first two. This corpus was one of them. `kyle_lambda` regresses interval price change on interval signed volume, which is the second measure and lives in the linear regime, and `order_flow_imbalance` is in the same family. Neither prices a metaorder, so using either to size one applies a linear coefficient to a concave problem — understating the cost of large orders and overstating it for small ones.

`KC-IMPACT-CONFLATION` records this, contradicts `KC-INFO-KYLE` deliberately, and carries the correction in its own failure modes rather than in a footnote. Metaorder reconstruction normally needs participant attribution that almost no dataset has. This venue publishes both counterparty addresses on every fill, so the third measure is estimable here rather than assumed, which is what `HY-IMPACT-EXPONENT` proposes to do.

## Reading the whole store at once

```bash
python scripts/knowledge.py assess --markdown
```

Every other command answers a question about one card, one context or one queue. This one asks what the collection looks like taken together, which is where a different class of problem lives:

- **Contradiction structure** — which cards argue with which, and the clusters they form. A cluster is a question the corpus has two defensible answers to, not a defect.
- **Chains that reach a decision** — a problem is served only when some concept covering it has a bound method, a hypothesis with a cost model, *and* a decision card. Anything less is a claim the agent cannot act on, and a problem can look well covered by every count-based measure while having no complete chain at all.
- **Load-bearing sources** — anchors supporting several cards. One of these being wrong takes everything above it down together, and the check that matters is whether anyone read it.
- **High confidence on unopened material** — cards at confidence 0.6 or above with no anchor anyone opened. Not evidence they are wrong; evidence that the confidence is a memory of the literature rather than a reading of it.
- **Orphans** — methods bound to nothing, concepts outside the problem map, cards carrying neither a contradiction nor an alternative explanation.

`make smoke-knowledge` asserts the last group is empty and that the contradiction structure has not collapsed. Those are the four ways a store like this rots quietly, and they are cheap to check and invisible from inside any single card.

See [docs/CORPUS_ASSESSMENT.md](CORPUS_ASSESSMENT.md) for the current reading.

## Ranking what to compile next

```bash
python scripts/knowledge.py compile-queue --limit 25
```

```
V(s) = P(new capability) × P(behaviour change | capability) × P(net gain | change)
       − processing cost − redundancy − misapplication risk
```

Before outcomes exist these are component priors: **problem proximity** (personalized PageRank seeded on the problem map, so a source ranks by closeness to a problem we actually have rather than by citation count), mechanistic density, analyst priority, likely pretraining scarcity, cross-bucket bridge value (betweenness — structural holes are where transfer lives), accessibility, minus processing cost and redundancy with what is already compiled.

Likely pretraining scarcity is an **access-friction proxy, never an observation**. No one can see a closed model's training set. Paywalled, library-only and out-of-print material is more likely to be thin in pretraining — and a rare bad book is still a bad book, which is why scarcity carries a small weight.

Output is chapter-level and comes in six queues: human foundation spine, machine reading, rare source, contradiction, implementation, and experiment — plus the minimum set of sources covering the whole problem map, chosen by greedy submodular coverage rather than by rank.

## Running it as a lab

```bash
labrat new my_dxap --profile=quant-finance-corpus --profile=dxap-knowledge
cd my_dxap
python scripts/knowledge.py validate      # the SERVABLE gate
python scripts/knowledge.py status        # problem coverage and gaps
python scripts/methods.py self-test       # every method's closed-form checks
python scripts/bootstrap.py               # candidates are retrieval policies
```

Profiles stack; later profiles win on conflicting files. The knowledge profile needs the corpus profile underneath it, because source anchors resolve against `corpus/bibliography.yaml`.

Candidates are retrieval policies. Families are the structural disciplines competing to explain the improvement: `structural_filtering`, `decision_value_rerank`, `counterevidence_expansion`, `abstention_calibration`, `context_economy`. The decisive challenges are `non_applicability` and `counterevidence_coverage` — both things similarity scoring cannot win, since a nearest neighbour is always available.

Unlike the corpus lab, this one runs unattended: scoring a policy is a sub-second deterministic evaluation.

## Command reference

| Command | Does |
|---|---|
| `knowledge.py validate` | SERVABLE gate over every card; non-zero exit on failure |
| `knowledge.py status` | Problem coverage, missing methods, missing hypotheses |
| `knowledge.py retrieve --context c.json [--policy p] [--markdown]` | Build an evidence packet |
| `knowledge.py evaluate [--policy p]` | Score policies against the labelled trials |
| `knowledge.py stress [--policy p]` | Re-score under five perturbations, with integrity violations |
| `knowledge.py bets [--verbose]` | Rank the frontier research bets; refuse any that is not refutable and grounded |
| `knowledge.py extensions [--verbose]` | Rank proposed new work; refuse anything not grounded in a unit that has been read |
| `knowledge.py compile-queue [--limit n]` | Rank what to read and compile next |
| `knowledge.py vocab` | Card vocabularies and the gate's conditions |
| `methods.py list / show / run / self-test` | The deterministic method registry — 17 methods, 20 closed-form checks |
| `ledger.py record / ladder / analyze / utility / assign` | Attribution and randomized analysis |
| `graphops.py self-test` | PageRank, betweenness, co-citation, coupling, communities, MMR, coverage |
| `corpus.py self-test` / `knowledge.py self-test` | Gates, filters and merge logic on adversarial input |

## What this repo deliberately does not do

- **No fine-tuning.** Structured external memory first; weight adaptation only after the gates identify which knowledge families change behaviour and improve outcomes.
- **No live self-modifying retrieval.** `historical_utility` reads a frozen posterior, never results from inside the current batch.
- **No trading claims from Gate 1.** Retrieval quality against expert labels is a precondition, not a result.
- **No vector index or database.** The retrieval layer is deliberately small and dependency-free so it can be read and audited. A hybrid lexical/vector index slots in behind the same interface when the card count justifies it; the filters and the re-rank do not change.

## Digest: how much source text a decision actually needs

`retrieve` answers *which claims apply* and returns concept cards, which are compressed
by construction. `digest` answers the next question: for each card in that packet, how
much of the underlying source goes in front of the model?

```bash
python scripts/knowledge.py digest --context ctx.json --budget 6000
python scripts/knowledge.py digest --context ctx.json --markdown
python scripts/knowledge.py digest --context ctx.json --compare
```

### Units and pages are not the same thing

A **unit** is a semantic reading target declared by hand in `bibliography.yaml`: a topic,
a locator, a priority, a read status, and a note. This corpus has 105 of them across 59
entries, median 15 declared pages.

A **page** is a physical extracted PDF page in `corpus/passages/passages.jsonl`. There are
5,963 of them across 64 entries, averaging about 372 tokens each, 2.2M tokens in total.

The join between the two is the locator string, and it is weak: **only 11 of 105 units
name a page range a parser can resolve.** The rest say "sections 3-4", "the empirical
section", "whole paper". A unit with no resolvable range does not get a `unit` tier at
all, because the fallback span is the entire entry and serving that under the name of one
section is how a card claiming to rest on an empirical section arrives carrying 54 pages.
Those anchors get an excerpt instead, and `locators_unresolved` counts them, because the
fix is to write page numbers into the locator.

### The five tiers

| tier | what it is | typical size |
| --- | --- | --- |
| `card` | the concept card's own fields, no source text | 0 |
| `note` | the reading note recorded when someone read that unit | ~40 tokens |
| `excerpt` | quoted passage text from the resolved pages, capped at `excerpt_chars` | up to 5,000 tokens |
| `unit` | every page the unit names, only when the locator resolves | 1–90k tokens |
| `source` | every page of the entry | 100–200k tokens |

Two things decide which one an anchor gets.

**There is no licence gate.** `corpus.py` records the terms for every source, and that
record is worth keeping — it is a fact about the source and the thing to consult if any
of this is ever published. Redistribution is not what the digest does. It assembles text
you already hold into a prompt on your own machine, and a licence restricting
redistribution does not restrict reading. Gating that produced a tool refusing to show
you a paper on your own disk.

**Triggers raise it.** Escalation is never a vibe. Each trigger names a condition the
card text demonstrably cannot settle, and every one that fires is written into the digest
next to the passage it paid for:

| trigger | fires when |
| --- | --- |
| `contested` | another card in this same packet contradicts it |
| `unread_anchor` | nobody opened the unit, so the card is a claim about a source |
| `low_confidence` | confidence is below the policy floor |
| `lexical_miss` | the context asks about terms present in the source and absent from the card |
| `load_bearing` | two or more cards in the packet rest on this one anchor |

**The budget allocates it.** Top-k with full reads is the wrong shape: it spends
everything on the first two anchors and starves the rest. This is a multiple-choice
knapsack — at most one tier per anchor, maximum total value under a token ceiling — so it
will buy four notes instead of one full unit when that is the better packet. Watch it
work by tightening the budget on the same context:

```
budget 60000   1 excerpt + 1 excerpt    6,544 tokens
budget  1200   2 excerpts                 696 tokens
budget   400   1 excerpt + 1 card         348 tokens
```

Identical text is bought once. Two anchors on the same entry — common, since most
locators fall back to the whole entry — hold byte-identical passages, and nothing in a
knapsack stops it buying both. The anchor with the most at stake carries the passage and
the others record `shares_text_with`. On one real context that is the difference between
31,699 and 53,398 tokens for the same material.

### Bringing in a whole source

The default is deliberately not the whole thing: `source` tier is never reached by a
trigger. Escalation answers "the card is not enough here"; it has no opinion on whether a
200,000-token course should be paged in. That is an operator decision, so it has to be
stated.

```bash
python scripts/knowledge.py digest --context ctx.json --full he-2022-fundamentals-perpetual-futures
python scripts/knowledge.py digest --context ctx.json --full-all
```

Or permanently, on the bibliography entry, for a source that should always arrive
complete:

```yaml
- id: he-2022-fundamentals-perpetual-futures
  digest_full_text: true
```

Asking for a source the lab does not hold returns a line in `starved`, which is the
fetch list.

**What is actually reachable.** All 2.2M tokens extracted from this corpus, across 64
entries. The limit is what has been extracted, not what may be used.

### Two things the digest reports that are not tier choices

**Refused by rights.** A trigger asked for source text and the licence said no. The row
records what was wanted, what capped it, and whether the lab even holds the text, so it
is clear whether clearing the licence would buy anything.

**Asked for, and not held.** A trigger asked, the licence allows it, and there is neither
a reading note nor an extracted page. Nothing is wrong with the packet; the material is
missing. This is the fetch list.

### The control arms

`--arm never` serves cards only. `--arm always` serves every anchor at its rights
ceiling. `--compare` runs all three and scores the policy against the unbounded arm on
tier agreement and cost share. If the policy does not land close to `always` for a
fraction of the tokens, the triggers are not earning their place and should change. When
the licences bind before the triggers do, the comparison says so rather than crediting
the policy for a decision the rights made.

