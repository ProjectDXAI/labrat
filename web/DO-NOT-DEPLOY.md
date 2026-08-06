# This app is local only

The explorer reads `public/corpus.json`, which is generated from the lab and contains
the full bibliography, the reading notes, and the compiled knowledge store. It is
private working material. It is not licensed for redistribution and it is not intended
for anyone but its author.

Guards in place:

- `public/corpus.json` is gitignored, so the data is never committed.
- `npm run dev` and `npm run start` bind to `127.0.0.1`, so nothing is served to the
  local network.
- There is no deployment configuration in this directory, and none should be added.

If you ever do need to put any of this somewhere public, the licence terms recorded by
`corpus.py rights` become the relevant question at that point. They are deliberately not
enforced anywhere in the reading path, because reading material you already hold is not
redistribution.
