# Dead Ends

- character-only models
  - why it failed: loses too much semantic structure on this toy corpus
  - revive only if: misspellings or noisy user text become the main failure mode

- giant vocabulary sweeps
  - why it failed: they mostly add sparse noise without moving held-out selection
  - revive only if: search/selection metrics suggest the current feature floor is still representation-bound

- calibration before the frontier matters
  - why it failed: it spends credits before the representation/classifier families have something worth stabilizing
  - revive only if: the main frontier is close and unstable
