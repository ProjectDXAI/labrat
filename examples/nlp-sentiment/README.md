# NLP Sentiment Example

This is the canonical labrat vNext example.

The runnable lab lives in `research_lab/`.

It ships the same operator surface expected from any real lab:

- `research_lab/AGENTS.md` for Codex
- `research_lab/.agents/skills/labrat-operator/SKILL.md` for Codex's optional lab-operation workflow
- `research_lab/CLAUDE.md` and `research_lab/.claude/commands/` for Claude Code
- `research_lab/agent_prompts/` for the shared phase prompts

There is no hidden skill-file requirement.

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
python -m venv .venv
source .venv/bin/activate
pip install -e '.[nlp-sentiment]'
labrat doctor --lab-dir examples/nlp-sentiment/research_lab
labrat bootstrap --lab-dir examples/nlp-sentiment/research_lab
python -m http.server 8787 --directory examples/nlp-sentiment/research_lab
labrat status --lab-dir examples/nlp-sentiment/research_lab
labrat runtime-summary --lab-dir examples/nlp-sentiment/research_lab
labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto
```

Swap `--runner codex` to drive the same lab from Codex.

## Fixture-driven tests

To load a controlled audit state:

```bash
cd examples/nlp-sentiment/research_lab
python scripts/load_fixture.py audit
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

To load a frame-break state:

```bash
python scripts/load_fixture.py frame_break
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```
