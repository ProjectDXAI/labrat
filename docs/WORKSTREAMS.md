# Working notes: state, and where to pick it up

**What this corpus is for.** Exploratory understanding of structural mathematics that may or may not touch the trading work — a place to track findings and pathways as they accumulate, and to seed an AI coding agent with creative direction when building. It is not a licensing exercise and not a justification layer for trades.

**Rights are metadata, not a gate.** Recorded so a redistributable build stays possible later; ignored otherwise. Nothing should stop a source being read. The taxonomy records `mode: exploratory` for this reason, and neither reading path consults rights status.

**The primary artifact is `knowledge/structural_findings.yaml`** — patterns that span two or more domains, each with what it buys and an `agent_seed` written for whoever builds in that area next.

```bash
python scripts/knowledge.py findings --verbose         # the findings, grouped and marked
python scripts/knowledge.py findings --status tension  # and the one that does not resolve
python scripts/corpus.py reading --limit 15            # what to open next
```

Everything below lives in two profiles that stack:

```bash
labrat new ~/labs/dxap --profile=quant-finance-corpus --profile=dxap-knowledge
cd ~/labs/dxap
python scripts/corpus.py status
python scripts/knowledge.py status
```

## Where the work stands

```
468 bibliographic records · 70 decomposed into 125 units · 68 units read
25 structural findings (23 read, 1 tension, 1 conjecture)
43 concept cards, all servable (27 anchored to a read unit, 16 to unread anchors)
23 methods · 11 frontier bets · 18 exploratory extensions
68 units read but not yet compiled — the current backlog
```

Reading is the binding constraint, and it always has been. Every finding in the file came from opening something; none came from adding another entry to the bibliography.

## What the reading has produced

The findings file is the output. Some of it bears on the trading work and some of it plainly does not, which is the intended shape. The patterns that keep recurring are recorded at the bottom of that file under `recurring_shapes`; the ones that have shown up more than once so far:

- **One inequality underwriting several apparently separate capabilities** — a maximal inequality behind continuous monitoring, a dissipation identity behind model cost, an uncertainty relation behind precision.
- **An invariant enforced by the mechanism rather than by the participants** — atomic settlement in the token layer, categorical priority in a consensus batch, and convex-order barriers implied by two marginals with no model at all.
- **The mechanism decides which strategies exist, before it decides which pay** — first-come-first-served makes frontrunning inexpressible rather than expensive; a CLOB carries combinatorial structure no tractable scoring-rule maker could quote.
- **The same object under two names in two fields with no shared citations** — adverse selection and loss-versus-rebalancing; market-maker subsidy and learner regret; and, joining those, market-maker pricing and natural gradient descent.

Two results worth naming here because they change how anything gets evaluated:

- **Backtest optimism is a closed form.** `R_in² / (1−q) = R_true² = (1−q) R_out²` with `q = N/T`, for a completely general population covariance. The in-sample number understates realized risk by exactly `(1−q)²`, and at `q = 1` in-sample risk is zero while out-of-sample risk diverges. No holdout is needed to correct it — it is arithmetic on two integers any harness already knows.
- **Quoting is harder than matching.** The LMSR cost function over permutations is `b log perm(B)`, so pricing is #P-hard while matching the same divisible bet language is polynomial. A CLOB can carry combinatorial structure no tractable scoring-rule maker could quote, and the incoherence it permits is what buys the tractability.
- **A corrective re-sort inherits the bias it was meant to remove.** Sui linearizes a committed sub-DAG by validator index — an 89% same-round ordering win with no attacker — and the gas-price re-sort that supposedly fixes this is a *stable* sort whose key is tied whenever transactions pay the reference price. Both stages are individually correct. Our venue has the same shape: proposer order breaks ties inside a batch category, so any downstream price-time rule inherits it on every equal-priced pair.
- **Irreversibility has a closed form, and it is what makes eigenvalues untrustworthy.** The nearest reversible chain is the arithmetic mean of a kernel and its time-reversal, so `D(P || P_m)` needs no surrogate null — implemented as `reversible_projection`. Reversibility is also exactly the condition under which eigenvalue perturbation is dimension-free, which joins the irreversibility reading to the random-matrix one.

The one open tension, `FIND-EXPONENT-TENSION`, is unresolved on purpose: measured Hawkes kernel exponents on equity flow sit near 0.15–0.45, `H ≈ 0.1` implies `α ≈ 0.6`, and the scaling theorem needs `α > 1/2` to give roughness at all. The three cannot all be right about the same object.

## Context: what the trading work actually is

Recorded so a reader knows what the applied side looks like, **not** as a filter on what is worth reading. Plenty of what is in the findings file connects to none of it.

| Workstream | Venue mechanics that matter |
|---|---|
| **Polymarket** | CLOB, not a scoring-rule maker. Conditional Token Framework: splitting collateral mints a complete set, merging a complete set returns collateral **atomically**. Negative-risk markets convert one NO into YES across the other outcomes. |
| **Hyperliquid L4** | Fully on-chain CLOB with price-time priority, but actions inside a consensus batch are sorted **orders without GTC/IOC → cancels → GTC/IOC orders**, proposer order inside each category, 1–2 batches per block. Margin checked on open *and again for the resting side at each match*. |
| **DXAP agents** | LLM agents with tools, memory and triggers; path-dependent decisions; outcomes mature far slower than the agent acts. |

Two venue facts invalidate standard modelling:

- **Batch type-priority is not arrival-time priority.** Every order-book queueing result — birth-death, queue-reactive, heavy traffic — assumes continuous arrival. Cancels being processed *before* aggressive orders in the same batch is a structural maker protection no CEX offers.
- **Atomic merge removes leg risk.** Cross-market arbitrage literature prices logical inconsistency leg by leg because everywhere it studies, legs can come apart. For constraints the token layer enforces, they cannot.

## What the warehouse actually captures

Read from `ProjectDXAI/hyperliquid-ingest`, migrations `00001` and `00015`. Recorded in `knowledge/problems.yaml` under `observables_available`, including an explicit `not_captured` list — a retrieval filter naming observables we do not have is fiction.

Two properties the published literature has never had:

- **`hl_trades.buyer` and `hl_trades.seller`** — counterparty addresses on every fill. The empirical microstructure literature spends enormous effort *inferring* what this column states outright.
- **`hl_l2_book_levels.order_count`** — order counts per level alongside size. Queueing models of the book are written in aggregate size; a level held by one large order and one held by twenty small orders are the same state to those models and are obviously different systems.

Not captured: own-order queue rank, individual order lifecycle events, fee schedule.

## Ranked next actions

### Compile the backlog

68 units are read and not yet compiled. That is now the largest gap in the system — material has been opened and the cards do not reflect it. `python scripts/knowledge.py compile-queue` ranks it.

### Read next

`python scripts/corpus.py reading --limit 15` ranks the 57 unopened units and, since the queue no longer surfaces units anyone has already read, its top rows are now real work.

### Runnable today, no new data

1. `EXT-EVENT-TREE-CONSTRAINTS` — group `pm_market_snapshots` by `event_id`, treat each group as a partition, run `prediction_market_consistency --settlement atomic`.
2. `EXT-CTF-ATOMIC-ARB` — split constraints into protocol-enforced and free, price each against its true hurdle.
3. `EXT-COUNTERPARTY-FLOW` — rank addresses by realized mark-out of their aggressive flow, test out-of-sample persistence.
4. `EXT-FANO-EXPONENT` — theory plus simulation, small enough to finish, and it bears directly on the open tension above.

### Needs a decision or new plumbing

- `EXT-BATCH-QUEUE` — the queueing model for type-prioritized consensus batches. Highest novelty in the file; needs batch reconstruction from the feed.
- `EXT-AGENT-SHAM-ARM` — matched-but-irrelevant cards alongside the real retrieval arm. Without it, every retrieval benefit measured on agents is confounded with the deliberation effect.
- `EXT-PHANTOM-DEPTH` — needs account-level state joined to resting orders.

## Access gap — what could not be read

Three paths were named that this environment cannot reach, because sessions run in a remote container holding only the cloned repos:

- `/Users/punkyrest/polymarket-mm`
- `/Users/punkyrest/Documents/HyperLiquidL4Collection`
- `/Users/punkyrest/DXT Reports`

`list_repos` shows no GitHub counterpart for any of the three. `ProjectDXAI/hyperliquid-ingest` was attached and read; it is clearly related to the L4 collection work but is a data-capture service rather than the collection itself.

To get them read: push each to GitHub and name it, or paste the material. Until then, anything proposed about the market-making implementation, the L4 collection, or the DXT reports would be invented rather than read — and `knowledge extensions` will refuse to rank it, because the grounding rule requires a unit marked read.

Note also that acquired PDFs live outside git by design, so a fresh container holds none of them. Reading resumes from open sources or from a re-run of the acquisition path.

## The rules this repo enforces, so they are not accidentally undone

- **SERVABLE gate** — a card needs a mechanism, assumptions, observables, expected signature, failure modes, counterevidence, and resolvable anchors. No contradicting concept and no alternative explanation means it does not serve.
- **Rights** — recorded as metadata in exploratory mode, not enforced anywhere in the reading path. The manifest machinery still works if a redistributable build is ever wanted.
- **Version pin** — a method card names its implementation version. A numerical change fails validation until someone re-verifies the card.
- **Point-in-time** — retrieval refuses sources published after the decision timestamp.
- **Read-grounding** — an extension must cite a unit whose `read_status` is `read` or `compiled`. This one caught three of my own proposals on first run.
- **Findings grounding** — a `read` or `tension` finding must name the sources read; a `tension` must state its open question; every finding must span at least two domains.
- **Reading queue honesty** — a unit anyone has opened leaves the reading queue and is counted as `units_awaiting_compile` instead. Without this the queue ranked already-read units first, because reading raises no score.
- **Ledger refusal** — no effect estimate on unmatured outcomes or an unfrozen batch.

`make test` runs the smoke paths plus the engine self-tests, and each of those rules has an assertion behind it.
