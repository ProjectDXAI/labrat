# Changelog

## 0.2.2 - 2026-04-23

- Updated Codex guidance for GPT-5.5 availability in Codex, without tying the lab runtime to API model strings.
- Clarified Codex `AGENTS.md` layering so lab-local instructions govern runtime operation inside nested labs.
- Expanded the `labrat-operator` skill around Codex discovery, Plan mode, review, subagents, MCP, and verification.

## 0.2.1 - 2026-04-23

- Added frontier-model operating guidance for Codex and Claude Code lab supervision.
- Added an optional repo-scoped `labrat-operator` Codex skill and included it in generated labs.
- Tightened runner docs around completion criteria, verification, reasoning-effort choice, and trusted-source research.
- Kept model-specific docs conservative: the lab runtime uses host-selected model settings instead of hardcoded API model IDs.

## 0.2.0 - 2026-04-21

- Added a first-class installable `labrat` CLI, including `labrat doctor`, JSON status outputs, and `labrat --version`.
- Added repo-root and lab-root operator guidance so Codex and Claude Code are both supported as primary orchestration interfaces.
- Added `AGENTS.md` to scaffolded labs, synced the canonical example lab with agent guidance files, and clarified runner docs in the README and supporting docs.
- Switched runtime-owned file writes to atomic helpers for safer local state updates.
