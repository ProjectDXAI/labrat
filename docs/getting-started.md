# Getting Started with labrat vNext

## 1. Evaluate the framework quickly

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/nlp-sentiment/requirements.txt
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

The example includes:

- a real local dataset
- a runtime-backed `branches.yaml`
- `evaluation.yaml` and `runtime.yaml`
- a working external evaluator
- decisive held-out challenge tests beyond the search metric
- audit and frame-break fixtures

## 2. Start a real lab

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

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
