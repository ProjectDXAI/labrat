# SST-5 Example Tree Designer

This example already contains a completed Phase 0.

Use the generic tree-design protocol, but keep these example-specific constraints:

- dataset: SST-5 via `SetFit/sst5`
- objective: maximize macro F1
- compute: CPU only
- iteration speed: seconds per experiment
- reduced lab surface: TF-IDF + scikit-learn, with the broader production-scale ideas preserved only in the research notes

The completed Phase 0 outputs for this example are:

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`

If you re-run Phase 0 for this example, preserve the distinction between:

1. the full research tree the problem deserves
2. the smaller runnable lab that exists to demonstrate the loop honestly on a laptop
