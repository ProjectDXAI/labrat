# labrat

[English](README.md) | [简体中文](README.zh-CN.md)

`labrat` is a local-first runtime for giving Claude Code or Codex a real research problem, a scoreboard, and enough structure to keep going for hours.

Population search, not single-thread. Families of ideas compete for compute budget. The ones that produce real signal earn more room to keep going.

In plain English:

- you define a problem and a baseline
- the agent explores multiple families of ideas
- the runtime keeps the queue moving
- the evaluator scores results consistently
- families gain real status by winning hard held-out challenges, not just by overfitting the local hill-climb

![labrat dashboard](docs/dash-sample.png)

<sub>Live example run: the baseline still leads on the main selection metric, while `classifier_search` has already won two decisive held-out challenges and earned extra funding.</sub>

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
pip install -r examples/nlp-sentiment/requirements.txt
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py status
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Use `--runner codex` for Codex.

What you get from the example:

- a running dashboard
- a fully scaffolded lab
- held-out decisive challenges on top of search / selection metrics
- a reference supervisor + worker flow that you can copy into a new lab

## Start from a profile

If you already know the shape of your research problem, a profile scaffolds a runnable lab in one command. No Phase 0 hand-editing, no `LABRAT_PLACEHOLDER` stubs.

```bash
python scripts/new_lab.py my_transformer_search --profile=transformer-arch
cd my_transformer_search
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
```

From there, open Claude Code in the lab directory and type `/next` — the profile ships its own slash commands (`/next`, `/why-stuck`, `/synthesize`, `/audit-candidate`, `/frame-break`, `/consolidate`). You can also hand-run `python scripts/operator_helper.py next-prompt --runner claude --phase auto`.

Available profiles:

- `transformer-arch` — tiny character-level transformer architecture search with held-out-distribution decisive challenges. CPU-runnable in its default synthetic mode; flip `training.mode: "real"` after installing torch for real training.

More profiles (world-model, multi-dataset) land in follow-up PRs. See [docs/PROFILES.md](docs/PROFILES.md) for the profile contract and [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md) for interim-checkpoint and long-running-job conventions.

## Create your own lab from scratch

If no profile fits your problem, scaffold an empty lab and finish Phase 0 by hand. The default path is deep research first.

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

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
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): runtime, state, and evaluation details
- [docs/PROFILES.md](docs/PROFILES.md): profile mechanism and how to author a new one
- [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md): `checkpoints.jsonl` contract, `failure_class` values, per-pool timeouts

## Background

`labrat` comes out of DXRG. We first used variants of this runtime internally to explore different financial world-model architectures and adjacent research workflows, then published the parts that generalized cleanly beyond that domain.

## References

`labrat` is its own system, but the current shape is informed by a few clear predecessors and adjacent designs:

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch): the minimal agent-driven autonomous experiment loop that helped establish the basic pattern of fixed evaluation plus overnight iteration.
- [AIRA_2](https://arxiv.org/abs/2603.26499): population search, stronger evaluation discipline, and stateful operator quality as first-class system levers.
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018): hierarchical orchestration, File-as-Bus coordination, progressive disclosure, and thin control over thick state.
- [Stanford Encyclopedia of Philosophy: Imre Lakatos](https://plato.stanford.edu/archives/fall2020/entries/lakatos/): useful framing for when a family is still progressive versus when it has become degenerating and should escalate to audit or frame break.

<sub>English is canonical. The Chinese README is included for accessibility and may lag slightly behind.</sub>
