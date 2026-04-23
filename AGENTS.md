# labrat repo

This is the repository root, not a runnable lab directory.

Use this file when working on `labrat` itself from Codex.

If Codex is opened inside a nested lab that has its own `AGENTS.md`, follow the lab-local file for runtime operation. This root file governs repo maintenance, scaffold consistency, releases, and docs.

## Source Of Truth

- Product/setup docs: `README.md`, `program.md`, `docs/getting-started.md`, `docs/runners.md`, `docs/MODEL_GUIDANCE.md`
- Scaffolded lab UX: `templates/AGENTS.md`, `templates/CLAUDE.md`, `templates/.agents/skills/`, `templates/.claude/commands/`, `templates/agent_prompts/`
- Canonical example lab: `examples/nlp-sentiment/research_lab/`
- Packaging/versioning: `pyproject.toml`, `labrat/__init__.py`, `CHANGELOG.md`

## Interface Rules

- Keep Codex and Claude Code first-class. If a lab gets one operator surface, add the matching one for the other interface.
- Generated labs should ship `AGENTS.md`, `.agents/skills/`, `CLAUDE.md`, `.claude/commands/`, and `agent_prompts/`.
- Keep `AGENTS.md` short enough to stay durable. Put longer repeatable Codex workflows in `.agents/skills/`.
- Do not require a hidden local setup for basic operation. The runnable contract should live in the repo.
- When operator guidance changes, keep templates, the canonical example lab, and the docs in sync.
- Prefer `labrat ...` examples in docs when working from the repo root. Keep the copied `scripts/*.py` flow valid inside labs.

## Frontier Model Rules

- Use `docs/MODEL_GUIDANCE.md` for model and prompt-process updates.
- GPT-5.5 is a Codex host selection, not a lab runtime constant. Do not hardcode API model IDs into `labrat` for Codex usage.
- Prefer explicit completion and verification contracts over broad encouragement.
- Reserve high reasoning effort for design, audit, frame break, profile authoring, and release work.
- Keep root `AGENTS.md` focused on repo maintenance; lab runtime details belong in lab-local `AGENTS.md` and `.agents/skills/labrat-operator/SKILL.md`.

## Checks

- `. .venv/bin/activate && labrat doctor --lab-dir examples/nlp-sentiment/research_lab`
- `. .venv/bin/activate && labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner codex --phase auto`
- `. .venv/bin/activate && labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto`
- `. .venv/bin/activate && make smoke`

## Publish Discipline

- Bump the package version in both `pyproject.toml` and `labrat/__init__.py`.
- Record user-visible changes in `CHANGELOG.md`.
- Do not leave docs describing Claude-only flows when Codex is equally supported.
