# Prioritized tasks

_Seed. The supervisor overwrites this file each synthesis cycle with a durable note about the next highest-leverage work. Keep it short — it is control intent, not a log._

## Cold start (before the supervisor's first synthesis)

1. Run `python scripts/operator_helper.py status` to see whether Phase 0 is ready and whether the runtime is initialized.
2. If Phase 0 is incomplete, do the design phase first (`operator_helper.py next-prompt --phase design`).
3. If the runtime is not initialized, run `python scripts/bootstrap.py`.
4. Then enter the supervisor loop via `/next` (or `operator_helper.py next-prompt --phase auto`).

Once the first synthesis cycle runs, this file becomes a one-paragraph statement of current control intent and is overwritten each cycle.
