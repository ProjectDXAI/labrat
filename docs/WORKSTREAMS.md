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
267 bibliographic records · 57 reading units · 12 units actually read
20 concept cards (4 anchored to a read unit, 16 to unread anchors)
11 method bindings at pinned versions · 12 implemented methods
11 frontier bets · 18 exploratory extensions
manifest: 2 entries eligible — our own repo, plus one confirmed CC course
```

`python scripts/knowledge.py status` prints the provenance line. **4 of 20 cards rest on a unit someone opened.** Seeding from working knowledge is a legitimate way to start; leaving it that way silently is not.

## Ranked next actions

### Runnable today, no new data

1. `EXT-EVENT-TREE-CONSTRAINTS` (8.2) — group `pm_market_snapshots` by `event_id`, treat each group as a partition, run `prediction_market_consistency --settlement atomic`, measure how often it fails to sum to one beyond the cost hurdle. Everything needed is already in the warehouse.
2. `EXT-CTF-ATOMIC-ARB` (5.8) — split constraints into protocol-enforced and free, price each against its true hurdle, compare against what could actually have been executed.
3. `EXT-COUNTERPARTY-FLOW` (5.3) — rank addresses by realized mark-out of their aggressive flow, test out-of-sample persistence.
4. `EXT-FANO-EXPONENT` (3.8) — pure theory plus simulation, small enough to finish: derive how the Fano-based `n(w)` grows with aggregation scale under a power-law kernel, invert to read the exponent.

### Needs a decision or new plumbing

- `EXT-BATCH-QUEUE` — the queueing model for type-prioritized consensus batches. Highest novelty in the file; needs batch reconstruction from the feed.
- `EXT-AGENT-SHAM-ARM` — matched-but-irrelevant cards alongside the real retrieval arm. Without it, every retrieval benefit measured on agents is confounded with the deliberation effect.
- `EXT-PHANTOM-DEPTH` — needs account-level state joined to resting orders.

### Corpus hygiene, highest leverage first

```bash
python scripts/corpus.py rights --verify-queue --limit 20   # 266 sources held, 0 verified
python scripts/corpus.py reading --limit 15                 # 45 units unread
python scripts/corpus.py frontier --limit 20                # 47 open targets
```

The binding constraint is no longer coverage. It is that **266 of 267 sources have never had their rights checked**, and **45 of 57 reading units are unopened**. Two `verify` rounds on `open_courseware` and the venue documentation would move the manifest more than another hundred entries.

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
