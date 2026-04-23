# labrat program

This is the repo-level entrypoint for Codex or Claude Code.

The repository root is not a runnable lab. Use the root `AGENTS.md` or `CLAUDE.md` for repo maintenance, and use a lab directory when you want to operate the runtime itself.

## Path 1: Evaluate the repo quickly

Use the flagship example.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[nlp-sentiment]'
labrat doctor --lab-dir examples/nlp-sentiment/research_lab
labrat bootstrap --lab-dir examples/nlp-sentiment/research_lab
python -m http.server 8787 --directory examples/nlp-sentiment/research_lab
labrat status --lab-dir examples/nlp-sentiment/research_lab
labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto
```

Codex uses the same flow with `--runner codex`.

## Path 2: Start from a profile

Use this when the user arrives with a concrete research workload that matches an existing profile.

```bash
labrat new my_search --profile=transformer-arch
cd my_search
python -m pip install -r requirements.txt
python scripts/operator_helper.py doctor
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Profiles ship with filled Phase 0 files, a working `run_experiment.py`, `AGENTS.md`, `CLAUDE.md`, `.claude/commands/`, and `agent_prompts/`. `transformer-arch` is the first profile. See [docs/PROFILES.md](docs/PROFILES.md) for the full list and contract.

## Path 3: Create a real lab from scratch

Use this when no profile fits and the user wants a new runtime-backed research program.

1. scaffold a new lab with `labrat new`
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
labrat new my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Use `--runner codex` if you are operating from Codex instead of Claude Code.

## Interface contract

Every generated lab carries the operator instructions in version control:

- `AGENTS.md` for Codex
- `.agents/skills/labrat-operator/SKILL.md` for Codex's optional repeatable workflow
- `CLAUDE.md` and `.claude/commands/` for Claude Code
- `agent_prompts/` for the shared phase prompts

There is no hidden skill file. The goal is that a new user can open the lab in either interface and start from the files already present in the lab root.

For current frontier-model operating guidance, see [docs/MODEL_GUIDANCE.md](docs/MODEL_GUIDANCE.md).

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
