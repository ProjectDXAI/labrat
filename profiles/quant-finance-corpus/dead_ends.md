# Known dead ends — quantitative finance corpus

Do not spend rounds here unless a cheap probe convincingly contradicts the entry.

## Low-density literature

The categories in `corpus/taxonomy.yaml` under `deprioritized` are excluded on signal density, not on taste: technical analysis, retail trading books, trading psychology, retail options books, candlestick books, popular momentum investing, and "AI for finance" trade books.

These are cheap to find and cheap to acquire, which makes them a trap for a search that rewards volume. If a round returns them, the channel is broken, not productive. Revive only with evidence that a specific work carries something the tier 1 buckets do not.

## Treating free-to-read as licensed

A PDF on an author's page, a course site, or a preprint server grants reading. It does not grant corpus construction. `author_hosted_free` maps to `reference_only` on purpose, and the engine will not put it in the manifest even at `confidence: confirmed`.

The only escapes are a stated licence (`cc_*`, `open_license_other`), a public-domain determination, or an explicit `rights.grant` with the permission recorded as evidence.

## Confidential or leaked material

Prop desk manuals, internal training decks, and NDA-bound material circulating on file-sharing sites are `proprietary_confidential` → `excluded`. Do not acquire, do not cite as a source, do not ingest, regardless of how dense the content is.

One placeholder entry (`leaked-prop-desk-manual-placeholder`) is kept in the bibliography with `status: rejected` precisely so this decision is recorded once instead of being re-litigated every round.

## Purchase as a clearance strategy

Buying a textbook, a certification curriculum, or a paid course grants a personal reading licence, usually explicitly non-transferable. It does not clear the work for corpus construction. Purchases are worth making for reading; they are not a route to `manifest_eligible`, and a round that reports otherwise is misreporting.

## Page-count chasing in `practitioner_training`

Certification curricula are enormous and low density, and their licences are the most restrictive in the corpus. The bucket's page target is deliberately small. Adding three thousand pages of curriculum that can never be ingested moves no metric that matters.

## Verification rounds on settled commercial works

Confirming that a commercial textbook is `all_rights_reserved` buys nothing — it was already `reference_only`. The verify queue weights these at 0.15 for that reason. If a `rights_first` round spends its budget on trade-press books, it will score near zero on `rights_clearance` and deserve to.

## Re-running expansion into a saturated bucket

Two consecutive expansion rounds with no new entries and an empty frontier means the bucket is done at the current depth. Re-running the same channel produces rediscovery, not coverage. Either switch channel (a bucket saturated for `citation_chase` is often still open for `syllabus_mining`), or move on.
