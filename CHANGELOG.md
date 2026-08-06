# Changelog

## Unreleased

### Added

- `reversible_projection` 1.0.0: exact time-irreversibility as an information projection. Wolfer
  and Watanabe give the m-projection onto the reversible manifold as the arithmetic mean of a kernel
  and its time-reversal and the e-projection as their rescaled geometric mean; `D(P || P_m)` is then
  the divergence to the nearest reversible chain with no surrogate null to calibrate against.
  Writing it produced a small result the source does not state: in edge-measure coordinates that
  divergence is exactly the Jensen-Shannon divergence between `Q` and its transpose, which makes it
  the same divergence our surrogate-based ordinal statistic computes, applied to a different object.
  The self-test asserts the identity and the Pythagorean decomposition to 1e-12, and a deterministic
  three-cycle returns exactly `ln 2`.
- `knowledge/structural_findings.yaml` and `knowledge.py findings`: patterns that recur across two
  or more unrelated domains, each recording the structure, the correspondence, what it buys, the
  sources actually read to reach it, and an `agent_seed` written for whoever builds there next.
  Validation requires two domains, refuses a `read` or `tension` finding that names no source read,
  and refuses a `tension` that states no open question. 19 findings so far.
- The reading round behind them. Bun, Bouchaud and Potters give backtest optimism in closed form —
  `R_in²/(1−q) = R_true² = (1−q) R_out²` for a completely general population covariance — and show
  the optimally cleaned spectrum is narrower than the *true* one, so recovering the population
  eigenvalues is provably the wrong objective. Bongiorno and Lamrani show the expected KL divergence
  of a sample covariance depends on the aspect ratio alone and not at all on what is being
  estimated, and that the Frobenius error is the leading term of a series that diverges exactly
  where the tractable loss stays finite and small. Chen, Fortnow, Lambert, Pennock and Wortman show
  the LMSR cost function over permutations is `b log perm(B)`, so quoting is #P-hard while matching
  the same divisible bet language is polynomial — and that LMSR prices are Weighted Majority weights
  with the `b log n` subsidy as the regret bound. Beiglböck, Nutz and Touzi show two marginals in
  convex order imply barriers no martingale transport crosses, and that the pointwise
  superreplication dual has a duality gap the quasi-sure formulation closes. Raskutti and Mukherjee
  show mirror descent is natural gradient descent on the dual manifold, which joins to the LMSR
  result: market-maker pricing, exponential weights and natural gradient are one algorithm in three
  coordinate systems, recorded as the file's one `conjecture` because the join is asserted nowhere.
  Wolfer and Watanabe show the reversible Markov kernels form both an exponential and a mixture
  family, and that reversibility is exactly the condition under which eigenvalue perturbation is
  dimension-free — losing it swaps Weyl's inequality for a bound exponential in the dimension, which
  ties the irreversibility reading to the random-matrix one. Mirzaei and Amiri show a two-stage
  ordering pipeline where each stage is correct and the composition is not: Sui linearizes a
  committed sub-DAG by validator index, worth an 89% same-round ordering win with no attacker, and
  the gas-price re-sort meant to erase that is a *stable* sort whose key is tied whenever
  transactions pay the reference price — which is the common case, so the bias passes through the
  mechanism intended to remove it at no cost. The same paper shows a validator raising its win rate
  above 94% by declining to broadcast, an advantage obtained by abstention and indistinguishable
  from ordinary downtime.
- Rights are metadata rather than a gate. The corpus taxonomy records `mode: exploratory`, and
  nothing in the reading or compiling path consults rights status. The manifest machinery is
  unchanged, so a redistributable build remains possible if it is ever wanted.
- `knowledge.py digest`: decides how much source text a decision packet actually needs.
  Four tiers per anchor (card, note, excerpt, unit), a rights ceiling no trigger can
  lift, five named escalation triggers logged next to the passage each one paid for, and
  a multiple-choice knapsack that allocates a token budget across anchors instead of
  reading the top-k in full.
- `digest --compare` runs the `never`, `policy` and `always` arms and scores the policy
  on tier agreement and cost share, so the triggers have to justify their tokens.
- The digest reports two things separately from tier choice: anchors refused by a
  licence, and anchors that a trigger asked for and the lab does not hold.
- `digest --full <id>` / `--full-all`, and a `digest_full_text` flag on a bibliography
  entry, to bring a whole source into the packet. The `source` tier is never reached by
  an escalation trigger: whether a 200k-token course pages in is an operator decision.
- `scripts/acquire.py` and `make acquire`: ranks what to acquire by what the knowledge
  store currently cannot support — cards resting on it, confidence held without evidence,
  live contradictions it could settle, problems it blocks from reaching a decision — and
  separately lists the buckets we hold almost nothing from, which produce no cards to
  block and so never surface in a gap analysis driven by existing cards.
- `scripts/atlas.py` and `make map`: writes `MAP.md`, one self-describing file an agent
  can read start to finish, plus flat `concepts.csv`, `sources.csv`, `units.csv` and
  `chains.csv` for filtering. Both generated; the YAML stays the source of truth.
- `scripts/add_library.py` registers a local library of purchased books as entries, and
  `passages.py` now indexes markdown and text sources as well as PDFs, so an exchange's
  documentation site can be a first-class source instead of something printed to PDF.
- `make web` / `make web-data` and the corpus explorer under `web/`, documented in
  `docs/EXPLORER.md`.

### Changed

- Digest defaults raised for long-context use: budget 6k -> 60k tokens, excerpt cap
  1,400 -> 20,000 characters. The old excerpt was under a third of one extracted page.
- The four `ingest_*` classes that clear derivative use now reach the `source` tier.

### Fixed

- `corpus.py reading` skipped `compiled` and `abandoned` units but not `read` ones. Since reading
  raises no score, every unit anyone had opened sat permanently at the top of "what to read next" —
  the first twelve rows of the real queue were all already read. Read units now leave the queue, and
  `status` reports `units_awaiting_compile` so the backlog is visible rather than silent. The
  self-test plants a read unit that outscores every unread one on every term.
- Removed the licence gate from both reading paths (`knowledge.py digest` and
  `passages.py brief`) rather than making it configurable. `corpus.py` still records every
  source's terms, which is the thing to consult if any of this is published; reading
  material you already hold is not redistribution and is no longer gated on it.
- The explorer and its dev server bind to `127.0.0.1`, the generated bundle stays
  gitignored, and `web/DO-NOT-DEPLOY.md` records why.
- A unit whose locator names no pages no longer serves the whole entry as its `unit`
  tier. Ninety-four of this corpus's hundred-and-five units are in that state, so a card
  anchored to "the empirical section" was arriving with all 54 pages of the paper.
  `locators_unresolved` now counts them.
- Identical passages are bought once. Two anchors on one entry could each pay for the
  same span; on one real context that was 53,398 tokens for 31,699 tokens of material.

## 0.21.0 - 2026-08-06

- Added `knowledge.py assess`, which reads the whole store at once. Every other command answers a question about one card, one context or one queue; this asks what the collection looks like taken together, where a different class of problem lives. It reports the contradiction structure and its clusters, which problems have a chain that actually reaches a decision, which anchors carry several cards and whether anyone read them, which confident cards rest on unopened material, and the orphans.
- **The finding that justified building it.** `PB-INVENTORY-FUNDING` and `PB-STALE-PROBABILITY` have five and seven concepts, four hypotheses and five decision cards between them, and **zero complete chains** — no single concept covering either problem carries a bound method, a hypothesis and a decision card together. Both look healthy by every count-based measure and neither can be acted on. Breadth of coverage is not a path from a source to a decision, and only reading the store as a whole shows the difference.
- The structural result is otherwise clean: every anchor supporting two or more cards has been read, no method is bound to nothing, no concept floats outside the problem map, and no card carries neither a contradicting card nor an alternative explanation. Those are the four ways a store like this rots quietly, and `make smoke-knowledge` now asserts all four are empty.
- 18 contradiction pairs in 8 clusters. Each cluster is a question the corpus has two defensible answers to rather than a defect: what price impact is and how it scales; whether near-critical order flow is real or an estimator artifact; what a quoted price means; whether a regime change is visible before it matters; whether flow carries information; whether queue position means anything on a batching venue; whether logged data can answer a counterfactual; and whether an incoherent event tree is an opportunity or an artifact of who is trading which leg.
- Sixteen cards carry confidence at or above 0.6 with no anchor anyone has opened, including the four most confident in the store. They are almost all the microstructure and execution canon, which is paywalled — so the most confident part of the corpus is the least verified part, and that is an acquisition problem rather than an effort one.
- Added `docs/CORPUS_ASSESSMENT.md`: the current reading, with the generated structure separated from the judgment about what it means.
- Fixed a real bug the new command surfaced immediately: it read decision cards from the wrong store key and reported zero, which would have made every chain look broken. Caught because the planted self-test expects exactly one complete chain.

## 0.20.0 - 2026-08-06

- Four more held sources read and compiled. Units read 36 to 40, provenance 24 of 40 cards to 27 of 43.
- `KC-CRITICALITY-SCALING` is the mathematical bridge this corpus was missing. Jaisson and Rosenbaum start from the empirical fact that order-flow data only fits a Hawkes process when it is nearly unstable, and prove that after rescaling such processes converge to integrated Cox-Ingersoll-Ross — and that the Hawkes-based price model converges to Heston under the same criticality condition. So the branching ratio landing near one is not an awkward estimate to explain away: criticality at the microstructure scale is the regime in which the point process and the macroscopic diffusion are the same object at two resolutions. The card is paired with its own rival, since Hardiman's estimator artifact produces the same reading.
- `KC-IMPACT-SQRT` gained the confirmation that matters for our venue class. Donier and Bonart reconstruct over a million metaorders on Bitcoin/USD and find the square-root law holding across four decades of size, along the whole trajectory rather than only at the final execution price, **despite the quasi-absence of statistical arbitrage and market-making strategies** — which rules out every explanation requiring sophisticated arbitrageurs.
- `KC-TIME-UNIFORM-WIDTH`: the premium for being allowed to look whenever you like is a law-of-the-iterated-logarithm factor, not an arbitrary penalty. Howard et al build sequences by making the Cramér-Chernoff method time-uniform, giving nonasymptotic nonparametric coverage with widths that still go to zero. A sequence whose width does not shrink indicts the tail assumption rather than the method.
- `KC-CFMM-ORACLE`: a constant function market maker reports a price implicitly, and under stated conditions the agent who corrects it profits by doing so — honesty as an incentive result rather than a trust assumption, with convex duality bounding what any set of trades can remove from the pool. It contradicts `KC-ORACLE-LAG` deliberately: a time-weighted feed buys manipulation resistance with staleness, a CFMM is fresh and has a cost-width band instead, and importing one correction into the other is the error.
- **The SERVABLE gate caught an overclaim of mine.** `KC-TIME-UNIFORM-WIDTH` was written as `implemented` because we ship a confidence sequence, but our construction inverts a capital process on a grid and does not compute the LIL rate the card describes. The gate refused it until the status was corrected to `specified`. That is the version pin and the binding requirement doing exactly the job they exist for.
- 43 servable concepts, 457 entries, 58 decomposed into 104 units, zero validator warnings.

## 0.19.0 - 2026-08-06

- Made executable four pieces of mathematics the corpus carried and never ran. 23 methods, 27 closed-form checks.
- `doubly_robust_value` demonstrates its defining property exactly rather than approximately: on a balanced logged sample, a reward model biased by a constant 10 leaves the doubly robust estimate **exactly** unbiased while the direct method carries the whole 10, because the reweighted residual is −10 on half the rows at weight 2. The card and the method both lead with the caveat that doubly robust is not doubly safe, and that propensities have to be designed into a decision trace before it is generated rather than recovered afterwards.
- `engle_granger_cointegration` recovers the hedge ratio exactly on a noiseless pair, reads a planted bounded spread over a random walk as cointegrated with a negative error-correction coefficient, and reads two independent random walks as not cointegrated with an order of magnitude more residual variance. It reports the residual t-statistic against the conventional Engle-Granger threshold and says in its failure modes why that statistic does not have a standard distribution.
- `robust_location_scale` shows the breakdown point rather than asserting it: one arbitrary observation moves the mean by three orders of magnitude and leaves the Huber M-estimate within one unit. A degenerate median absolute deviation is refused rather than divided by.
- `har_realized_volatility` could not be tested by planting coefficients, and the reason is recorded rather than worked around: any stable linear recursion converges to a fixed point, at which the daily, weekly and monthly aggregates become collinear and the coefficients stop being identified. Exactness is tested on the least-squares core instead — a planted four-parameter model recovered to 1e-9, a collinear design refused rather than solved — and the HAR check verifies structure.
- Three new cards behind them: `KC-COINTEGRATION`, `KC-VOLATILITY-CASCADE` (the HAR cascade is the benchmark any volatility forecast has to beat, and it is cheap enough that omitting it is a choice) and `KC-ROBUST-ESTIMATION`, whose own alternative explanation is the standing objection to it — on market data the outliers are frequently the event, so the card argues for measuring influence rather than for always downweighting.
- 446 to 457 entries, weighted to results with theorems. Blackwell's approachability, which the whole no-regret and calibration literature is built on. Foster and Vohra: a forecaster can be asymptotically calibrated against an adversarial sequence with no model of it, which bounds what calibration alone can be evidence of. Aumann on agreeing to disagree and Milgrom and Stokey's no-trade theorem, which together say volume requires something outside the model and that which something is assumed decides what a flow-informativeness measure is measuring. Freedman's martingale Bernstein inequality, the workhorse under our time-uniform bounds. Robbins and Monro. Kesten, for power-law tails arising from ordinary multiplicative dynamics rather than extreme inputs. Rockafellar, because the scoring-rule correspondence, the transport dual and the market-maker cost function are the same theorem in different clothes.
- 40 servable concepts, 22 method bindings, 457 entries. Zero validator warnings. The six new anchor units are declared `unread` on purpose: those cards rest on working knowledge, and the provenance line should say so rather than let a section reference imply someone opened the copy.

## 0.18.0 - 2026-08-06

- Audited the catalogue against its own claims and filled what was missing. **Cointegration was entirely absent** while cross-market relative value is a named problem — Engle and Granger, and Johansen for the multivariate case where the number of independent relationships is itself the estimate. **Realized-volatility econometrics was absent** while every estimator here runs on high-frequency data: Andersen et al, Barndorff-Nielsen and Shephard, and Corsi's HAR, which is the benchmark any volatility forecast has to beat and is cheap enough that there is no excuse for not running it as the control.
- **Entity resolution was absent while "one address is not one participant" was written into `KC-COUNTERPARTY-INFO` as a failure mode with no literature behind it.** Fellegi and Sunter give the decision-theoretic framework with explicit error rates and a region where the honest answer is to refuse; Meiklejohn et al give the applied clustering heuristics for chain addresses. That failure mode now has a method behind it rather than a shrug.
- Robust statistics was absent while everything here is estimated on heavy-tailed data. Added Huber and Ronchetti, and Maronna et al: the influence function and the breakdown point are the right diagnostics and neither appeared anywhere.
- Also added repeated games and reputation, which is the theory of when a counterparty ranking keeps holding and when acting on it destroys the thing it measured; textual analysis, where Loughran and McDonald's result that a general-purpose sentiment dictionary misclassifies a large share of finance words is the direct warning for any model reading market text without a domain check; tail latency, where the 99th percentile of each component becomes the median of a fan-out; and Makarov and Schoar on persistent cross-exchange price differences, the empirical baseline any cross-venue consistency claim has to beat.
- 425 to 446 entries. `defi_mechanics` filled further with live protocol documentation, including Chainlink's per-feed heartbeat and deviation threshold — the exact configuration `KC-ORACLE-LAG` says a measured lag is only valid under.
- Read two more held sources and compiled them. `KC-REAL-DRIFT`: the conditional distribution of the outcome given the inputs can change while the input distribution stays identical, so a monitor watching price or flow features alone is watching the distribution that need not move, and detection needs matured outcomes and is therefore structurally late. `KC-DOUBLY-ROBUST`: a reward model is biased and a propensity model is high variance, and the doubly robust combination is accurate when either is good — but it needs propensities, which a decision trace has to be designed to record before it is generated rather than recovered after.
- 37 servable concepts, 19 hypotheses, 39 decision cards, 24 trials. Provenance 24 of 37 cards on units someone opened, up from 18 of 32 two releases ago. Units read 27 to 36. Zero validator warnings.
- The arXiv harvest is now exhausted for this corpus: 60 further preprintable titles searched, none matched. What remains unheld is genuinely not there.

## 0.17.0 - 2026-08-06

- Read six more held sources and compiled three cards. Provenance is 22 of 35 cards on units someone opened, up from 18 of 32. Units read went 27 to 33. The bottleneck was never effort: the seed cards cite the canon, the canon is paywalled, and provenance was blocked on acquisition until the arXiv harvest reached the preprint versions.
- **`KC-IMPACT-CONFLATION` is a correction to this repo.** Tóth et al distinguish three quantities all called price impact — the immediate impact of one order (exponent ≈ 0.2 or logarithmic), the interval price change against interval imbalance (increasingly linear as the interval grows), and the total impact of a metaorder (0.4 to 0.7) — and say plainly that many authors unduly identify the first two. `kyle_lambda` regresses interval price change on interval signed volume, which is the second measure, and `order_flow_imbalance` is in the same family. Neither prices a metaorder, so using either to size one applies a linear coefficient to a concave problem. The card contradicts `KC-INFO-KYLE` deliberately and carries the correction in its own failure modes.
- Metaorder reconstruction normally needs participant attribution almost no dataset has. This venue publishes both counterparty addresses on every fill, so the metaorder exponent is estimable here rather than assumed. `HY-IMPACT-EXPONENT` states the prediction.
- `KC-LIQUIDATION-DESIGN`: a protocol liquidates by auction or at a fixed spread, and the choice sets how much collateral leaves as liquidator profit and how concentrated the forced selling is. Qin et al show fixed-spread designs hand liquidators an unnecessarily large discount and that successive liquidations lift the close-factor cap, worth 53.96K USD on one worked case executed against real chain state. The design taxonomy transfers to a perpetuals venue; the magnitudes do not, and the card says so.
- `KC-OFFLINE-SHIFT`: evaluating a policy on data it did not generate is extrapolation rather than measurement, and the error is worst exactly where the evaluated and logged policies differ most — which is the region the exercise is about. This is why Gate 2 is a behavioural comparison and not an economic one, now stated as a card rather than as a caveat in the docs.
- Re-anchored `KC-IMPACT-SQRT` and `KC-REFLEXIVITY-DRIFT` onto units that were actually opened, clearing the last outstanding validator warning. The Filimonov reading is recorded with the note that Hardiman, Bercot and Bouchaud later attribute its headline trend to an estimator artifact, which is why the card built on it is scored low and paired with its contradiction.
- 35 servable concepts, 19 hypotheses, 39 decision cards, 24 trials, 425 entries, 47 decomposed into 91 units, 5,963 indexed passages, 327 PDFs on disk.

## 0.16.0 - 2026-08-06

- The dedicated arXiv harvest ran to completion without tripping its breaker: 19 preprints downloaded, 116 titles with no arXiv match, 4 errors. Local holdings went from 41 sources with extractable text to 64, and the passage index from 3,849 to 5,963.
- What it brought in matters more than how many. The preprints are the sources that existing concept cards were already citing without anyone having opened them: Bouchaud, Farmer and Lillo on slow digestion of order flow, Tóth et al on latent liquidity, Donier on metaorder impact, Filimonov and Sornette on reflexivity, Bacry on Hawkes processes in finance, Guéant on inventory risk. Provenance is now 18 of 32 cards on units someone opened, and `KC-MICRO-MECHANICAL-FLOW` and `KC-REGIME-PERSISTENCE` are grounded for the first time.
- One detail from that reading is directly checkable on our own feed and worth stating: market orders, limit orders and cancellations each show long memory in their sign series separately, but if a cancellation of a buy order is signed negative — matching the only direction of price move it can cause — the combined series does **not** show long memory. That decides which construction of order-flow sign is the informative one, and it is not the obvious one.
- Units read went 12 to 27 across three releases. 425 entries, 45 decomposed into 87 units.

## 0.15.0 - 2026-08-06

- Added `resolve.py arxiv`, a dedicated slow preprint harvest. arXiv was previously a passenger on `identify`, sharing its pace and its circuit breaker, so one throttle partway through a run killed the index for every title after it. Preprints are the largest pool of readable full text the corpus has any claim on, which earns them their own pass at their own rate.
- Resolution now persists. Identifiers found by `identify` are merged back into the bibliography rather than living only in a run artifact, so subsequent passes are incremental and `study` can reach every entry that has ever been resolved. Entries carrying a DOI went from 59 to 164.
- 405 to 425 entries. Widened the adjacent sweep with a deliberate bias toward open-access venues, because a source we can read compiles into a card and a source we cannot read stays a note: real-time reproduction-number estimation and its bias catalogue, real-time forecast scoring, ensemble underdispersion and Bayesian model averaging, concept drift and adaptive windowing, target-trial emulation, and causal inference under interference — which is the setting a branch-randomized trial is actually in, since two paper accounts trading the same book violate no-interference by construction.
- Closed the last of the co-cited frontier targets bar three: stochastic complexity, backward SDEs, hybrid dynamical systems, rough Heston, multivariate market-event point processes, stochastic portfolio theory, radar systems and Rasch.
- Read two more held sources and compiled them. `KC-PERP-BASIS`: a perpetual is not obliged to converge to spot, so its fundamental basis is non-zero and set by the borrowing rate against funding intensity, which means the tradable quantity is the residual after that level and a strategy trading the raw basis is implicitly short the rates spread. The derivation rests on random-maturity arbitrage, where convergence happens at a random time and the position has to survive margin until it arrives.
- `KC-ORACLE-LAG`: an oracle buys manipulation resistance with staleness, and both are mechanical. Time-weighted averaging raises the cost of single-block manipulation in proportion to the window and delays the reported price by the same window. On a venue where the oracle drives funding and liquidation, that lag is a predictable wedge that moves money, and it is widest exactly when the market is moving fastest.
- 32 servable concepts, 18 hypotheses, 37 decision cards, 24 labelled trials. Provenance is 16 of 32 cards on units someone opened, up from 9 of 25 two releases ago; units read went 12 to 24.

## 0.14.0 - 2026-08-06

- **Fixed two silent merge bugs.** `units` were never merged into an existing entry, so a reading round wrote nothing at all and reported success. Separately, because findings pass through `merge_defaults` before merging, an entry mentioning only one field arrived carrying every other field's default and quietly reset it — a finding about units was resetting `acquisition.state` from `owned` back to the default. The merge now tracks which keys the scout actually wrote, merges units by `unit_id`, and lets `read_status` advance but never regress. Both are covered by `corpus.py self-test`, which is where a silent drop of this kind should have been caught.
- Read the seven adjacent-discipline sources held on disk and compiled five concept cards from them, each anchored to a unit someone opened. Provenance rose from 9 of 25 cards on read units to 14 of 30; units read went from 12 to 21.
- `molchan_error_diagram`: probability gain is not an objective. It is maximised as alarm time goes to zero, so optimising it selects a rule that almost never fires. The error diagram plots alarm fraction against missed fraction with a no-skill line at exactly 1.0. This diagnoses a failure already in our own stress table, where `conservative_abstain` scores perfectly on clean trials and 0.00 robustness under tool loss.
- `cascade_forecast`: forecasting a self-exciting stream from observed events alone is short by the total-descendants factor 1/(1−n), because activity over the horizon is dominated by events triggered by events that have not happened yet. The card carries the source's own qualification that the naive forecast's relative evolution is often good enough.
- `KC-JUDGMENT-AGGREGATION` imports List and Pettit's impossibility result: a set of logically connected markets can be collectively incoherent with every participant individually coherent, because each leg attracts its own population and the majorities diverge. It contradicts `KC-EVENT-TREE-CONSTRAINTS` on purpose. The theorem's escape route is convergence, which makes it testable on data nobody else has — coherence should track participant overlap across legs, and both venues publish addresses.
- Also compiled `KC-EARLY-WARNING-FRAGILITY` (critical slowing down is real and its false-positive rate is the binding constraint) and `KC-STRATEGY-CAPACITY` (a strategy's return declines toward a carrying capacity).
- Bulk rights verification: 92 landing pages read, rights confirmed on 405 entries went from 28 to 66. Three new CC BY sources cleared into the manifest, which now admits 9 entries across four use classes. 52 pages were read in full and grant nothing, so they are settled as `all_rights_reserved` rather than left as unknowns.
- 19 methods with 22 closed-form checks, 30 servable concepts, 16 hypotheses, 34 decision cards, 22 labelled trials, 5,154 indexed passages. `decision_value` holds precision 1.00 and correct abstention 1.00 with robustness 0.95 and zero integrity violations; `raw_similarity` now commits 656.

## 0.13.0 - 2026-08-06

- Added `scripts/passages.py`: passage retrieval over the sources we hold, and the analysis brief built on it. `knowledge.py retrieve` answers a structured decision context; this answers a question in prose, which is the shape analysis work actually has. A brief returns the compiled concepts that bear on the question with their assumptions and contradictions, the union of their failure modes as *what would change the answer*, ranked passages with exact locators, the unread units in sources we hold, what is catalogued and relevant but not on disk, and the open bets and extensions on the same ground.
- Passages are subordinate to concepts by construction. A nearest passage is selected because its words resemble the query, not because its mechanism applies, so passages appear as evidence anchors under a compiled claim and as a reading queue, never as the answer.
- **The rights gate is on output, not on indexing.** Everything we hold is indexed so search can find it; `ingest_*` results carry a snippet, `reference_only` and `needs_review` results carry the locator, the matched terms and where to open it, and nothing else. A brief is written to be carried into an analysis and onward, so text that may not be redistributed must not ride along inside it. `--quote-local` overrides the printing for personal reading and says so; it does not change the licence, and the `quotable` flag stays false.
- Corpus-wide vocabulary is floored out of the ranking. In a corpus entirely about order books, "orders" and "position" clear any generic stopword list and are still noise, so the floor comes from the corpus: a term in more than a quarter of passages cannot discriminate. When every word in a question is corpus-wide the brief returns no passages and says why, rather than ranking on page length.
- Indexed 3,540 passages from 32 sources with `pdftotext`, no new Python dependency. One held source has no text layer at all and is reported rather than silently contributing nothing.
- 377 to 405 entries. `defi_mechanics` was 155 pages against a 20,000 target while being one of the three live workstreams, which was the worst mismatch in the corpus: added perpetual-futures pricing, DeFi liquidation mechanics, oracle manipulation, blockchain extractable value, proposer-builder separation, AMM-versus-book venue competition and fee-adjusted LVR. Added Kalshi and the CFTC event-contract rules as the regulated comparison case for the prediction-market workstream, which states in a rulebook what Polymarket leaves to convention.
- Closed 14 co-cited frontier targets, leaving 11: the Biais-Glosten-Spatt survey, Lehalle and Neuman on execution with signals, Hamilton's regime-switching paper, Shiryaev's optimal stopping, Kleinrock volume II, Gai and Kapadia on contagion, percolation theory, point processes volume II, the two-time-scales result, universal portfolios, Wasserstein distributionally robust optimization and POMDP planning.

## 0.12.0 - 2026-08-06

- `resolve.py study` downloads reading copies of full texts the publisher already serves for free, and is deliberately separate from `fetch`. `fetch` builds the corpus and is gated by the manifest, because putting a text into a corpus is a distribution and a derivative use. Reading a paper served free is neither, and the corpus model already drew that line — `reference_only` means read it, learn from it, write our own explanations, do not copy it in, and a study copy is the "read it" half. Nothing in `study` moves a rights tag or a use class; only `acquisition` changes. Keeping the two ledgers apart is the point, because a folder of PDFs is not a licence.
- Resolution roughly doubled by putting the author surname and the year into the Crossref query rather than only checking them afterwards. A sharper query lets the match rule stay strict instead of having to loosen it.
- A preprint DOI beside a publisher DOI for the same title is now one work with two locations rather than an ambiguity. Previously this refused a large share of the recent literature for being findable in two places.
- Added arXiv as a second index. Its Atom API refuses this environment outright — persistent 429 on every query, including at the documented three-second delay — so the resolver reads the public search results page, parsing the *originally announced* date rather than the submission date, because a v3 revision would place a 2015 paper in 2024 and fail the year check for the wrong reason. Backoff and retry on 429, never recording a throttle as "this paper does not exist".
- **295 PDFs, 176 MB, across 34 entries.** 5 MIT OpenCourseWare courses under CC BY-NC-SA — the only openly licensed material and the only material `fetch` will take — plus study copies from publisher sites, institutional repositories and course pages. Every study copy keeps the rights tag it arrived with; only `acquisition` moved.
- Added a circuit breaker for a blocked index. arXiv throttled partway through a sweep, and the resolver now abandons that index after six consecutive failures and reports it, rather than grinding two hundred more titles at eighty seconds each and turning a block into two hundred silent misses.
- Twenty more adjacent-discipline entries, 377 total. Seismology deepened where the transfer is strongest: Omori decay as the kernel exponent we do not estimate, Helmstetter and Sornette's ceiling on how much predictability a self-exciting process can offer, the CSEP testing centre, probability gain as a forecast currency, and operational earthquake forecasting — a field that had to decide in public what to do with a real but small probability gain, which is the abstention problem with lives attached.
- Added epidemiology (the reproduction number is a branching ratio estimated in real time under reporting delay, and that literature solved the delay correction first), fisheries management strategy evaluation (simulation-test a rule against worlds you cannot distinguish, then deploy the rule rather than the model — Gate 2 done properly), decision curve analysis (score a model by net benefit across decision thresholds, not by AUC), critical slowing down with its false-positive catalogue, market ecology as carrying capacity, the favourite-longshot bias, and Rasmussen on systems drifting to the safety boundary under efficiency pressure.

## 0.11.0 - 2026-08-06

- Added `scripts/resolve.py`: the deterministic resolver the design called for and never had. `identify` fills in identifiers from Crossref, `licence` reads the licence off the landing page, `fetch` downloads what the manifest already admits. Matching refuses rather than guesses — title similarity, a one-year window and an author check, with a containment path for truncated registry titles that demands an exact year and a matching author.
- An API error is now distinct from a negative result and is never cached. The first run against OpenAlex silently recorded 216 quota failures as "no such work", which is precisely how a resolver stops working while still printing a plausible number.
- **First real acquisition.** 5 MIT OpenCourseWare courses confirmed CC BY-NC-SA by reading both the terms page and each course page, then 109 PDFs and 37 MB downloaded through the rights gate. 20 publisher pages were read in full and grant nothing, so they are now `all_rights_reserved, confirmed` and off the verify queue; 20 more sit behind a bot wall and are recorded as unresolved rather than assumed.
- Recorded what arXiv actually grants. The default is a licence to arXiv to distribute, not a licence to us, and the resolver refuses to read it as an open licence. arXiv is the largest pool of freely readable material the corpus touches and almost none of it is ingestable.
- The seed rights assertion now checks the invariant that matters — every manifest-eligible entry carries confirmed rights, an evidence URL and a check date — instead of enumerating which licences are acceptable. The old form broke the moment a real licence was confirmed.
- Added the `adjacent_disciplines` bucket and 31 entries: fields that solved a structurally identical problem for a different reason and never exported the solution. Seismology's ETAS and its prospective CSEP testing regime, meteorological forecast verification and Murphy's calibration/resolution split, actuarial credibility as the derived version of our hand-tuned shrinkage, competing-risks survival for exits with several causes, group-sequential trial design as the live rival to anytime-valid monitoring, the doctrinal paradox for coherent individuals producing an incoherent aggregate, Charnov's marginal value theorem as the exit rule with opportunity cost priced, optimal search theory, multivariate SPC with contribution plots, the base-rate fallacy in intrusion detection, revenue management's bid-price control, accelerated degradation testing, TREC evaluation methodology for Gate 1, correlated polling error, item response theory, and the bullwhip effect.
- Admission to that bucket requires a named DXAP problem with the same shape and refs into the working literature. 52 cross-bucket edges resulted; a discipline with no edge in is a reading list rather than a bridge.
- 326 to 357 entries. `resolve.py self-test` joins `make selftest`, and generated labs now ship the resolver.

## 0.10.0 - 2026-08-06

- Expanded the bibliography from 267 to 326 entries, aimed at the three workstreams rather than at coverage. The canon was already here; what was missing was the machinery for the systems we actually trade.
- **Batched priority queueing.** A consensus batch that serves action classes in a fixed order is a polling system, and no order-book model in the corpus described one. Added Takagi's polling analysis, Jaiswal on non-preemptive priority, both Neuts volumes on matrix-analytic methods for batch arrivals, and Bruneel & Kim and Takagi on discrete-time slotted systems. The intra-batch order is also a consensus artifact, so HotStuff, Kelkar et al on order-fairness for Byzantine consensus, and Tendermint went in alongside — order-fairness sets the ceiling on how much arrival-time priority an on-chain book can ever offer.
- **Probabilistic coherence.** The Polymarket constraint problem is a logic problem before it is a trading problem. Nilsson's probabilistic logic casts joint consistency as a linear program over possible worlds, which subsumes the partition and implication checks; Hansen & Jaumard make it tractable by column generation at event-tree scale. Added with de Finetti on coherence, Hailperin, Gneiting & Raftery on proper scoring rules, Nelsen and Rüschendorf for the Fréchet bounds themselves, and Beiglböck, Henry-Labordère & Penkner for martingale optimal transport — the general statement of the bound the joint-bounds bet uses in its two-market special case.
- **Slow-maturing attribution.** Waudby-Smith & Ramdas is the construction `betting_eprocess` implements and was not in the corpus. Added with Shafer & Vovk, Cameron & Miller and Abadie et al on clustering, Gerber & Green on placebo design, and Joulani et al on online learning under delayed feedback — the defining feature of an agent whose positions mature over days while it acts every few minutes.
- Added the primitives our implemented methods rest on and did not cite: Bandt & Pompe for ordinal patterns, Page for CUSUM, Athreya & Ney for branching processes, Seifert for entropy production. A method that estimates a branching ratio against a corpus with no branching-process text was resting on nothing.
- Also Tóth et al on latent liquidity, Back's continuous-time Kyle, Glosten on the open limit order book with Sandås rejecting it empirically, Duffie & Manso on information percolation, Dixit & Pindyck and the prophet-inequality survey for stopping with a cost of acting, Watts on cascades, and Cardaliaguet & Lehalle on trade crowding.
- 23 co-cited frontier targets closed, 25 remain, and the new entries carry refs so the frontier keeps generating. `defi_mechanics` and `network_science`, the two thinnest buckets, both grew.
- `make smoke-corpus` no longer hardcodes a real work as its fixture. It reads the top frontier target at test time and resolves that, so expanding the seed stops breaking the test — which is what happened to Ho & Stoll the moment it was catalogued for real.

## 0.9.0 - 2026-08-06

- Closed the four workstream problems the venue reads opened and then left uncovered. `knowledge status` had been reporting `PB-BATCH-PRIORITY`, `PB-PHANTOM-LIQUIDITY`, `PB-LOGICAL-ARB` and `PB-AGENT-ATTRIBUTION` as problems with no servable concept; five concept cards, five method bindings, five hypotheses and seven decision cards now cover them. Every problem in the map has a servable concept, and `make smoke-knowledge` asserts it rather than leaving it to be noticed.
- Five deterministic methods, each with closed-form self-tests. `batch_priority_fill` applies HyperCore's intra-batch type hierarchy and reports displacement against the arrival-time counterfactual, plus the cancels that beat an aggressive order which arrived first. `depth_realization` measures executable against displayed depth at the levels a sweep passed through, excluding the deepest level because it is partially consumed by design. `event_tree_constraints` derives the partition set from Polymarket event metadata and splits it into what the token layer enforces and what it leaves free, in the exact shape `prediction_market_consistency` consumes. `betting_eprocess` gives an anytime-valid test and confidence sequence via Ville's inequality. `counterparty_markout` ranks counterparties by shrunk mark-out and measures out-of-sample rank persistence.
- `betting_eprocess` is checked against the property it rests on: the mean capital over every equiprobable null path is exactly one, at every sequence length. A fixed bet reproduces 1.5^wins x 0.5^losses exactly, and an all-wins stream crosses the 5% threshold at the eighth observation and not before.
- `KC-BATCH-PRIORITY` contradicts `KC-MICRO-QUEUE` outright: continuous-time queue position says a late cancel loses, and on a batching venue it wins. Both are servable and scoped by market type, and the new trial `T-NEG-BATCH-ON-CONTINUOUS` checks that the batching card stays out of a continuous-matching context — a case a retriever matching on queueing vocabulary gets exactly backwards.
- Nineteen labelled trials, up from fourteen. `decision_value` keeps precision at 1.00 and correct abstention at 1.00, and its stress robustness rose to 0.94 with zero integrity violations; `raw_similarity` now commits 549.
- Fifteen of the eighteen exploratory extensions name a first computation that exists, up from six. Their scores were deliberately left alone: raising the score of a proposal because an implementation was written for it would let the ranking reward whatever happened to get built.
- Provenance rose from 4 of 20 cards on units someone opened to 9 of 25. Every card added in this release is anchored to venue documentation or to our own schema, both read directly.
- `docs/WORKSTREAMS.md` updated to the new counts, with the ranked next actions re-split: what runs against the warehouse today, and what has a first computation but still needs plumbing — batch reconstruction, account state joined to resting orders, and the sham cards themselves.

## 0.8.0 - 2026-08-06

- Added `docs/WORKSTREAMS.md`: working notes on the three workstreams, what the warehouse captures, ranked next actions, corpus hygiene priorities, the access gap, and the rules the repo enforces — written to be picked up on a local machine.

- Encoded the three live workstreams — Polymarket prediction markets, Hyperliquid L4 order-book research, and LLM-based agentic asset managers — into the problem map with their venue mechanics, so the compile queue and retrieval rank by proximity to work that is actually happening. Added four workstream-specific problems.
- Read venue documentation directly. HyperCore sorts actions within a consensus batch by a type hierarchy — orders without GTC/IOC, then cancels, then GTC/IOC orders — before proposer order, which is not the continuous arrival-time priority every order-book model assumes. Polymarket's conditional-token layer merges a complete set for collateral atomically, which invalidates the leg-by-leg cost model used for logical arbitrage.
- `prediction_market_consistency` 1.1.0 adds `settlement=atomic`, applying the single-transaction hurdle only to partition constraints the token layer actually enforces, and leaving conjunction and implication breaches on the leg-by-leg model.
- Read our own ingest repository and recorded what the warehouse actually captures. The observables vocabulary now matches the schema, including two properties the literature has never had: counterparty addresses on every fill, and order counts per book level. Recorded what is *not* captured, so untestable concepts are visible as such.
- Added nine extensions grounded in venue and schema reads, covering batched queueing with type priority, phantom depth from margin checks at match time, atomic-settlement arbitrage, protocol-enforced constraint boundaries, counterparty informativeness, event-tree constraint derivation, order-count queue composition, oracle-basis cascade decomposition, and a sham-retrieval arm for agentic traces.
- The internal ingest repository is the first `owned_by_us` source in the corpus, so the build manifest is non-empty for the first time.

## 0.7.0 - 2026-08-05

- Added `knowledge/exploratory_extensions.yaml` and `labrat knowledge extensions`: nine proposals for new work extending read literature into our domain, each naming what the source leaves open in its own terms, our specific advantage over the original authors, the novel claim and the experiment that would kill it. The validator refuses any extension not grounded in a corpus unit whose `read_status` is `read` or `compiled`.
- Read primary sources directly and revised accordingly: `FB-CRITICALITY`'s prediction was rewritten after Hardiman, Bercot and Bouchaud show the branching ratio pinned near one for fourteen years and the published rising-reflexivity claim to be an estimator artifact; `FB-NONHERMITIAN` had its novelty cut from 5 to 3 after prior art was located; `FB-IRREVERSIBILITY` was refined from presence to rank after Flanagan and Lacasa show every series they measure is irreversible.
- `time_irreversibility` 1.1.0 adds the deterministic surrogate null the source method treats as essential, and `hawkes_branching_ratio` 1.1.0 adds a scale profile and an explicit warning about the window-scale artifact. Both version bumps forced their method cards to be re-verified.
- Compiled four concept cards from directly-read material, including a contradiction pair drawn from a live disagreement in the literature, with anchors pointing at sections actually read.
- Added six corpus entries with real read units, including one whose authorship was corrected against the source after a misremembering.
- `knowledge status` now reports provenance: how many cards rest on units someone opened versus unread anchors.

## 0.6.0 - 2026-08-05

- Added `knowledge/frontier_bets.yaml` and `labrat knowledge bets`: eleven ranked hypotheses about which advanced-mathematics imports are most likely to pay, each required to carry a sharp prediction, a falsifier, the minimum data and a first computation. Validation refuses a bet that is unfalsifiable, cites a source outside the bibliography, or names an unimplemented computation. Scored by payoff x sqrt(novelty) x testability x maturity - effort.
- Added four frontier probe methods so the top bets are refutable immediately rather than after a research project: `hawkes_branching_ratio` (endogeneity from count dispersion via the Fano identity), `prediction_market_consistency` (Frechet-Hoeffding, implication and partition bounds across correlated binaries, cost-gated per leg), `path_signature` (level-2 iterated integrals and Levy areas, invariant to time reparametrization), and `time_irreversibility` (ordinal-pattern divergence between a series and its reverse). Each has closed-form self-tests: a recovered branching ratio, an exact Levy area, a reversible triangle wave against an irreversible sawtooth, and a sharp joint bound.
- Added Fernholz's stochastic portfolio theory to the corpus, decomposed into reading units, closing the last dangling reference from the bets file.
- Recorded the deliberate non-bets — topological data analysis, quantum portfolio optimization, deterministic chaos prediction, fractal-market narratives, agent-based simulation as evidence — with reasons.

## 0.5.0 - 2026-08-05

- Corpus sources can now be decomposed into `units` — targeted parts of a source ("the chapter about dealer inventory") with their own page estimate, priority, read status and expected concepts. Reading and compiling happen at unit granularity; `labrat corpus reading` ranks the chapter-level queue and distinguishes units that are located from those still needing to be found, and from sources not yet decomposed at all. 15 high-value sources seeded with 41 units.
- Added `knowledge.py stress`: five deterministic perturbations (reworded context, missing observable, tools unavailable, distractor cards, near-duplicate restatements) with per-perturbation scoring modes, plus label-independent integrity violations for serving a card whose data is absent or whose market or horizon does not match.
- `robustness` is now a third decisive challenge in the `dxap-knowledge` profile, so policies are selected for holding up under perturbation rather than for fitting the labelled trial set.
- Added `corpus.py self-test` and `knowledge.py self-test` covering adversarial input: unevidenced confirmations, hollow licence grants, excluded and unknown sources, verbatim quotes from restricted material, unbacked implementation claims, version drift, dangling relations, costless hypotheses, each retrieval filter in isolation, unicode and CJK titles, and degenerate empty stores. `make selftest` runs all five engines; both smoke paths depend on it.

## 0.4.0 - 2026-08-05

- Added the executable-bibliography layer: `scripts/knowledge.py` compiles sources into concept, hypothesis, method-binding and decision-relevance cards behind a SERVABLE gate that requires a mechanism, assumptions, observables, an expected signature, counterevidence, and resolvable source anchors — and refuses a verbatim quote from a source whose rights do not permit it.
- Added `scripts/methods.py`: eight deterministic, versioned market methods (order flow imbalance, Kyle's lambda, Avellaneda-Stoikov quotes, Almgren-Chriss schedule, local-level Kalman filter, CUSUM change detection, continuation hazard, binary LMSR), each declaring its as-of contract and numerical failure modes, each with closed-form self-tests. Method bindings pin the implementation version, so a numerical change fails validation until the card is re-verified.
- Added structured retrieval: hard structural filters (market, horizon, available observables, point-in-time source availability, decision type) before scoring, a decision-value re-rank, MMR diversity, explicit abstention, and a one-hop expansion that must carry counterevidence.
- Added `scripts/ledger.py`: the offered-to-beneficial attribution ladder, deterministic arm assignment, cluster-level bootstrap comparison, and utility posteriors — refusing to estimate an effect on unmatured outcomes or an unfrozen batch.
- Added `scripts/graphops.py`: personalized PageRank, Brandes betweenness, co-citation, bibliographic coupling, deterministic communities, MMR and greedy submodular coverage, all self-tested on hand-computable graphs.
- Added the `dxap-knowledge` profile: 16 concept cards, 8 hypotheses, 8 method bindings, 18 decision-relevance cards and 14 labelled retrieval trials across four verticals. Candidates are retrieval policies; decisive challenges are correct abstention on inapplicable contexts and counterevidence coverage.
- Profiles now stack: repeat `--profile` to overlay several, later profiles winning on conflicting files.
- Added `docs/KNOWLEDGE.md`, `make smoke-knowledge` and `make selftest`; `make test` now runs every smoke path.

## 0.3.0 - 2026-08-05

- Added `labrat corpus`: bibliography network mapping, iterative scouting rounds, and form/rights tagging, with a rights-gated build manifest that only admits entries carrying confirmed rights, an evidence URL, and a check date.
- Added the `quant-finance-corpus` profile — a 173-entry seed bibliography across market microstructure, quantitative finance, information economics, signal processing, detection and tracking, control, operations research, queueing, information theory, Bayesian statistics, sequential decision theory, dynamical systems, network science, exchange documentation, open courseware, and practitioner training — where candidates are scouting policies and the decisive challenges are cross-domain bridge discovery and rights clearance.
- Added corpus operator surfaces for both interfaces: `/corpus-round` and `/corpus-status` for Claude Code, the `corpus-scout` skill for Codex, and a shared round contract under `agent_prompts/shared/`.
- Added `docs/CORPUS.md` and a `make smoke-corpus` end-to-end check; `make test` now runs both smoke paths.
- Generated labs now ship `scripts/corpus.py`.

## 0.2.3 - 2026-04-23

- Synced the Simplified Chinese README with the current CLI, profile, Codex skill, and runner guidance.
- Cleaned up smoke-test wording so generated-lab checks describe both Codex and Claude Code surfaces.

## 0.2.2 - 2026-04-23

- Updated Codex guidance for GPT-5.5 availability in Codex, without tying the lab runtime to API model strings.
- Clarified Codex `AGENTS.md` layering so lab-local instructions govern runtime operation inside nested labs.
- Expanded the `labrat-operator` skill around Codex discovery, Plan mode, review, subagents, MCP, and verification.

## 0.2.1 - 2026-04-23

- Added frontier-model operating guidance for Codex and Claude Code lab supervision.
- Added an optional repo-scoped `labrat-operator` Codex skill and included it in generated labs.
- Tightened runner docs around completion criteria, verification, reasoning-effort choice, and trusted-source research.
- Kept model-specific docs conservative: the lab runtime uses host-selected model settings instead of hardcoded API model IDs.

## 0.2.0 - 2026-04-21

- Added a first-class installable `labrat` CLI, including `labrat doctor`, JSON status outputs, and `labrat --version`.
- Added repo-root and lab-root operator guidance so Codex and Claude Code are both supported as primary orchestration interfaces.
- Added `AGENTS.md` to scaffolded labs, synced the canonical example lab with agent guidance files, and clarified runner docs in the README and supporting docs.
- Switched runtime-owned file writes to atomic helpers for safer local state updates.
