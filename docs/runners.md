# Runners: Claude Code and Codex

Both runners use the same runtime contract.

## Claude Code

Typical loop:

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Claude Code should act as:

- async supervisor
- audit operator
- frame-break / expansion operator
- bounded worker when you explicitly assign a probe / mutation / crossover task

## Codex

The Codex flow is the same:

```bash
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

## Shared rules

- workers do not self-promote
- `result.json` is not the final verdict
- `evaluator.py` is authoritative
- runtime state is the source of truth
- use audit before killing suspicious families
- use frame break only after cheap probes and audit are no longer the right move
