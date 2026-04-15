# Phase: Normal Cycle

Operate the lab's autonomous exploitation/exploration loop.

## Read first

1. `orchestrator.md`
2. `research_brief.md`
3. `research_sources.md`

## Your job

- Follow the orchestrator's graduated read order.
- Use the lab's cheap screening or proxy stage when one is defined before spending full experiment cost.
- Run branch-local inner hill climbing inside selected branches.
- Force a few cheap orthogonal probes around a live frontier before declaring the family flat.
- Favor branch ladders like width/order/packing, overlap/prefetch, and representation/layout probes when they are cheaper than a full formulation jump.
- Switch to mutation mode when a branch exhausts its explicit search space but still has budget.
- Detect stuck branches and route them to scout mode instead of stalling.
- Route invalid-fast or suspicious near-miss families to implementation audit mode instead of exhausting them.
- Trigger frame-break mode when the frontier is flat and the current family may be structurally incomplete.
- Trigger expansion after the frame break identifies what assumption needs to change.
- Write state updates and `logs/handoff.md` before ending the cycle.

## Rules

- Use only this lab's files and scripts.
- Do not ask the human for permission during a cycle.
- Keep one coherent state trail.
