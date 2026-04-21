Use Codex as a stateful runtime operator.

- Read `AGENTS.md` first.
- Start with `python scripts/operator_helper.py doctor` and `python scripts/operator_helper.py status`.
- Use `python scripts/operator_helper.py next-prompt --runner codex --phase auto` to choose the next phase.
- Keep supervision decisions grounded in runtime state files.
- Prefer direct commands over long freeform reasoning.
- Workers produce artifacts; evaluator and runtime produce decisions.
