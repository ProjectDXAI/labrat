# SST-5 Example Research Scout

Use the standard scout protocol, but keep the example constraints front and center:

- CPU only
- fast experiments
- no heavyweight neural fine-tuning in the runnable branch proposals
- favor techniques that can be expressed as sparse features, light ensembles, class balancing, or cheap representation changes

Read:

1. the latest `scout_request.json`
2. `dead_ends.md`
3. `research_sources.md`
4. the branch-specific history in `state/experiment_log.jsonl`

Write:

- proposals to `experiments/{branch}/scout_proposals/`
- a summary next to the proposal file
- a short memo in `logs/scouts/`

The best proposals for this example are usually:

- stronger sparse feature formulations
- better imbalance handling
- CPU-friendly embedding hybrids
- cheap ensemble or calibration variants
