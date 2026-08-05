Report the corpus state to the user.

Run, in order:

```bash
python scripts/corpus.py status
python scripts/corpus.py rights --verify-queue --limit 10
python scripts/corpus.py frontier --limit 10
python scripts/corpus.py manifest
```

Then summarise in a few lines:

- coverage against page targets, and which buckets are `open`, `cooling`, or `saturated`
- how many pages are manifest-eligible versus study-only, and what is blocking the rest
- the highest-upside verification targets (confirmation there unlocks the most pages)
- the top frontier targets and which bucket they belong to
- the single next round you would run, with mode and bucket

Do not open a round from this command. Report only.
