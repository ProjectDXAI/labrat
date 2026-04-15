# Agent Prompts

This directory is the lab-local operating surface for Claude Code and Codex.

## Structure

- `shared/`: phase-specific workflow prompts
- `claude_code.md`: runtime guidance for Claude Code
- `codex.md`: runtime guidance for Codex

## How to use it

1. Run `python scripts/operator_helper.py status`.
2. Run `python scripts/operator_helper.py next-prompt --runner claude --phase auto` or the Codex equivalent.
3. Give that output to the agent.
4. Let the agent follow the local prompt files and update this lab's state.

## Phase flow

1. `design`: complete Phase 0 deep research before bootstrapping.
2. `cycle`: run the normal exploitation/exploration loop.
3. `audit`: inspect invalid-fast or near-miss families before discarding them.
4. `scout`: research new ideas for stuck branches.
5. `frame_break`: challenge the current bottleneck model before spending more search budget.
6. `expansion`: search the negative space when the whole lab flattens.
7. `checkpoint`: consolidate findings and decide what the next wave should be.
