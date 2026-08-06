# Corpus building

`labrat corpus` maps a literature as a citation network, expands it in bounded rounds until each area stops yielding, and tags every item with what it *is* (form) and what you may *do* with it (rights). It answers two questions that a reading list cannot: what should we look for next, and what may we actually build with.

The flagship instance is the [`quant-finance-corpus`](../profiles/quant-finance-corpus) profile — market microstructure, quantitative finance, information economics, signal processing, control, operations research, queueing, information theory, Bayesian statistics, sequential decision theory, dynamical systems, network science, exchange documentation, open courseware and practitioner training — but the engine is domain-agnostic. Point it at any taxonomy and any seed bibliography.

## Why a search runtime rather than a spreadsheet

Three properties make corpus assembly a search problem worth scoring:

- **The frontier is not obvious.** What a literature treats as load-bearing shows up in its reference network, not in search rankings. Co-citation support is a free, local prior on importance.
- **Volume is the wrong objective.** Twenty more papers from a bucket you already cover are worth less than one work that connects two buckets. Transfer comes from abstractions that move between fields.
- **Rights are the binding constraint.** The densest material is usually commercially copyrighted. A round that catalogues a hundred works and clears none has produced a bibliography, not a corpus. If the scoreboard does not price clearance, the search optimizes the wrong thing.

## Data model

Everything lives under `<lab>/corpus/`:

```
corpus/
  taxonomy.yaml       buckets, page targets, deprioritized categories, bridge pairs
  bibliography.yaml   the durable store — written by the merge step, not by hand
  state.json          round counter, per-bucket dry-round counters
  rounds/
    round-001/request.json   what the round asked for (targets, coverage snapshot)
    round-001/request.md     the scout's brief
    round-001/findings.yaml  the scout's answers — the only write path into the store
    round-001/merge_report.json
    log.jsonl                one record per closed round
  manifest.json       the rights-gated build manifest
  graph.json          nodes, edges, unresolved frontier, components
  REPORT.md           coverage, rights posture, network shape, round history
```

One entry:

```yaml
- id: harris-2003-trading-exchanges
  title: "Trading and Exchanges: Market Microstructure for Practitioners"
  authors: [Larry Harris]
  year: 2003
  bucket: market_microstructure        # from taxonomy.yaml
  form: textbook                       # what it physically is
  pages: 656                           # estimate until a verify round fixes it
  density: high
  priority: 5
  rights:
    status: all_rights_reserved        # what the licence says
    confidence: inferred               # confirmed | inferred | unknown
    evidence: null                     # the URL you actually read
    checked_at: null
    grant: null                        # an explicit permission we hold, if any
  acquisition: {state: purchasable, copy_path: null}
  refs:                                # the network edges
    - {target: ohara-1995-market-microstructure-theory, relation: builds_on}
    - {target: "Schwartz — Equity Markets", relation: cites}   # unresolved: a frontier target
  status: candidate
```

A `ref` that names a stored entry becomes a graph edge. A ref that names something not yet catalogued becomes a **frontier target** — that is how the network tells you what to look for next.

## Tagging

### Form

`textbook`, `monograph`, `handbook`, `lecture_notes`, `problem_set`, `course`, `paper`, `working_paper`, `survey`, `thesis`, `proceedings`, `rulebook`, `exchange_doc`, `api_doc`, `regulatory_filing`, `manual`, `interview_packet`, `newsletter`, `software_docs`, `dataset`, `standard`, `blog`, `video`, `notes_own`.

### Rights

Each status maps to a **use class**. `labrat corpus vocab` prints the full table.

| Status | Use class |
|---|---|
| `public_domain`, `cc0`, `government_work`, `owned_by_us` | `ingest_full` |
| `cc_by` | `ingest_attribution` |
| `cc_by_sa` | `ingest_share_alike` |
| `cc_by_nc`, `cc_by_nc_sa` | `ingest_noncommercial` |
| `open_license_other` | `ingest_check_terms` |
| `cc_by_nd`, `cc_by_nc_nd` | `reference_only` (corpus building is a derivative use) |
| `author_hosted_free` | `reference_only` (free to read is not licensed) |
| `public_but_restricted` | `reference_only` (most exchange docs and rulebooks) |
| `subscription_required`, `licensed_purchase_required`, `all_rights_reserved` | `reference_only` |
| `proprietary_confidential` | `excluded` |
| `unknown` | `needs_review` |

Two gates then apply:

- **A grant upgrades.** A recorded permission (`rights.grant` with evidence) makes an otherwise restricted work `ingest_licensed`.
- **Missing evidence downgrades.** Anything otherwise ingestable falls back to `needs_review` unless `confidence: confirmed` *and* an `evidence` URL *and* a `checked_at` date are present.

`reference_only` is not a dead end. You may read it, learn from it, and write your own explanations — catalogue those as `notes_own` / `owned_by_us`, which are manifest-eligible on their own terms.

## Books, units, and cards

Three different things, easy to conflate:

| | what it is | where it lives | do we hold it? |
|---|---|---|---|
| **Source record** | Bibliographic metadata: a work exists, in this form, under these rights | `corpus/bibliography.yaml` | No. `pages` counts pages that exist in the world, not pages we have. |
| **Unit** | A target *inside* a source — "the chapter about dealer inventory" | `units:` on an entry | No. A unit has no locator until someone opens the source and fills it in. |
| **Card** | Our own written account of a mechanism, anchored to a unit | `knowledge/concepts.yaml` | **Yes. This is the only content we own.** |

The corpus contains zero bytes of source text and always will. Reading and compiling happen at unit granularity, because a 656-page textbook is not a task:

```yaml
- id: harris-2003-trading-exchanges
  pages: 656                      # exists in the world
  units:
    - unit_id: dealers-and-market-making
      topic: "dealer economics, inventory and the sources of the spread"
      locator: null               # filled in when someone opens the book
      pages: 50
      priority: 5
      read_status: unread         # unread | located | skimmed | read | compiled | abandoned
      concepts_expected: [KC-MM-INVENTORY]
```

```bash
labrat corpus reading --limit 15                    # chapter-level queue, ranked
labrat corpus reading --include-unmapped            # also: sources not yet decomposed
```

Each row carries an `action`: `read` when the unit is located, `map_first` when it is still a topic without a locator, `decompose_source` for a source with no units at all. `status` reports how many sources are decomposed and how many units sit in each read state, so "we have mapped 105,000 pages" never gets mistaken for "we have read them".

## The iterative loop

```bash
labrat corpus status                              # coverage, rights posture, saturation
labrat corpus frontier --limit 15                 # what to look for next, and why

labrat corpus round open --mode expand --bucket market_microstructure --limit 15
# read corpus/rounds/round-001/request.md, do the research,
# write corpus/rounds/round-001/findings.yaml
labrat corpus round close

labrat corpus report                              # REPORT.md
labrat corpus manifest                            # the rights-gated build list
```

Three round modes:

- **expand** — work the frontier: identify the targets, and record what *they* cite so the frontier regenerates.
- **verify** — resolve rights, working the queue ranked by upside. Confirming that a trade-press textbook is copyrighted buys nothing; confirming a course licence can unlock hundreds of pages, so the queue weights them 0.15 and 1.0 respectively.
- **acquire** — record where a legitimately obtained copy of an already-eligible work lives.

### Frontier ranking

```
score = 2.0·log(1 + support) + 0.6·(mean citing priority / 5) + 1.5·(bucket page gap) + 0.5·(cross-bucket bridge)
```

Co-citation support dominates, the bucket's remaining page gap steers effort toward what is thin, and a work referenced from more than one bucket gets a bonus — those are the connectors worth having.

### Closing frontier targets

A finding closes a frontier target either by declaring it:

```yaml
resolves: ["Ho & Stoll — Optimal dealer pricing under transactions and return uncertainty"]
```

or by matching heuristically (title overlap plus an author signal). Every ref that used the free-text label is rewritten to point at the new entry, so the frontier shrinks as the network grows.

### Saturation is the stopping rule

A bucket is `saturated` when two consecutive **expansion** rounds add nothing new *and* its frontier is empty. Verification rounds never count — failing to clear rights says nothing about whether material remains. "Exhaustive" means every bucket saturated, not a fixed number of rounds.

`rediscovery_rate` — the share of a round's findings that were already mapped — is the early warning: it climbs before a bucket goes dry.

## Sourcing: resolving, verifying and acquiring

`scripts/resolve.py` is the deterministic resolver. It fills in identifiers from public bibliographic infrastructure, reads licences off the pages that grant them, and downloads what genuinely clears.

```bash
python scripts/resolve.py identify --limit 400        # title -> DOI, against Crossref
python scripts/resolve.py licence  --limit 60         # DOI -> licence, from the landing page
python scripts/resolve.py fetch --dest corpus/sources # only what the manifest already admits
```

Three rules do the work:

- **Refuse rather than guess.** A candidate must clear a title-similarity threshold, a one-year window and an author check, or it goes to quarantine with its candidates listed. A truncated registry title is rescued by a containment path that requires an exact year *and* a matching author, so a one-word record cannot capture an unrelated work. On the shipped corpus that resolves 56 of 305 and quarantines the rest, most of them books with several editions where the right answer is genuinely ambiguous.
- **An API error is not a negative result.** A rate limit cached as "no such work" is how a resolver quietly stops working while still printing a number. Errors are surfaced separately and never cached. This was not hypothetical: the first run silently recorded 216 quota failures as "not found".
- **The aggregator's licence field is a lead, not a grant.** Verification fetches the landing page and requires the licence to be stated there, recording the operative text. A page that loads and grants nothing is recorded as `all_rights_reserved, confirmed` — a result that retires the entry from the verify queue. A page that will not load is recorded as unresolved, because absence of evidence is not evidence.

### Study copies are a different question from corpus ingest

```bash
python scripts/resolve.py study --dest corpus/study
```

`fetch` builds the corpus and is gated by the manifest, because putting a text into a corpus is a distribution and a derivative use. `study` downloads reading copies of full texts the publisher already serves for free, and is gated by nothing except availability. The corpus model already drew this line: `reference_only` means *read it, learn from it, write our own explanations, do not copy it in*. A study copy is the "read it" half.

Nothing in `study` changes a rights tag or a use class. An entry downloaded as a study copy still holds `all_rights_reserved` or `author_hosted_free`, still reads `reference_only`, and still cannot enter the manifest. The only field that moves is `acquisition`, which records where the reading copy sits and where it came from. Keeping those two ledgers separate is the point: a folder full of PDFs is not a licence, and an engine that conflated them would quietly launder one into the other.

Locations come from Unpaywall by DOI, and from arXiv directly where a preprint exists. arXiv's Atom API refuses this environment outright — persistent 429 on every query, including at the documented three-second delay — so the resolver reads the public search results page instead, which carries the identifier, full title, author list and original announcement year. It parses the *originally announced* date rather than the submission date, because a v3 revision would place a 2015 paper in 2024 and fail the year check for entirely the wrong reason.

### What actually cleared

| Class | Outcome |
|---|---|
| MIT OpenCourseWare | **CC BY-NC-SA, confirmed** on both the terms page and each course page. 5 courses, 109 PDFs, 37 MB downloaded |
| Publisher landing pages that loaded | 20 read in full, none granting an open licence → `all_rights_reserved, confirmed` |
| Publisher pages behind a bot wall | 20 returned 403 → unresolved, not assumed either way |
| arXiv | The default grant is a licence **to arXiv** to distribute, not a licence to us. Read on the page and mapped to `author_hosted_free` → `reference_only`. Readable, downloadable as a study copy, not ingestable |
| Course notes pages | Stanford EE364a and Berkeley CS285 serve slides publicly with no licence stated → `author_hosted_free`, harvested as study copies |

The arXiv row is the one worth internalizing. arXiv is the largest pool of freely readable material the corpus touches, and freely readable is not licensed. A paper there is ingestable only if its author chose a CC licence, which has to be checked per paper. It is still perfectly readable, which is what `study` is for.

Locating those copies did not go smoothly, and the failures are recorded because they are the interesting part. OpenAlex became a metered API mid-run and the first version cached its quota errors as "no such work". arXiv's Atom API refuses this environment outright, so the resolver reads the public search page instead — and then arXiv throttled that too, partway through a sweep, at which point a circuit breaker abandons the index after six consecutive failures and says so in the output. Grinding through two hundred more titles at eighty seconds each would have turned a block into two hundred silent misses.

**Current haul: 295 PDFs, 176 MB, across 34 entries** — 5 MIT OpenCourseWare courses under CC BY-NC-SA (the only openly licensed material, and the only material `fetch` will take), plus study copies from publisher sites, institutional repositories and course pages. Every one of those study copies keeps the rights tag it arrived with.

## Running it as a labrat lab

```bash
labrat new my_corpus --profile=quant-finance-corpus
cd my_corpus
python scripts/operator_helper.py doctor
python scripts/bootstrap.py
```

A candidate is a **scouting policy**, not a model: which bucket, which mode, how deep, through which discovery channel. The families in `branches.yaml` are the channels — `citation_chase`, `syllabus_mining`, `rights_first`, `venue_documentation`, `bridge_hunting`, `practitioner_channel` — and they compete for credits.

Each candidate runs in two phases:

1. First run opens the round, writes the brief, and returns `failure_class: awaiting_findings` (not scored).
2. A scout fills `findings.yaml`; re-running the same candidate merges, closes and scores it.

The runtime never invents bibliographic facts. It decides what to look for and keeps the accounting honest when the answers come back.

Metrics:

| Metric | Measures |
|---|---|
| `search_eval` | productivity: new entries, frontier targets closed, entries improved |
| `selection_eval` | legally usable value added: manifest-eligible pages gained, confirmation rate |
| `final_eval` | share of the touched buckets' page targets now manifest-eligible |
| `bridge_discovery` *(decisive)* | cross-bucket connections created per new entry |
| `rights_clearance` *(decisive)* | share of works touched that ended confirmed with evidence |

Both decisive challenges are things volume cannot buy, which is the point: a family that only piles up more of the same literature can win `search_eval` and still lose the lab.

Operator surfaces ship for both interfaces: `/corpus-round` and `/corpus-status` for Claude Code, the `corpus-scout` skill for Codex, and the shared contract in `agent_prompts/shared/corpus_round.md`.

## Rights policy in practice

The engine enforces the mechanics; these are the working rules behind them.

- **Confirmed means someone read it.** A rights tag asserted from memory is worthless, and the merge step rejects `confidence: confirmed` without evidence.
- **A silent licence page is a result.** Record `all_rights_reserved` at `confidence: confirmed`, note what you checked, and the entry leaves the verify queue for good.
- **Free to read is not licensed.** Author-hosted PDFs, preprints and course pages grant reading unless they say otherwise.
- **A purchase is not a clearance.** Buying a book or a certification curriculum grants personal reading, usually explicitly non-transferable.
- **Confidential material is excluded, and recorded as excluded** — once, so the decision is not re-litigated every round.
- **Ask.** A narrow, specific permission request to a course-notes author or an out-of-print rights holder is cheap and sometimes works. Record the reply as `rights.grant` with the message as evidence.

The highest-yield clearance channels, in order: openly licensed courseware, author-hosted books with a stated permission, government and regulatory text, venue documentation repositories with a real LICENSE file, direct permission requests, and material you write yourself.

## Command reference

| Command | Does |
|---|---|
| `labrat corpus init` | create the workspace |
| `labrat corpus validate` | check entries against the vocabularies; exits non-zero on error |
| `labrat corpus status [--json]` | coverage, rights posture, network shape, saturation |
| `labrat corpus frontier [--bucket B] [--limit N]` | ranked next targets with score components |
| `labrat corpus reading [--bucket B] [--include-unmapped]` | chapter-level reading queue across decomposed sources |
| `labrat corpus round open --mode M [--bucket B] [--limit N]` | open a round and write the brief |
| `labrat corpus round close [--round N] [--findings PATH]` | merge findings, score the round, append the log |
| `labrat corpus round list` | closed and open rounds |
| `labrat corpus rights [--verify-queue] [--bucket B]` | rights report, or the upside-ranked verification queue |
| `labrat corpus manifest [--out PATH]` | the rights-gated build manifest, with reasons for every hold |
| `labrat corpus graph [--out PATH]` | nodes, edges, unresolved frontier, components |
| `labrat corpus report [--out PATH]` | the markdown report |
| `labrat corpus vocab [--json]` | form and rights vocabularies with use-class mapping |
| `labrat corpus self-test` | rights gates, dedupe, graph, merge and unit logic on adversarial input |

All commands take `--lab-dir` (the corpus is `<lab>/corpus`) or `--corpus-dir` to point somewhere else. Inside a scaffolded lab, `python scripts/corpus.py <command>` is the same tool.

## Adapting it to another domain

1. Write `corpus/taxonomy.yaml`: buckets, page targets, why each matters, and — worth the effort — a `deprioritized` list so cheap low-density material cannot inflate a round.
2. Seed `corpus/bibliography.yaml` with the works you already know, each carrying `refs`. The seed's job is to give the frontier something to grow from; twenty well-referenced entries beat two hundred isolated ones.
3. Tag seed rights as `inferred`, never `confirmed`. Nothing should be manifest-eligible before someone has read a licence.
4. Run `labrat corpus validate`, then start opening rounds.
