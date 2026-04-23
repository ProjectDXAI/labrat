# labrat

[English](README.md) | [简体中文](README.zh-CN.md)

`labrat` is a local-first runtime that puts Claude Code or Codex on a real research problem with a scoreboard and enough structure to run for hours. Population search, not single-thread: families of ideas compete for compute budget, and the ones that produce real signal earn more room to keep going.

![labrat dashboard](docs/dash-sample.png)

<sub>Live example run: the baseline still leads on the main selection metric, while `classifier_search` has already won two decisive held-out challenges and earned extra funding.</sub>

`labrat` treats Claude Code and Codex as peer operator interfaces. Stronger reasoning models still help most on synthesis, audit, and consolidation, but the runtime contract and file layout stay the same across both.

**Jump to** → [Run it in 5 minutes](#run-it-in-5-minutes) · [Start from a profile](#start-from-a-profile) · [Create your own lab](#create-your-own-lab-from-scratch) · [Why it exists](#why-it-exists)

In plain English:

- you define a problem and a baseline
- the agent explores multiple families of ideas
- the runtime keeps the queue moving
- the evaluator scores results consistently
- families gain real status by winning hard held-out challenges, not just by overfitting the local hill-climb

## Why it exists

- **Async population search**: no global cycle barrier; workers keep evaluating descendants as soon as slots free up.
- **Funding over families**: credits are minted by stable, reproducible progress and spent on new descendants.
- **Consistent external evaluation**: workers produce artifacts, not authoritative verdicts.
- **Supervisor + worker model**: the agent supervises the runtime, while probe / mutation / crossover / audit workers execute bounded tasks.
- **File-as-Bus workspace**: durable files and append-only logs carry state forward so the supervisor can keep thin control over thick project state.
- **Decisive challenges**: a family earns extra status when it wins a held-out challenge that was not already baked into the local search metric.

This means a family can become strategically important even before it becomes the global selection champion. The dashboard now shows both the current champion and the current decisive-challenge leaders.

## Good first problems

`labrat` works best when the problem has:

- a clear baseline
- a bounded experiment runner
- a metric you can score consistently
- at least one harder held-out challenge beyond the main hill-climb metric

Good examples:

- tune a small classifier or ranking model
- iterate on prompt + rubric combinations with fixed evaluation
- search over retrieval / reranking strategies
- compare workflow variants where one family should win a specific hard slice, not just the average score

If you only open three things first:

- [program.md](program.md)
- [examples/nlp-sentiment/research_lab](examples/nlp-sentiment/research_lab)
- [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md)

## A useful framing

`labrat` is not a philosophy-of-science engine, but Lakatos is a useful mental model for the runtime.

Stay inside a family while it is still producing real signal. Escalate to audit or frame break when local repairs stop paying for themselves. In Lakatos's terms, a programme [“is progressive if it is both theoretically and empirically progressive, and degenerating if it is not”](https://plato.stanford.edu/archives/fall2020/entries/lakatos/). In `labrat`, that means a family should not only improve the known metric, but also win a decisive held-out test that rivals do not already own. More on that in [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md).

## Run it in 5 minutes

Start with the flagship example:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[nlp-sentiment]'
labrat doctor --lab-dir examples/nlp-sentiment/research_lab
labrat bootstrap --lab-dir examples/nlp-sentiment/research_lab
python -m http.server 8787 --directory examples/nlp-sentiment/research_lab
labrat status --lab-dir examples/nlp-sentiment/research_lab
labrat next-prompt --lab-dir examples/nlp-sentiment/research_lab --runner claude --phase auto
```

Use `--runner codex` for Codex.

The editable install is intentional: the `labrat` CLI keeps using the templates, profiles, and scripts from this checkout. If you prefer the original in-lab workflow, the copied `scripts/*.py` entrypoints still work unchanged inside each lab.

What you get from the example:

- a running dashboard
- a fully scaffolded lab
- held-out decisive challenges on top of search / selection metrics
- a reference supervisor + worker flow that you can copy into a new lab

## Agent interfaces

`labrat` does not depend on hidden local skills, private prompts, or machine-specific setup. The operator contract ships in the repo and in every generated lab:

- repo root: `AGENTS.md` for Codex, `CLAUDE.md` for Claude Code
- each lab: `AGENTS.md`, `.agents/skills/`, `CLAUDE.md`, `.claude/commands/`, and `agent_prompts/`
- shared runtime surface: `labrat ...` from the repo root or `python scripts/...` inside a lab

That means a user can clone the repo, open either Codex or Claude Code, and operate the lab from files that are already present in version control. Codex can optionally load the checked-in `labrat-operator` skill, but no hidden local skill file is required.

## Start from a profile

If you already know the shape of your research problem, a profile scaffolds a runnable lab in one command. No Phase 0 hand-editing, no `LABRAT_PLACEHOLDER` stubs.

```bash
labrat new ~/labs/my_search --profile=transformer-arch
cd ~/labs/my_search
python -m pip install -r requirements.txt
labrat doctor --lab-dir .
labrat check-readiness --lab-dir .
labrat bootstrap --lab-dir .
```

### Operator surfaces

Every lab, whether profile-scaffolded or hand-built, ships both primary operator surfaces:

- `AGENTS.md` for Codex
- `.agents/skills/labrat-operator/SKILL.md` for the optional Codex workflow
- `CLAUDE.md` plus `.claude/commands/` for Claude Code
- `agent_prompts/` for the shared phase prompts consumed by either interface

The Claude Code slash commands are short markdown files that wrap common operator actions so you do not have to remember the CLI invocations:

- `/next` — print the prompt for the current phase and execute it.
- `/why-stuck` — diagnose a stalled frontier from `state/frontier.json` and recent evaluations.
- `/synthesize` — summarise the last ~10 evaluations before dispatching more work.
- `/audit-candidate` — walk the highest-signal suspicious candidate through the audit worker.
- `/frame-break` — propose a structural pivot once cheap probes and audits are exhausted.
- `/consolidate` — write a compact checkpoint note to `logs/checkpoints/`.

Open Claude Code in the lab directory and type `/next`, or hand-run `python scripts/operator_helper.py next-prompt --runner claude --phase auto`. In Codex, read `AGENTS.md` and run `python scripts/operator_helper.py next-prompt --runner codex --phase auto`.

### Available profiles

- `transformer-arch` — tiny character-level transformer architecture search with held-out-distribution decisive challenges. Ships a synthetic runner so you can exercise the full runtime loop without a training framework; replace `scripts/run_experiment.py` with your own trainer when you want real training.

More profiles (world-model, multi-dataset) land in follow-up PRs. See [docs/PROFILES.md](docs/PROFILES.md) for the profile contract and [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md) for interim-checkpoint and long-running-job conventions.

## Create your own lab from scratch

If no profile fits your problem, scaffold an empty lab and finish Phase 0 by hand. The default path is deep research first.

```bash
labrat new my_lab
cd my_lab
labrat doctor --lab-dir .
labrat next-prompt --lab-dir . --runner claude --phase design
labrat check-readiness --lab-dir .
labrat bootstrap --lab-dir .
python -m http.server 8787
labrat next-prompt --lab-dir . --runner claude --phase auto
```

Use `--runner codex` if you are operating from Codex instead of Claude Code.

Phase 0 must produce:

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`
- `evaluation.yaml`
- `runtime.yaml`

`evaluation.yaml` now includes at least one held-out `prediction_tests` challenge. That is how the runtime distinguishes “fit the known metric a bit better” from “this family actually predicted something hard.”

## Repo map

- [program.md](program.md): repo-level entrypoint
- [docs/getting-started.md](docs/getting-started.md): setup and first-run flow
- [docs/runners.md](docs/runners.md): Codex and Claude Code operator contract
- [docs/MODEL_GUIDANCE.md](docs/MODEL_GUIDANCE.md): frontier-model prompting, reasoning-effort, and research guidance
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): runtime, state, and evaluation details
- [docs/PROFILES.md](docs/PROFILES.md): profile mechanism and how to author a new one
- [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md): `checkpoints.jsonl` contract, `failure_class` values, per-pool timeouts
- [docs/AUTONOMY.md](docs/AUTONOMY.md): permission allowlist, `/loop` cadence, stop criteria, cold-start recovery

## Background

`labrat` comes out of DXRG. We first used variants of this runtime internally to explore different financial world-model architectures and adjacent research workflows, then published the parts that generalized cleanly beyond that domain.

## References

`labrat` is its own system, but the current shape is informed by a few clear predecessors and adjacent designs:

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch): the minimal agent-driven autonomous experiment loop that helped establish the basic pattern of fixed evaluation plus overnight iteration.
- [AIRA_2](https://arxiv.org/abs/2603.26499): population search, stronger evaluation discipline, and stateful operator quality as first-class system levers.
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018): hierarchical orchestration, File-as-Bus coordination, progressive disclosure, and thin control over thick state.
- [Stanford Encyclopedia of Philosophy: Imre Lakatos](https://plato.stanford.edu/archives/fall2020/entries/lakatos/): useful framing for when a family is still progressive versus when it has become degenerating and should escalate to audit or frame break.

<sub>English is canonical. The Chinese README is included for accessibility and may lag slightly behind.</sub>
