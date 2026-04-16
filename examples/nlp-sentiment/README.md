# NLP Sentiment Example

This is the canonical labrat vNext example.

The runnable lab lives in `research_lab/`.

## What it demonstrates

- async population runtime
- external consistent evaluation
- decisive held-out challenges that are separate from the search metric
- three families:
  - `text_representation`
  - `classifier_search`
  - `fusion_frontier`
- one cheap-probe-heavy family
- one mutation-heavy family
- one crossover family
- audit and frame-break fixtures
- family-level challenge claims in `branches.yaml`

## Quick start

```bash
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py status
python scripts/operator_helper.py runtime-summary
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

## Fixture-driven tests

To load a controlled audit state:

```bash
python scripts/load_fixture.py audit
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

To load a frame-break state:

```bash
python scripts/load_fixture.py frame_break
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```
