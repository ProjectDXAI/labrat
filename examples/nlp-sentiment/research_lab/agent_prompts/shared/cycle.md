# Phase: Normal Cycle

Operate the example lab's autonomous exploitation/exploration loop.

## Read first

1. `orchestrator.md`
2. `research_brief.md`
3. `research_sources.md`

## Your job

- follow the orchestrator's graduated read order
- use cheap probes before expensive sweeps when the branch allows it
- run branch-local inner hill climbing inside selected branches
- force a few cheap orthogonal probes around a live frontier before declaring the family flat
- switch to mutation mode when a branch exhausts its explicit search space but still has budget
- detect stuck branches and route them to scout mode instead of stalling
- route suspicious near-miss families to implementation audit instead of exhausting them
- trigger frame-break or expansion only after probes and audits are no longer the right next step
- write state updates and `logs/handoff.md` before ending the cycle
