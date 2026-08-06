# DXAP workstreams: state, and where to pick it up

Working notes for the corpus and knowledge work as it stands. Written to be picked up on a local machine, so it says what exists, what was actually read, what is ranked, what is blocked, and what to do next.

Everything below lives in two profiles that stack:

```bash
labrat new ~/labs/dxap --profile=quant-finance-corpus --profile=dxap-knowledge
cd ~/labs/dxap
python scripts/corpus.py status
python scripts/knowledge.py status
python scripts/knowledge.py extensions --verbose
```

## The three workstreams

Encoded in `knowledge/problems.yaml` under `workstreams`, because the compile queue seeds a personalized PageRank there and retrieval filters on it. Literature that touches none of them is a distraction, not a neutral addition.

| Workstream | Venue mechanics that matter | Reading priorities |
|---|---|---|
| **Polymarket** | CLOB, not a scoring-rule maker. Conditional Token Framework: splitting collateral mints a complete set, merging a complete set returns collateral **atomically**. Negative-risk markets convert one NO into YES across the other outcomes. | economics_information, mathematical_foundations, exchange_documentation |
| **Hyperliquid L4** | Fully on-chain CLOB with price-time priority, but actions inside a consensus batch are sorted **orders without GTC/IOC → cancels → GTC/IOC orders**, proposer order inside each category, 1–2 batches per block. Margin checked on open *and again for the resting side at each match*. | queueing_networks, market_microstructure, mathematical_foundations |
| **DXAP agents** | LLM agents with tools, memory and triggers; path-dependent decisions; outcomes mature far slower than the agent acts. | inference_causality, decision_sequential, machine_learning_frontier |

Two of those facts invalidate standard modelling:

- **Batch type-priority is not arrival-time priority.** Every order-book queueing result — birth-death, queue-reactive, heavy traffic — assumes continuous arrival. Cancels being processed *before* aggressive orders in the same batch is a structural maker protection no CEX offers.
- **Atomic merge removes leg risk.** Cross-market arbitrage literature prices logical inconsistency leg by leg because everywhere it studies, legs can come apart. For constraints the token layer enforces, they cannot. `prediction_market_consistency` 1.1.0 now takes `settlement=atomic` and applies it *only* to partition constraints, since no token operation enforces a conjunction bound.

## What the warehouse actually captures

Read from `ProjectDXAI/hyperliquid-ingest` at commit `eca892b`, migrations `00001` and `00015`. Recorded in `knowledge/problems.yaml` under `observables_available`, including an explicit `not_captured` list — a retrieval filter naming observables we do not have is fiction.

Two properties the published literature has never had:

- **`hl_trades.buyer` and `hl_trades.seller`** — counterparty addresses on every fill. The empirical microstructure literature spends enormous effort *inferring* what this column states outright. It also means trade-classification rules can be validated against ground truth rather than assumed.
- **`hl_l2_book_levels.order_count`** — order counts per level alongside size. Queueing models of the book are written in aggregate size; a level held by one large order and one held by twenty small orders are the same state to those models and are obviously different systems.

Also captured and unused: `mark_px` and `oracle_px` alongside `mid_px` with `funding` and `open_interest` (so the mechanical trigger of liquidation is observable, not inferred), and Polymarket snapshots keyed to `event_id` / `event_ticker` / `series_id` with `mentioned_symbols` and `tracked_coin` (so the logical constraint set and the cross-venue link are already in the schema).

Not captured: own-order queue rank, individual order lifecycle events, fee schedule.

## Where the work stands

```
267 bibliographic records · 60 reading units · 12 units actually read
25 concept cards (9 anchored to a read unit, 16 to unread anchors)
16 method bindings at pinned versions · 17 implemented methods
11 frontier bets · 18 exploratory extensions (15 with a runnable first computation)
19 labelled retrieval trials · every diagnosed problem has a servable concept
manifest: 1 entry eligible at seed (our own repo); a confirmed CC course clears in the smoke round
```

`python scripts/knowledge.py status` prints the provenance line. **9 of 25 cards rest on a unit someone opened**, and every card added since the first reading pass is one of them. Seeding from working knowledge is a legitimate way to start; leaving it that way silently is not.

The four workstream problems the venue reads opened are now covered: `KC-BATCH-PRIORITY`, `KC-PHANTOM-DEPTH`, `KC-EVENT-TREE-CONSTRAINTS`, `KC-ANYTIME-ATTRIBUTION` and `KC-COUNTERPARTY-INFO`, each with a bound method and a hypothesis carrying a cost model. `make smoke-knowledge` now fails if any problem in the map has no servable concept, so the next gap announces itself.

## Ranked next actions

### Runnable today against the warehouse

1. `EXT-EVENT-TREE-CONSTRAINTS` (8.2) — `event_tree_constraints` derives the partition set from `pm_market_snapshots` grouped by `event_id` and marks which partitions the token layer enforces; feed its `enforced` rows straight into `prediction_market_consistency` with `settlement=atomic`. The two compose without translation and the smoke path checks that they do. What is left is pointing it at a week of real snapshots.
2. `EXT-CTF-ATOMIC-ARB` (5.8) — the enforced/free split is what `event_tree_constraints` returns. Price each class against its true hurdle and compare against what could actually have been executed.
3. `EXT-COUNTERPARTY-FLOW` (5.3) — `counterparty_markout` ranks addresses by shrunk mark-out and measures out-of-sample rank persistence. Needs mark-outs computed from `hl_trades` joined to a mid-price series; the statistic itself is done.
4. `EXT-FANO-EXPONENT` (3.8) — pure theory plus simulation, small enough to finish: derive how the Fano-based `n(w)` grows with aggregation scale under a power-law kernel, invert to read the exponent.

### First computation exists; the data plumbing does not

- `EXT-BATCH-QUEUE` — `batch_priority_fill` takes a batch and returns the execution order, the arrival-time counterfactual and the cancels that escaped an earlier aggressive order. It takes the batch as given, so reconstructing batch boundaries from the feed is the remaining work, and a wrong reconstruction invalidates every number it produces.
- `EXT-PHANTOM-DEPTH` — `depth_realization` measures the shortfall between displayed and executable depth. It cannot attribute the shortfall to margin rather than to ordinary cancellation; that needs account-level state joined to resting orders.
- `EXT-AGENT-SHAM-ARM` — `betting_eprocess` is the monitor for the comparison. The sham cards themselves — matched for length, structure and citation density, wrong on market and horizon — still have to be generated. Without that arm, every retrieval benefit measured on agents is confounded with the deliberation effect.
- `EXT-ORDER-COUNT-QUEUE`, `EXT-LVR-DISCRETE`, `EXT-VENUE-LAG-NULL` — the three proposals still naming no first computation at all.

### Corpus hygiene, highest leverage first

```bash
python scripts/corpus.py rights --verify-queue --limit 20   # 266 sources held, 0 verified
python scripts/corpus.py reading --limit 15                 # 48 units unread
python scripts/corpus.py frontier --limit 20                # 47 open targets
```

The binding constraint is no longer coverage. It is that **266 of 267 sources have never had their rights checked**, and **48 of 60 reading units are unopened**. Two `verify` rounds on `open_courseware` and the venue documentation would move the manifest more than another hundred entries.

The single most load-bearing unknown: `hyperliquid-api-docs#market-data-feeds` is marked unread, and whether resting orders carry a persistent publicly visible owner decides how much of the L4 workstream is possible. Open that unit next.

## Access gap — what could not be read

Three paths were named that this environment cannot reach, because sessions run in a remote container holding only the cloned repos:

- `/Users/punkyrest/polymarket-mm`
- `/Users/punkyrest/Documents/HyperLiquidL4Collection`
- `/Users/punkyrest/DXT Reports`

`list_repos` shows no GitHub counterpart for any of the three. `ProjectDXAI/hyperliquid-ingest` was attached and read, and it is clearly related to the L4 collection work but is a data-capture service rather than the collection itself.

To get them read: push each to GitHub and name it, or paste the material. Until then, anything proposed about the market-making implementation, the L4 collection, or the DXT reports would be invented rather than read — and `knowledge extensions` will refuse to rank it, because the grounding rule requires a unit marked read.

## The rules this repo enforces, so they are not accidentally undone

- **SERVABLE gate** — a card needs a mechanism, assumptions, observables, expected signature, failure modes, counterevidence, and resolvable anchors. No contradicting concept and no alternative explanation means it does not serve.
- **Rights gate** — nothing reaches the manifest without confirmed rights, an evidence URL and a check date. Free to read is not licensed; a purchase is not a clearance. Verbatim quotes are refused from sources whose rights forbid them.
- **Version pin** — a method card names its implementation version. A numerical change fails validation until someone re-verifies the card.
- **Point-in-time** — retrieval refuses sources published after the decision timestamp.
- **Read-grounding** — an extension must cite a unit whose `read_status` is `read` or `compiled`. This one caught three of my own proposals on first run.
- **Ledger refusal** — no effect estimate on unmatured outcomes or an unfrozen batch.

`make test` runs all three smoke paths plus five engine self-tests, and each of those rules has an assertion behind it.
