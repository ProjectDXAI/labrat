# Claude Code Runner Wrapper

You are operating this lab from Claude Code.

- Use the local lab files as the source of truth.
- Keep shell output readable. Redirect noisy command output to files and only surface the important result lines.
- Use subagents when the phase prompt explicitly benefits from parallel branch work.
- Use `/loop` only after the lab is bootstrapped and the human wants repeated cycles.
- Write state updates and handoff files directly in this lab instead of narrating the plan in chat.
