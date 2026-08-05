# Research sources

The seed bibliography lives in `corpus/bibliography.yaml` (173 works at seed) and the bucket structure, page targets and deprioritized categories in `corpus/taxonomy.yaml`. This file records where the seed came from and which channels rounds should work.

## Seed provenance

The seed is a prior, not a finding. It was assembled from working knowledge of these literatures, so:

- **Bibliographic metadata is unverified.** Titles, authors and years are believed correct; page counts are order-of-magnitude estimates; ISBNs, DOIs and URLs are deliberately left null rather than guessed.
- **Every rights tag is `inferred` or `unknown`, with no evidence.** Nothing in the seed is manifest-eligible. That is the point: a rights tag only becomes load-bearing when a verify round attaches a licence URL and a check date.

Treat a seed entry as "this work exists and probably matters", nothing more.

## Discovery channels

Each family works one channel, so a round measures the channel rather than the scout's mood.

| Channel | Where to look | What it is good for |
|---|---|---|
| `citation_chase` | Reference lists and co-citation of already-mapped works | Finding what a literature considers load-bearing |
| `syllabus_mining` | Graduate course pages, reading lists, lecture notes, problem sets | Openly licensed material; expert ordering of a field |
| `rights_first` | Licence pages, publisher permissions, docs repositories, rights-holder contact | Turning `inferred` into `confirmed`; unlocking the manifest |
| `venue_documentation` | Exchange technical libraries, protocol standards bodies, venue docs repos | The literal rules of the venues we trade |
| `regulatory_text` | Regulator rule text, concept releases, market structure reports | Dense, and the one place unrestricted status is common |
| `bridge_hunting` | Works cited across two buckets; applications papers | Transferable abstractions, not more of the same |
| `practitioner_channel` | Training programmes with a commercial licence path | Rare licensable heuristic material |

## Rights channels worth trying explicitly

Ranked by expected yield per unit of effort:

1. **Openly licensed courseware.** MIT OpenCourseWare and similar carry an explicit licence. Confirm it on the specific course page — defaults vary and change.
2. **Author-hosted books with a stated permission.** Several standard texts are distributed free by their authors under an arrangement with the publisher. The arrangement's wording decides whether it is `ingest_*` or `reference_only`; read it, do not assume.
3. **Government and regulatory text.** Often outside copyright, jurisdiction-dependent. Confirm per document.
4. **Venue documentation repositories.** Rendered docs sites usually carry restrictive terms; the underlying public repository sometimes carries a real open licence. Check the repository.
5. **Direct permission requests.** For a course-notes author or an out-of-print rights holder, a specific, narrow request is cheap to send and occasionally works. Record the reply as `rights.grant` with the message as evidence.
6. **Purchased licences.** A purchase grants reading. Corpus construction needs a separate grant; record it as `rights.grant` or it does not count.

## Our own material

`notes_own` is a first-class form. Summaries, derivations and explanations we write ourselves from legally obtained references are `owned_by_us` and manifest-eligible without further clearance. For high-value `reference_only` works, generating our own explanation is the compliant route to the same knowledge, and it should be catalogued as an entry that `builds_on` the source.

## What the seed is missing

Known gaps, in rough priority order — the frontier will surface others:

- Non-US venue documentation beyond the few placeholders (Asian venues in particular).
- Practitioner conference proceedings and archived trading newsletters.
- Older monographs from the 1980s-2000s where rights may have lapsed or reverted; `wald-1947-sequential-analysis` is the template case worth checking.
- Theses, which are frequently openly licensed and rarely catalogued.
- Non-English literature, especially French and Russian probability and control.
