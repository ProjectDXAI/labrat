# Research brief — quantitative finance corpus

## What we want to learn

Which scouting policy builds a dense, legally usable knowledge corpus fastest for markets work: chasing citations, mining syllabi, verifying rights, sweeping venue documentation, or hunting cross-domain bridges?

The output is two artifacts, not a paper:

1. **A bibliography network** — the works that matter across market microstructure, quantitative finance, information economics, statistical signal processing, control, operations research, queueing, information theory, Bayesian statistics, sequential decision theory, dynamical systems, network science, exchange documentation, open courseware, and practitioner training — mapped as a graph, with the frontier of works-we-know-exist-but-have-not-catalogued kept explicit.
2. **A rights-tagged manifest** — the subset of that network that can actually be built into a corpus, each item carrying a form tag, a rights status, an evidence URL, and a check date.

## Why this is worth running as a lab

The material we want is unevenly represented in general pretraining. Papers, blogs, GitHub and forums are over-represented; graduate textbooks, course notes, exchange technical documentation, and desk training material are under-represented, and they are far denser per page.

But "go find good books" is not a plan. Three things make it a search problem worth running with a scoreboard:

- **The frontier is not obvious.** What a literature considers load-bearing is visible in its reference network, not in search rankings. Co-citation support is a usable prior that costs nothing.
- **Volume is the wrong objective.** A round that adds twenty more microstructure papers is worth less than one that connects queueing theory to order book dynamics. Transfer comes from abstractions that move between fields.
- **Rights are the binding constraint.** Most of the densest material is commercially copyrighted. A round that catalogues a hundred works and clears none of them has produced a reading list. The scoreboard has to price clearance, or the search optimizes the wrong thing.

## Baseline

`baseline_broad_sweep`: one expansion round, no bucket filter, no channel constraint, limit 20 — "just go find more." Every family has to beat that.

## Metrics

- `search_eval` — productivity: new entries, frontier targets closed, entries materially improved.
- `selection_eval` — legally usable value added: manifest-eligible pages gained, plus the confirmation rate.
- `final_eval` — share of the touched buckets' page targets that is now manifest-eligible.

Two decisive challenges, neither of which volume can buy:

- `bridge_discovery` — cross-bucket connections created per new entry.
- `rights_clearance` — share of works touched that ended with a confirmed, evidence-backed rights tag.

## What good looks like

A family earns credits by lifting `selection_eval` *and* winning at least one decisive challenge. Specifically we expect, and want the runtime to test:

- `citation_chase` wins early on volume and defines the core, then saturates.
- `syllabus_mining` and `rights_first` should own `rights_clearance`; if they do not, the open-licence thesis is wrong and the corpus is smaller than we hoped.
- `bridge_hunting` should keep winning `bridge_discovery` after `citation_chase` saturates.
- `practitioner_channel` is funded low on purpose. If several rounds clear nothing, defund it and record the bucket as reference-only.

## The two-phase candidate

A candidate is a scouting policy, not a model. Running it opens a bounded round and writes `corpus/rounds/round-NNN/request.md`. It returns `failure_class: awaiting_findings` until a scout writes `findings.yaml`; re-running the same candidate merges the findings, closes the round, and scores it.

The runtime never invents bibliographic facts. It decides what to look for, and keeps the accounting honest when the answers come back.

## Saturation

A bucket is `saturated` when two consecutive *expansion* rounds add nothing new and its frontier is empty. Verification rounds never count toward saturation — failing to clear rights says nothing about whether material remains.

Saturation is the stopping rule for this lab. "Exhaustive" means every bucket saturated, not a fixed number of rounds.

## What we are not doing

- No acquisition of confidential, leaked, or NDA-bound material. It is recorded as excluded, once, so it is not rediscovered every round.
- No treating free-to-read as licensed. An author-hosted PDF is `reference_only` until an actual permission says otherwise.
- No page-count padding from the deprioritized categories in `corpus/taxonomy.yaml`.
- No corpus building inside this lab. This lab produces the map and the manifest; the build is downstream and reads `corpus/manifest.json`.
