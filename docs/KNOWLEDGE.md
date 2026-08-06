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

Shipped implementations, each with a closed-form self-test: `order_flow_imbalance`, `kyle_lambda`, `avellaneda_stoikov_quotes`, `almgren_chriss_schedule`, `kalman_local_level`, `cusum_changepoint`, `continuation_hazard`, `lmsr_binary`. Every one declares its as-of contract — what it is allowed to see relative to the decision timestamp — and its known numerical failure modes.

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
| `raw_similarity` | 1.00 | 0.24 | 0.00 | 0.00 | 3.14k |
| `filtered_only` | 1.00 | 0.80 | 1.00 | 0.00 | 0.99k |
| `decision_value` | 0.90 | 1.00 | 1.00 | 1.00 | 0.63k |
| `conservative_abstain` | 0.40 | 1.00 | 1.00 | 1.00 | 0.66k |

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
| `decision_value` | **0.92** | 0.92 (near-duplicates) | 0 | |
| `filtered_only` | 0.75 | 0.75 | 0 | serves 12 duplicate restatements — no diversity control |
| `decision_value_wide` | 0.70 | 0.70 | 0 | serves 9 duplicates |
| `raw_similarity` | 0.00 | — | **388** | recommends calculations on data that is not there |
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

### What reading changed

The first pass of primary reading revised three bets and produced nine extensions. Two of the revisions were corrections to my own claims:

- **`FB-CRITICALITY`'s prediction was wrong as written.** Hardiman, Bercot and Bouchaud measure the branching ratio fluctuating about one across fourteen years of E-mini data, and demonstrate that the published claim of *rising* reflexivity is an artifact of fitting exponential kernels on thirty-minute windows. What moves is the correlation timescale. The bet survived; its prediction was rewritten, and the surviving question became `EXT-CRITICAL-SCALE`.
- **`FB-NONHERMITIAN` was less novel than scored.** Time-lagged correlation matrices have already been treated as asymmetric random matrices. Novelty cut from 5 to 3; the residual opening — validating the null against a mechanically known lag — became `EXT-VENUE-LAG-NULL`.
- **`FB-IRREVERSIBILITY` was strengthened.** Flanagan and Lacasa find every series they measure is irreversible and essentially uncorrelated with volatility, and state the irreversibility-to-predictability link as an open question. The prediction was refined from presence to rank, and closing their open question with a decision ledger became the top-ranked extension.

Reading also changed two implementations. `time_irreversibility` gained the surrogate null that the source method treats as essential, and `hawkes_branching_ratio` gained a scale profile and a warning, because the published failure mode is exactly the one a window-based estimator walks into. Both are version 1.1.0, which forced their method cards to be re-verified — the version pin doing its job.

`knowledge status` reports provenance plainly: how many cards are anchored to a unit someone opened, and how many rest on unread anchors. At the time of writing that is 4 of 20. Seeding a store from working knowledge is legitimate; leaving it that way silently is not.

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
| `methods.py list / show / run / self-test` | The deterministic method registry |
| `ledger.py record / ladder / analyze / utility / assign` | Attribution and randomized analysis |
| `graphops.py self-test` | PageRank, betweenness, co-citation, coupling, communities, MMR, coverage |
| `corpus.py self-test` / `knowledge.py self-test` | Gates, filters and merge logic on adversarial input |

## What this repo deliberately does not do

- **No fine-tuning.** Structured external memory first; weight adaptation only after the gates identify which knowledge families change behaviour and improve outcomes.
- **No live self-modifying retrieval.** `historical_utility` reads a frozen posterior, never results from inside the current batch.
- **No trading claims from Gate 1.** Retrieval quality against expert labels is a precondition, not a result.
- **No vector index or database.** The retrieval layer is deliberately small and dependency-free so it can be read and audited. A hybrid lexical/vector index slots in behind the same interface when the card count justifies it; the filters and the re-rank do not change.
