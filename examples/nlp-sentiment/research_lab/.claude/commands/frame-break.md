Trigger a frame-break cycle only after cheap probes and audits are no longer productive.

1. Confirm `state/frontier.json.frame_break_required: true` and `remaining_cheap_probes: 0` across families. If either condition is false, stop and run `/why-stuck` instead.
2. Read `frame_break.md`.
3. Read the last ten entries in `state/evaluations.jsonl`. Look for structural patterns that the current families cannot express.
4. Propose a patch to `branches.yaml`, a new family or a revised axis set, and write it to `logs/expansions/<timestamp>.md` as the `expansion_scout` expects.
5. Do not edit `branches.yaml` directly. Let the expansion_scout flow merge it.
