# Agent Prompts

Use the helper instead of guessing the next step.

1. Read `AGENTS.md` if you are in Codex, or `CLAUDE.md` if you are in Claude Code.
2. Run `python scripts/operator_helper.py doctor`.
3. Run `python scripts/operator_helper.py status`.
4. Run `python scripts/operator_helper.py runtime-summary`.
5. Run `python scripts/operator_helper.py next-prompt --runner claude --phase auto`
   or
   `python scripts/operator_helper.py next-prompt --runner codex --phase auto`

Supported phases:

- `design`
- `supervisor`
- `audit`
- `frame_break`
- `expansion`
- `checkpoint`

This directory is the shared prompt layer for both interfaces. It does not replace `AGENTS.md`, `CLAUDE.md`, or Claude Code slash commands.
