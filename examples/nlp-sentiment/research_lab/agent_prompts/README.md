# Agent Prompts

This example mirrors the generated prompt structure used by new labs.

`next-prompt --phase auto` may resolve to:

- `design`
- `cycle`
- `audit`
- `scout`
- `frame_break`
- `expansion`
- `checkpoint`

Use:

1. `python scripts/operator_helper.py status`
2. `python scripts/operator_helper.py next-prompt --runner claude --phase auto`

Or:

1. `python scripts/operator_helper.py status`
2. `python scripts/operator_helper.py next-prompt --runner codex --phase auto`
