# Runners: Claude Code and Codex

Both runners use the same runtime contract, state files, and prompts. The difference is the interface surface around that runtime.

## Expected files

Every runnable lab should ship:

- `AGENTS.md` for Codex
- `.agents/skills/labrat-operator/SKILL.md` for Codex's optional repeatable workflow
- `CLAUDE.md` for Claude Code
- `.claude/commands/` for Claude Code slash commands
- `agent_prompts/` for the shared phase prompts

There is no hidden required skill file. A user should be able to clone the repo, open either interface, and operate from the files already committed to the lab.

## Claude Code

Typical loop:

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Claude Code should act as:

- async supervisor
- audit operator
- frame-break / expansion operator
- bounded worker when you explicitly assign a probe / mutation / crossover task

Claude Code should read `CLAUDE.md` first. If the user wants slash commands, `.claude/commands/next.md` and the other command files are the canonical shortcuts.

## Codex

The Codex flow is the same:

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

Codex should read `AGENTS.md` first. `AGENTS.md` is the stable operator brief, `.agents/skills/labrat-operator/SKILL.md` is the optional repeatable workflow, and `agent_prompts/codex.md` is the runner-specific supplement.

## Shared rules

- workers do not self-promote
- `result.json` is not the final verdict
- `evaluator.py` is authoritative
- runtime state is the source of truth
- use audit before killing suspicious families
- use frame break only after cheap probes and audit are no longer the right move
- use higher reasoning effort for design, audit, frame break, profile authoring, and release work
- browse external sources only when the answer depends on current facts or user-requested references

## Repo root vs. lab root

- From the repo root, prefer `labrat ... --lab-dir <path>`.
- From inside a lab, prefer `python scripts/...` or Claude Code slash commands.
- Keep docs and examples showing both runner flags so Codex and Claude Code remain first-class.
- See `docs/MODEL_GUIDANCE.md` before changing model or prompting guidance.
