Run one corpus scouting round in this lab.

1. Read `agent_prompts/shared/corpus_round.md` — it is the scouting contract for both runners.
2. Orient: `python scripts/corpus.py status` and `python scripts/corpus.py frontier --limit 15`.
3. If the runtime already opened a round for a leased candidate (`corpus/rounds/round-NNN/request.json` has a `candidate_id` and no `merge_report.json`), work that round. Otherwise open one:
   `python scripts/corpus.py round open --mode <expand|verify|acquire> --bucket <bucket> --limit 15`
4. Read `corpus/rounds/round-NNN/request.md`, do the research, and write `corpus/rounds/round-NNN/findings.yaml`.
5. Close it. For a runtime-opened round, re-run the candidate through `scripts/run_experiment.py` so it is scored. For a hand-run round, `python scripts/corpus.py round close`.
6. `python scripts/corpus.py report` and tell the user what moved.

Rights rules are hard constraints, not preferences: `confidence: confirmed` requires an evidence URL you actually read and a check date; free-to-read is not licensed; confidential material is excluded. Never edit `corpus/bibliography.yaml` by hand — findings files are the only write path.

Stay inside this lab.
