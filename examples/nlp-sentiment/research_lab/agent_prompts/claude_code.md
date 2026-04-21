Use Claude Code as a stateful runtime operator.

- Read `CLAUDE.md` first.
- Start with `python scripts/operator_helper.py doctor` and `python scripts/operator_helper.py status`.
- Use `/next` or `python scripts/operator_helper.py next-prompt --runner claude --phase auto` to choose the next phase.
- Prefer short command/result loops.
- Use local files as the source of truth.
- Keep worker runs narrow and artifact-oriented.
- Let the runtime decide promotion.
