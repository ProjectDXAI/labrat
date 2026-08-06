# Changelog

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
