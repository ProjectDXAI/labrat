Build an evidence packet for a decision context.

Given a context file (or the user's description of a decision — write it to a context JSON first, with `timestamp`, `market_type`, `instrument`, `decision_type`, `horizon`, `observables_available`, `tools_available`, `uncertainties`, `state_notes`, `latency_budget_seconds`):

```bash
python scripts/knowledge.py retrieve --context <ctx.json> --policy decision_value --markdown
```

Then:

1. Report what came back, including the counterevidence — never drop it because it weakens the case.
2. If the packet abstained, say so plainly and report why. Abstention is a result. Do not re-run with the filters off to manufacture an answer.
3. For each served card with a bound method, run it rather than reasoning about what it would say: `python scripts/methods.py run --method <id> --input <payload.json>`.
4. Record the retrieval event in the ledger so the offered-to-beneficial ladder stays countable:
   `python scripts/ledger.py record --json-event '{"event_type":"retrieval_event", ...}'`

The packet is evidence for the decision, not the decision. State applicability, supporting evidence, counterevidence, what is missing, and the implication — then let the caller decide.
