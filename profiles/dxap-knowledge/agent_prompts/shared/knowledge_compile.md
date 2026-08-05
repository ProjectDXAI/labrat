# Phase prompt — compiling a source into executable knowledge

Shared by Claude Code (`/compile-concept`) and Codex (`$knowledge-compiler`).

The output of reading a source is not a summary. It is a set of cards that a retrieval layer can serve to a live decision, and that a method can compute evidence for.

## The chain

```
source -> mechanism -> assumptions -> observable signature
       -> deterministic test -> decision relevance -> realized outcome
```

Each arrow is a card field. A card that skips one leaves the agent with a plausible sentence and no way to act on it or check it.

## The loop

```bash
python scripts/knowledge.py compile-queue --limit 15   # what to read next, and why
python scripts/corpus.py rights --bucket <bucket>      # what you may do with it
# read the chapter, draft cards into knowledge/*.yaml
python scripts/knowledge.py validate                   # the SERVABLE gate
python scripts/knowledge.py evaluate                   # did retrieval quality move
```

## Writing a concept card

Work in this order. Each step constrains the next.

1. **Mechanism.** What actually causes the effect? Not "order flow predicts returns" but why: queue depletion, adverse selection, inventory risk, information absorption. If you cannot state the cause, you have an empirical regularity, not a mechanism — say so in the card and set confidence accordingly.
2. **Assumptions.** What has to be true for the mechanism to operate? These are the fields that make a card refuse to be applied where it does not belong. Be specific: "price-time priority", "competitive risk-neutral market maker", "observation noise variance roughly stable".
3. **Required observables.** What data must exist at decision time? These become hard retrieval filters, so name them precisely and reuse the existing vocabulary (`l1_book`, `l2_book`, `signed_volume`, `mfe_history`, `funding_rate`, …).
4. **Expected empirical signature.** What would we see if this is operating here, now? This is what distinguishes a concept the agent can check from one it can only believe.
5. **Counterevidence.** At least one contradicting concept or alternative explanation, plus the known failure modes. The gate enforces this. If nothing could argue against the card, you have not finished reading.
6. **Source anchors.** `entry-id#chapter-4`. Anchors you have actually seen. Never a page number you inferred.

## Rights while compiling

- Most sources are `reference_only`. Read them, learn the mechanism, write it in our own words. That is the compliant route to the same knowledge.
- A verbatim quote is only permitted from a manifest-eligible source, and the gate will reject it otherwise.
- Never cite an `excluded` source, whatever it contains.

## Binding a method

If the concept can be measured, it should be — and the agent should call the implementation, not re-derive it mid-turn.

- Check `python scripts/methods.py list` first.
- A new implementation needs: declared inputs and outputs, an as-of contract stating what it may see, known numerical failure modes, and a self-test with a closed-form or hand-checkable answer.
- Pin `implementation_version` in `knowledge/methods.yaml`. When the implementation changes version, validation fails until someone re-verifies the card. That is intentional: a silent numerical change under a stable card is how a knowledge base quietly becomes wrong.
- `implementation_status: implemented` without a binding fails the gate.

## Writing a hypothesis

The concept is general; the hypothesis is what makes it testable here. Required: market context, causal story, ex-ante prediction, null, measurement operator, eligible universe, decision-timestamp rule, outcome horizons, **cost model**, invalidation conditions.

The decision-timestamp rule is where point-in-time discipline lives. Write it as a constraint on what the operator may see, not as a note.

## Writing a decision-relevance card

State the operator and the comparison, not the rule.

Wrong: "Close the position after it gives back a third of its maximum favourable excursion."

Right: "Estimate the conditional probability of a further favourable excursion given drawdown from MFE, flow innovation, spread, time since catalyst and regime. Compare continuation value against execution and opportunity cost."

Both halves are required — what would support the action *and* what would argue against it. The validator lints for unconditional directive language.

## When to stop

- The card passes `validate` and the concept is genuinely distinct from what is already compiled. Two cards restating one mechanism cost context at retrieval time and buy nothing.
- If the chapter yields no mechanism you can state, no observable you can name, and nothing that would falsify it, record that in `dead_ends.md` and move on. Not every dense source compiles.
