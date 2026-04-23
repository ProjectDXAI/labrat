# Getting Started with labrat vNext

## 1. Evaluate the framework quickly

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[nlp-sentiment]'
labrat doctor --lab-dir examples/nlp-sentiment/research_lab
labrat bootstrap --lab-dir examples/nlp-sentiment/research_lab
python -m http.server 8787 --directory examples/nlp-sentiment/research_lab
labrat status --lab-dir examples/nlp-sentiment/research_lab
labrat runtime-summary --lab-dir examples/nlp-sentiment/research_lab
labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto
```

Use `--runner codex` for Codex.

The example includes:

- a real local dataset
- a runtime-backed `branches.yaml`
- `evaluation.yaml` and `runtime.yaml`
- a working external evaluator
- decisive held-out challenge tests beyond the search metric
- audit and frame-break fixtures

The example lab also ships the full operator surface:

- `AGENTS.md` for Codex
- `.agents/skills/labrat-operator/SKILL.md` for Codex's optional lab-operation workflow
- `CLAUDE.md` and `.claude/commands/` for Claude Code
- `agent_prompts/` for the shared phase prompts

No hidden skill file is required. Everything needed to operate the lab lives in the repository.

## 2. Start a real lab

```bash
labrat new my_lab
cd my_lab
labrat doctor --lab-dir .
labrat next-prompt --lab-dir . --runner claude --phase design
labrat next-prompt --lab-dir . --runner codex --phase design
labrat check-readiness --lab-dir .
labrat bootstrap --lab-dir .
python -m http.server 8787
labrat next-prompt --lab-dir . --runner claude --phase auto
```

## 3. Pick the interface

Codex:

```bash
cat AGENTS.md
python scripts/operator_helper.py doctor
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

Claude Code:

```bash
cat CLAUDE.md
python scripts/operator_helper.py doctor
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Inside a lab, the `python scripts/...` commands and the `labrat ... --lab-dir .` commands are equivalent. Prefer `labrat ...` when you are working from the repo root, and prefer `python scripts/...` when you are already inside the lab directory.

## Phase 0 checklist

Do not bootstrap until these are real:

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`
- `evaluation.yaml`
- `runtime.yaml`

`branches.yaml` is now a family graph, not a per-cycle budget sheet.

Each family must define:

- cheap probes
- mutation policy
- crossover compatibility
- decisive challenge claim
- resource class
- funding prior
- audit triggers
- frame-break triggers

`evaluation.yaml` must also define at least one held-out `prediction_tests` challenge. Families earn extra status when they win those tests, not just when they climb the local search score.

## Operating phases

The helper routes into:

- `design`
- `supervisor`
- `audit`
- `frame_break`
- `expansion`
- `checkpoint`

`auto` picks the phase from runtime state.

## Runtime commands

- `python scripts/runtime.py bootstrap-runtime`
- `python scripts/runtime.py summary`
- `python scripts/runtime.py dispatch`
- `python scripts/runtime.py lease --worker-id cpu-1`
- `python scripts/runtime.py complete --candidate-id ... --result ...`
- `python scripts/runtime.py reap`
