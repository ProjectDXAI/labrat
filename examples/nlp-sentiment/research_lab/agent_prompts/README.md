# Agent Prompts

Use the helper instead of guessing the next step.

1. `python scripts/operator_helper.py status`
2. `python scripts/operator_helper.py runtime-summary`
3. `python scripts/operator_helper.py next-prompt --runner claude --phase auto`
   or
   `python scripts/operator_helper.py next-prompt --runner codex --phase auto`

Supported phases:

- `design`
- `supervisor`
- `audit`
- `frame_break`
- `expansion`
- `checkpoint`
