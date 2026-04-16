# labrat program

This is the repo-level entrypoint for Claude Code or Codex.

## Path 1: Evaluate the repo quickly

Use the flagship example.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/nlp-sentiment/requirements.txt
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Codex uses the same flow with `--runner codex`.

## Path 2: Create a real lab

Use this when the user wants a new runtime-backed research program.

1. scaffold a new lab with `scripts/new_lab.py`
2. finish Phase 0:
   - `branches.yaml`
   - `dead_ends.md`
   - `research_brief.md`
   - `research_sources.md`
   - `evaluation.yaml`
   - `runtime.yaml`
3. confirm readiness
4. bootstrap the runtime
5. supervise the worker pool through the helper prompts

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

## Defaults

- The runtime is async and steady-state.
- `evaluator.py` is authoritative for scores.
- `search_eval` and `selection_eval` are separate by default.
- `prediction_tests` define decisive held-out challenges that are not the same as the local hill-climb metric.
- Cheap probes and audits come before frame break.
- The static dashboard is the canonical UI.

## Lineage

If you want the shortest explanation of where this repo is coming from:

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) for the compact autonomous experiment loop
- [AIRA_2](https://arxiv.org/abs/2603.26499) for population-level search and evaluation discipline
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018) for artifact-mediated coordination and workspace continuity
