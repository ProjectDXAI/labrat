# labrat repo

This is the repository root, not a runnable lab directory.

Use this file when working on `labrat` itself from Codex.

## Source Of Truth

- Product/setup docs: `README.md`, `program.md`, `docs/getting-started.md`, `docs/runners.md`
- Scaffolded lab UX: `templates/AGENTS.md`, `templates/CLAUDE.md`, `templates/.claude/commands/`, `templates/agent_prompts/`
- Canonical example lab: `examples/nlp-sentiment/research_lab/`
- Packaging/versioning: `pyproject.toml`, `labrat/__init__.py`, `CHANGELOG.md`

## Interface Rules

- Keep Codex and Claude Code first-class. If a lab gets one operator surface, add the matching one for the other interface.
- Generated labs should ship `AGENTS.md`, `CLAUDE.md`, `.claude/commands/`, and `agent_prompts/`.
- Do not require a separate `SKILLS.md` or hidden local setup for basic operation. The runnable contract should live in the repo.
- When operator guidance changes, keep templates, the canonical example lab, and the docs in sync.
- Prefer `labrat ...` examples in docs when working from the repo root. Keep the copied `scripts/*.py` flow valid inside labs.

## Checks

- `. .venv/bin/activate && labrat doctor --lab-dir examples/nlp-sentiment/research_lab`
- `. .venv/bin/activate && labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner codex --phase auto`
- `. .venv/bin/activate && labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto`
- `. .venv/bin/activate && make smoke`

## Publish Discipline

- Bump the package version in both `pyproject.toml` and `labrat/__init__.py`.
- Record user-visible changes in `CHANGELOG.md`.
- Do not leave docs describing Claude-only flows when Codex is equally supported.
