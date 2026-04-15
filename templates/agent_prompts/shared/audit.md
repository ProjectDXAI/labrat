# Phase: Implementation Audit

Audit a suspicious frontier family before the lab discards it or frame-breaks away from it.

## Read first

1. `implementation_audit.md`
2. `logs/handoff.md`
3. `research_brief.md`
4. `research_sources.md`

## Your job

- pick the most suspicious invalid-fast or near-miss family
- rerun the anomaly and one or two cheap controls
- decide whether the issue is mechanical or scientific
- keep promising families alive with a concrete next probe
- update `logs/handoff.md` and leave an audit note or patch

## Output standard

- the audit names one specific target family
- it distinguishes implementation bugs from true dead ends
- it leaves a concrete next probe when the family survives
- it avoids a full frame break unless the audit says the family is genuinely exhausted
