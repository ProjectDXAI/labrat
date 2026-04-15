# labrat program

This is the repo-level entrypoint for Claude Code or Codex.

Do not start by reading every document. Pick the shortest path that matches the user's intent.

## Path 1: Evaluate The Repo Quickly

Use this when the user wants to understand `labrat`, see it work, or get a fast reference run.

### Your job

1. Read `README.md` for repo shape.
2. Use `examples/nlp-sentiment` as the default evaluation path.
3. Keep the path thin:
   - install example requirements
   - bootstrap the example lab
   - start the dashboard
   - use the example's local prompt files or helper to run the next step
4. Only move into the deeper framework docs when the user wants to build or change the framework.

### Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/nlp-sentiment/requirements.txt
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

The Codex version is the same except for `--runner codex`.

## Path 2: Create A Real Lab

Use this when the user wants a new research lab, not just a demo.

### Your job

1. Scaffold a new lab with `scripts/new_lab.py`.
2. Treat Phase 0 deep research as mandatory:
   - design the tree from evidence
   - finalize `branches.yaml`
   - finalize `dead_ends.md`
   - write `research_brief.md`
   - write `research_sources.md`
   - define the search ladder:
     - cheap probes
     - normal exploitation
     - implementation audit
     - formulation change
3. Confirm readiness with the helper.
4. Bootstrap only after Phase 0 is complete.
5. Start autonomous cycle execution from the lab-local prompts.

### Commands

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

The Codex flow is the same except for `--runner codex`.

## What To Read Next

- `docs/getting-started.md`: starter flow
- `docs/runners.md`: Claude Code and Codex specifics
- `docs/DEEP_RESEARCH.md`: the longer research-program playbook
- `docs/ARCHITECTURE.md`: framework internals

## Defaults

- Default to the flagship example before a blank scaffold when the user is still orienting.
- Default to Claude Code and Codex as the supported agent surfaces.
- Default to deep research for every new lab.
- Default to the lab-local prompt files and helper scripts instead of improvising the workflow from memory.
- Default to cheap probes and implementation audits before a full frame break when a frontier is suspicious but not truly dead.
