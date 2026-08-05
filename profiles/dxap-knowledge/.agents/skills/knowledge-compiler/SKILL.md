---
name: knowledge-compiler
description: Use when working the executable-bibliography lab with Codex - compiling sources into concept, hypothesis, method and decision-relevance cards, running the SERVABLE gate, scoring retrieval policies, building evidence packets for a decision context, or reading the attribution ledger.
---

# Knowledge Compiler

Use this skill from a knowledge lab root, identified by `knowledge/concepts.yaml` and `scripts/knowledge.py`. The compilation contract itself is in `agent_prompts/shared/knowledge_compile.md`, shared with Claude Code's `/compile-concept`.

## Cold Start

1. `python scripts/knowledge.py status`
2. `python scripts/knowledge.py validate`
3. `python scripts/knowledge.py evaluate`
4. `python scripts/methods.py self-test`
5. Read `research_brief.md` and `dead_ends.md`.

## Compilation Contract

- One concept at a time. A card is done when it passes the SERVABLE gate, not when the prose reads well.
- Every card needs counterevidence. No contradicting concept and no alternative explanation means the gate fails, by design.
- Anchors, not quotes. Most sources are `reference_only`; write the mechanism in our own words and cite chapter or section.
- Never claim `implementation_status: implemented` without a method binding at the registered version. Version drift fails validation deliberately.
- A hypothesis without a cost model is rejected. An ex-ante prediction with no costs is not a testable trading claim.

## Methods

- `python scripts/methods.py list` before writing anything new; the implementation may already exist.
- A new method needs inputs, outputs, an as-of contract, known numerical failure modes, and a self-test with a closed-form or hand-checkable answer.
- The as-of contract is not decoration. A method that can see data after the decision timestamp will produce a beautiful, useless result.

## Retrieval

- `python scripts/knowledge.py retrieve --context <ctx.json> --policy decision_value --markdown` builds the packet.
- Abstention is a valid outcome. Do not disable filters to force an answer.
- `python scripts/knowledge.py evaluate` scores every policy against the labelled trials; the `raw_similarity` arm is the control and is expected to lose on precision, abstention and counterevidence while winning hit rate.

## Ledger

- Record retrieval events, inspections, tool calls, claims, decisions and matured outcomes as they happen; `python scripts/ledger.py ladder` counts the rungs.
- `python scripts/ledger.py analyze` refuses on unmatured outcomes or an unfrozen batch. That refusal is the point — do not pass `--allow-unfrozen` and then report the number.

## Reasoning Effort

- Normal effort for status, evaluation and packet building.
- Higher effort for compiling a new concept from a source, for deciding what counterevidence a card needs, and for specifying a new method's failure modes.

## Stop Conditions

Stop and surface to the user when:

- a source's rights do not permit the use a card would need
- a method's self-test fails, since every packet citing it is now suspect
- the trial set no longer discriminates between policies, meaning it needs harder contexts rather than more policies
- someone asks for a Gate 2 or Gate 3 claim, which cannot be produced inside this lab
