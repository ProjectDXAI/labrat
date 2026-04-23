# Changelog

## 0.2.1 - 2026-04-23

- Added frontier-model operating guidance for Codex and Claude Code lab supervision.
- Added an optional repo-scoped `labrat-operator` Codex skill and included it in generated labs.
- Tightened runner docs around completion criteria, verification, reasoning-effort choice, and trusted-source research.
- Kept model-specific docs conservative: current public OpenAI docs identify GPT-5.4 as the latest API model, so the repo avoids hardcoding unsupported newer model IDs.

## 0.2.0 - 2026-04-21

- Added a first-class installable `labrat` CLI, including `labrat doctor`, JSON status outputs, and `labrat --version`.
- Added repo-root and lab-root operator guidance so Codex and Claude Code are both supported as primary orchestration interfaces.
- Added `AGENTS.md` to scaffolded labs, synced the canonical example lab with agent guidance files, and clarified runner docs in the README and supporting docs.
- Switched runtime-owned file writes to atomic helpers for safer local state updates.
