# Getting Started

`labrat` has two supported starts:

1. evaluate the repo quickly
2. create a real lab

If you are new to the repo, run the example first. If you are starting a real lab, Phase 0 deep research comes before bootstrap.

## Path A: Evaluate The Repo Quickly

This is the fastest way to understand the repo and see the loop shape.

### Install the example dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/nlp-sentiment/requirements.txt
```

### Bootstrap and serve the example

```bash
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
```

Open `http://localhost:8787/dashboard.html`.

### Point your agent at the example

Use the lab-local helper instead of guessing the next prompt.

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Or:

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

If you want the React dashboard:

```bash
cd dashboard-app
npm install
npm run dev
```

## Path B: Create A Real Lab

Use this when you want a new research program, not a toy first cycle.

### Scaffold a new lab

From the repo root:

```bash
python scripts/new_lab.py my_lab
cd my_lab
```

This creates:

- local prompt assets:
  - `tree_designer.md`
  - `research_scout.md`
  - `expansion_scout.md`
  - `consolidation_agent.md`
  - `implementation_audit.md`
  - `frame_break.md`
  - `agent_prompts/`
- Phase 0 artifacts:
  - `branches.yaml`
  - `dead_ends.md`
  - `research_brief.md`
  - `research_sources.md`
- support scripts:
  - `scripts/bootstrap.py`
  - `scripts/operator_helper.py`
  - `scripts/research_scout.py`
  - `scripts/judge.py`
  - `scripts/run_experiment.py`

### Complete Phase 0

Use one of these:

```bash
python scripts/operator_helper.py next-prompt --runner claude --phase design
```

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase design
```

Phase 0 is complete only when:

- every `LABRAT_PLACEHOLDER` token is gone
- `branches.yaml` is concrete
- `dead_ends.md` is source-backed
- `research_brief.md` is written
- `research_sources.md` maps branches to sources
- the lab has a search ladder:
  - cheap probes
  - normal exploitation
  - implementation audit
  - formulation change
- the cheap screening or proxy stage is explicit when the domain allows one

### Confirm readiness and bootstrap

```bash
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
```

`bootstrap.py` will fail by default if Phase 0 is incomplete. Use `--allow-incomplete` only for maintainers or partial scaffolds.

### Start autonomous operation

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Or:

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

## What The Framework Assumes

The agent is the orchestrator. Python does not run the research loop by itself.

Python handles:

- readiness checks
- state summarization
- scout request generation
- scoring and bookkeeping utilities

The agent handles:

- Phase 0 deep research
- cheap probe and screening decisions
- branch-local exploitation
- implementation audits for suspicious families
- mutation decisions
- scouting and expansion
- synthesis and handoff
