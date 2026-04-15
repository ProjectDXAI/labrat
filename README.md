# labrat

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)

Multi-branch autoresearch with funding as the control loop. `labrat` helps an agent explore competing research branches, reallocate budget to what works, and leave behind a state trail you can audit.

![labrat dashboard](docs/dash-sample.png)

`labrat` is the broad version of the idea behind `autoresearch`.

- `autoresearch` is one research thread against one fixed target.
- `labrat` is a research program with competing branches, shared budget, and an explicit exploration/exploitation loop.

The repo is built first for **Claude Code** and **Codex**.

## Why labrat

- **Multi-branch search**: run several lines of attack instead of one long thread.
- **Funding as control loop**: branches earn future compute from results, not vibes.
- **Agent-native workflow**: markdown prompts, YAML search spaces, JSON state, local scripts.
- **Readable state**: budgets, beliefs, champions, scouts, and handoffs are plain files.

## Two ways to start

### 1. Evaluate the repo quickly

Run the flagship example if you want to understand the framework before you build on it.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/nlp-sentiment/requirements.txt
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Use `--runner codex` for Codex.

### 2. Create a real lab

For a new lab, the default path is **deep research first**, not “run one cycle and hope.”

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

That flow is:

1. scaffold the lab
2. survey the landscape
3. define the search ladder:
   - cheap probes
   - normal exploitation
   - implementation audit
   - formulation change
4. finalize `branches.yaml`, `dead_ends.md`, `research_brief.md`, and `research_sources.md`
5. bootstrap
6. start autonomous cycles

## How it differs from autoresearch

| | `autoresearch` | `labrat` |
| --- | --- | --- |
| Search unit | one line of attack | multiple competing branches |
| Control loop | keep or revert | reallocate budget across branches |
| Operator surface | one research thread | tree design, branch loop, scouts, expansion |
| State | lightweight history | branch beliefs, budgets, champions, memos |
| Best fit | one tight optimization problem | broader research programs with several plausible axes |

The design goal is still simplicity. The difference is where the simplicity lives:

- `autoresearch` keeps the code surface tiny.
- `labrat` keeps the **operator workflow** coherent while exposing a broader search model.

## Deep-research-first scaffold

A new lab now generates:

- Phase 0 prompt assets:
  - `tree_designer.md`
  - `research_scout.md`
  - `expansion_scout.md`
  - `consolidation_agent.md`
  - `implementation_audit.md`
  - `frame_break.md`
  - `agent_prompts/`
- Phase 0 outputs:
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

`bootstrap.py` now enforces the Phase 0 gate by default. If the scaffold still contains `LABRAT_PLACEHOLDER` values or the brief/source files are incomplete, bootstrap fails with a clear message.

Phase 0 should not just list branches. It should also define how the lab escapes shallow search:

- what the cheap screening or proxy stage is
- which orthogonal probes should be tried before a full frame break
- when a suspicious family should go to implementation audit
- what contradiction would force a formulation-change branch

## Funding loop

The core idea is simple:

![funding loop](docs/funding-loop.svg)

1. start with a baseline and a few candidate branches
2. spend one credit per experiment
3. score the results mechanically
4. refill productive branches and let weak ones run out of budget
5. use cheap probes and implementation audits before declaring a family dead
6. use scouts and expansion when the frontier flattens for real
7. repeat until the tree is genuinely mapped

The novel part is the funding loop. The deep-research-first scaffold exists to keep that loop honest, and the probe/audit/frame-break ladder exists to keep it from converging too early on the wrong story.

## Dashboard

`labrat` ships with two dashboard surfaces:

- `templates/dashboard.html` for the zero-dependency path
- `dashboard-app/` for the cleaner React view

The static dashboard is the baseline. The React app is the polished monitoring surface.

## Example and origin

### Flagship example

`examples/nlp-sentiment` is the first-run example.

- CPU only
- fast to reproduce on a laptop
- includes a completed Phase 0 trail and a runnable reduced lab
- now acts as the reference lab for the helper-driven workflow

### Real origin

The framework was pressure-tested in real iterative research programs before this repo refresh.

- repeated branch competition forced the allocator, scoring, and dead-end tracking to stay honest
- that history is why `labrat` is opinionated about budgets, handoffs, and readable state

Those validation runs informed the framework, but they are not the onboarding path.

## Repo map

- `program.md`: repo-level agent entrypoint
- `docs/getting-started.md`: starter flow
- `docs/runners.md`: Claude Code and Codex usage
- `docs/DEEP_RESEARCH.md`: longer research-program playbook
- `templates/`: scaffold source files
- `scripts/`: bootstrap, helper, scout, judge, and scaffold utilities
- `examples/nlp-sentiment`: flagship example

## Constraints

`labrat` is not a hosted platform. No database. No control plane. No mandatory SDK.

The loop is built from:

- markdown instructions
- YAML branch definitions
- JSON state files
- Python support scripts
- an agent that can read, run commands, and write files

That keeps the repo easy to fork, easy to audit, and easy to bend to a specific domain.
