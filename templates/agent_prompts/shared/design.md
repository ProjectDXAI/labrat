# Phase 0: Deep Research And Tree Design

Complete Phase 0 before bootstrapping or running any experiments.

## Read first

1. `tree_designer.md`
2. `branches.yaml`
3. `constitution.md`
4. `dead_ends.md`
5. `research_brief.md`
6. `research_sources.md`

## Your job

- Survey the landscape with real external research.
- Replace every `LABRAT_PLACEHOLDER` token in the lab.
- Finalize `branches.yaml`, `dead_ends.md`, `research_brief.md`, and `research_sources.md`.
- Leave a concrete branch-to-source map in `research_sources.md`.
- Define a cheap screening plan if the domain allows one.
- Include at least one cheap orthogonal probe branch and one formulation-change branch unless you can defend omitting them.
- Include at least one formulation-change branch, or explain explicitly why the initial tree does not need one.
- Write down the baseline bottleneck model, the implied lower bound, and the contradiction with any stronger external target.
- Stop after Phase 0. Do not bootstrap. Do not run experiments.

## Completion standard

Phase 0 is complete only when:

- the mission, baseline, and branch search spaces are concrete
- the brief is written in plain language
- the sources file explains where each branch came from
- the tree includes a search ladder: cheap probes, normal exploitation, implementation audit, formulation change
- the brief and sources file record the frontier gap and what would force a frame break later
- known dead ends are documented with reasons and exceptions
