Compile a source into concept, hypothesis, method and decision-relevance cards.

1. Read `agent_prompts/shared/knowledge_compile.md` — it is the compilation contract for both runners.
2. Pick the target: `python scripts/knowledge.py compile-queue --limit 15`, or the source the user named.
3. Check the rights position first: `python scripts/corpus.py rights --bucket <bucket>`. If the source is `reference_only`, you may read it and write your own account of the mechanism; you may not paste its text into a card.
4. Draft the cards into `knowledge/*.yaml`, one concept at a time. Every concept needs a mechanism, its load-bearing assumptions, the observables it requires, an expected empirical signature, known failure modes, at least one contradicting concept or alternative explanation, and source anchors.
5. If the concept can be measured, bind a method: check `python scripts/methods.py list` for an existing implementation, or specify a new one in `scripts/methods.py` with a closed-form self-test before claiming `implementation_status: implemented`.
6. Validate: `python scripts/knowledge.py validate`. The SERVABLE gate must pass before anything is retrievable.
7. Re-score the retrieval policies if the store changed materially: `python scripts/knowledge.py evaluate`.

Never invent a page anchor, a source, or a numerical result. An anchor you have not seen is worse than no anchor.

Stay inside this lab.
