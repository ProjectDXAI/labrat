# Corpus explorer

A local reader for the corpus and the compiled knowledge store. It is a reader, not a
second source of truth: everything it shows comes from `scripts/export_web.py`, which
calls the same functions the CLI does, so a number on screen cannot drift from a number
in `knowledge.py assess`.

```bash
make web           # export the bundle, install if needed, serve on :3000
make web-data      # just re-export after a compile round
make web LAB=my_lab
```

The bundle (`web/public/corpus.json`, ~800 KB) is generated and gitignored. If the app
says it cannot load it, run `make web-data`.

## Four views

**Assessment** — the store read as a whole. The chain table is the one to look at first:
a problem is served only when one concept covering it has a bound method, a hypothesis
with a cost model, *and* a decision card. Rows with zero complete chains are tinted,
because they look healthy by every other column and cannot be acted on. Below that, the
contradiction clusters (each a question with two defensible answers), the confident cards
resting on unopened material, and the four structural-rot checks.

**Concepts** — every card with the mechanism it claims, the assumptions it needs, what
would falsify it, its competing explanations, and whether anyone opened the source it
rests on. Filter by grounded, ungrounded or contested. Contradicting cards are clickable,
so an argument can be followed both ways.

**Sources** — all 457 catalogued works. Filter by bucket, by what is held on disk, by what
has been read, or by rights that were never verified. Expanding a row shows its reading
units with their locators and the notes taken while reading them.

**Network** — the bibliography as a graph, clustered by field. This layout is the point:
a hairball hides the one thing worth seeing, which is an edge leaving its field. Clustered
into a ring, those become the pale chords across the middle, and *cross-field only* isolates
them. Size is citation degree; a white ring means we hold the full text.

## Design notes

Dark because this is a two-hour cross-referencing tool where the screen is the light
source, not because tools look good dark. One accent (amber). Every other colour carries
data: green is read or ingestable, red is a contradiction or a broken chain, amber is
unverified. System font stack, fixed rem scale, one family.

Two implementation notes worth keeping:

- The force simulation publishes positions into React state as a fresh array per frame.
  d3 mutates node objects in place, and React 19 memoises on identity, so a render driven
  by mutation is silently dropped.
- The SVG container is flex-sized and measures zero on first paint, so a `ResizeObserver`
  supplies the real dimensions and the simulation refuses to lay out until it has them.
