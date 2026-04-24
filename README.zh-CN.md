# labrat

[English](README.md) | [简体中文](README.zh-CN.md)

`labrat` 是一个本地优先的研究运行时，用来把 Claude Code 或 Codex 放到一个真实研究问题上：有问题定义、有基线、有计分板，也有足够的结构让它持续运行数小时。这里做的是人口式搜索，而不是单线程尝试：多个思路家族竞争计算预算，真正产生信号的家族会获得更多继续探索的空间。

![labrat dashboard](docs/dash-sample.png)

<sub>示例截图来自一次真实运行：主选择指标上的全局冠军仍然是 baseline，但 `classifier_search` 已经赢下两个决定性保留挑战，并因此获得了额外 funding。</sub>

`labrat` 把 Claude Code 和 Codex 视为同等的一线操作界面。更强的推理模型在 synthesis、audit、consolidation 这些步骤上最有价值，但运行时契约和文件布局对两个界面保持一致。

**快速跳转** → [5 分钟跑起来](#5-分钟跑起来) · [从 profile 开始](#从-profile-开始) · [从零创建 lab](#从零创建-lab) · [为什么需要它](#为什么需要它)

用更直白的话说：

- 你定义问题和基线
- 智能体探索多个思路家族
- 运行时持续调度队列
- 评估器稳定、一致地打分
- 家族通过赢下困难的 held-out challenge 获得地位，而不是只在局部 hill-climb 指标上过拟合

## 为什么需要它

- **异步人口式搜索**：没有全局 cycle barrier；worker 一空闲就继续评估新后代。
- **按家族 funding**：credits 由稳定、可复现的进展铸造，再花到新后代上。
- **外部一致评估**：worker 只产出 artifact，不负责最终裁决。
- **Supervisor + Worker 模式**：智能体监督运行时，而 probe / mutation / crossover / audit worker 执行边界清晰的任务。
- **File-as-Bus 工作区**：持久化文件和追加式日志承载长期状态，让 supervisor 用薄控制层管理厚项目状态。
- **决定性挑战**：家族如果赢下并非局部搜索指标本身的保留挑战，就会获得额外状态与 funding。

这意味着：一个家族即使还不是全局 selection champion，也可能已经在战略上变得重要。仪表盘会同时显示主冠军和决定性挑战的领先者。

## 适合的首批问题

`labrat` 最适合的问题通常具有这些特征：

- 有明确基线
- 有边界清晰的实验运行器
- 有可以稳定计算的指标
- 除了主 hill-climb 指标以外，至少还有一个更难的 held-out challenge

适合的例子：

- 调一个小型分类器或排序模型
- 在固定评估下迭代 prompt + rubric 组合
- 搜索 retrieval / reranking 策略
- 比较若干 workflow 变体，其中某个家族应该赢下特定困难切片，而不是只提升平均分

如果你第一次打开仓库，先看这三个入口：

- [program.md](program.md)
- [examples/nlp-sentiment/research_lab](examples/nlp-sentiment/research_lab)
- [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md)

## 一个有用的理解框架

`labrat` 并不是一个“科学哲学引擎”，但 Lakatos 很适合用来理解它的运行逻辑。

当一个家族还能持续产出真实信号时，就继续在家族内部推进；当局部修补已经不再值得继续投入时，就升级到 audit 或 frame break。Lakatos 的说法是：一个研究纲领如果在理论上和经验上都在前进，就是 progressive；否则就是 degenerating。在 `labrat` 里，这意味着家族不只要提升已知指标，还要赢下对手没有赢下的明确困难测试。更多细节见 [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md)。

## 5 分钟跑起来

先从旗舰示例开始：

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

如果用 Codex，把 `--runner claude` 换成 `--runner codex`。

这里使用 editable install 是有意的：`labrat` CLI 会继续使用当前 checkout 里的 templates、profiles 和 scripts。如果你更喜欢 lab 内部的原始工作流，每个 lab 里复制出来的 `scripts/*.py` 入口仍然可用。

这个示例会给你：

- 一个正在运行的 dashboard
- 一个完整脚手架化的 lab
- 建立在 search / selection 指标之上的 held-out decisive challenges
- 一个可以直接复制到新实验中的 supervisor + worker 参考流程

## Agent 界面

`labrat` 不依赖隐藏的本地 skills、私有 prompts 或机器专属设置。操作契约会随仓库和每个生成的 lab 一起提交：

- 仓库根目录：Codex 使用 `AGENTS.md`，Claude Code 使用 `CLAUDE.md`
- 每个 lab：`AGENTS.md`、`.agents/skills/`、`CLAUDE.md`、`.claude/commands/`、`agent_prompts/`
- 共享运行时入口：在仓库根目录用 `labrat ...`，在 lab 内部用 `python scripts/...`

也就是说，用户 clone 仓库后，可以打开 Codex 或 Claude Code，直接从版本控制中的文件开始操作。Codex 可以选择加载仓库内置的 `labrat-operator` skill，但不需要任何隐藏的本地 skill 文件。

## 从 profile 开始

如果你的研究问题已经匹配某个现有 profile，可以用一条命令生成可运行 lab。这样不需要手工完成 Phase 0，也不会留下 `LABRAT_PLACEHOLDER`。

```bash
labrat new ~/labs/my_search --profile=transformer-arch
cd ~/labs/my_search
python -m pip install -r requirements.txt
labrat doctor --lab-dir .
labrat check-readiness --lab-dir .
labrat bootstrap --lab-dir .
```

### 操作界面

每个 lab，无论来自 profile 还是从零创建，都会包含两个主要操作界面：

- `AGENTS.md`：给 Codex 的 lab 操作说明
- `.agents/skills/labrat-operator/SKILL.md`：可选的 Codex workflow
- `CLAUDE.md` 和 `.claude/commands/`：给 Claude Code 的说明与 slash commands
- `agent_prompts/`：两个界面共享的 phase prompts

Claude Code slash commands 是短小的 markdown 文件，会变成会话中的命令，避免你记住所有 CLI 调用：

- `/next`：打印并执行当前 phase prompt
- `/why-stuck`：根据 `state/frontier.json` 和近期评估诊断卡住原因
- `/synthesize`：在继续 dispatch 前总结最近约 10 次评估
- `/audit-candidate`：把最高信号的可疑候选交给 audit worker
- `/frame-break`：当 cheap probes 和 audits 都不再有效时提出结构性 pivot
- `/consolidate`：向 `logs/checkpoints/` 写入紧凑 checkpoint

在 lab 目录里打开 Claude Code 后可以直接输入 `/next`，也可以手动运行 `python scripts/operator_helper.py next-prompt --runner claude --phase auto`。在 Codex 中，先读 `AGENTS.md`，然后运行 `python scripts/operator_helper.py next-prompt --runner codex --phase auto`。

### 当前 profile

- `transformer-arch`：一个小型字符级 transformer 架构搜索 profile，包含 held-out-distribution decisive challenges。它默认使用 synthetic runner，因此不需要训练框架也能跑通完整 runtime loop；如果你要做真实训练，替换 `scripts/run_experiment.py` 即可。

更多 profiles（world-model、multi-dataset）会在后续 PR 中加入。profile 契约见 [docs/PROFILES.md](docs/PROFILES.md)，长任务和中间 checkpoint 约定见 [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md)。

## 从零创建 lab

如果没有 profile 适合你的问题，可以 scaffold 一个空 lab，然后手工完成 Phase 0。默认路径是先做 deep research。

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

如果你使用 Codex，把 `--runner claude` 换成 `--runner codex`。

Phase 0 必须产出：

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`
- `evaluation.yaml`
- `runtime.yaml`

`evaluation.yaml` 现在至少要包含一个 held-out `prediction_tests` challenge。这就是运行时区分“只是把已知指标抬高了一点”和“这个家族真的预测到了困难现象”的关键。

## 仓库地图

- [program.md](program.md)：仓库级入口
- [docs/getting-started.md](docs/getting-started.md)：实操启动流程
- [docs/runners.md](docs/runners.md)：Codex 和 Claude Code 的操作契约
- [docs/MODEL_GUIDANCE.md](docs/MODEL_GUIDANCE.md)：frontier model prompting、reasoning effort 和 research guidance
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：运行时、状态和评估细节
- [docs/PROFILES.md](docs/PROFILES.md)：profile 机制和新 profile 编写方式
- [docs/LONG_HORIZON.md](docs/LONG_HORIZON.md)：`checkpoints.jsonl`、`failure_class`、per-pool timeouts 的约定
- [docs/AUTONOMY.md](docs/AUTONOMY.md)：权限 allowlist、`/loop` cadence、stop criteria、cold-start recovery

## 背景

`labrat` 来自 DXRG。我们最早在内部用它来探索不同的金融 world-model 架构以及其他研究工作流，后来把那些能明显泛化到更广问题上的部分整理并开源。

## 参考来源

`labrat` 是一个独立系统，但当前形态受到这些项目和论文的启发：

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)：固定评估 + 智能体持续实验的极简模式。
- [AIRA_2](https://arxiv.org/abs/2603.26499)：人口式搜索、严格评估纪律，以及把 operator 质量视为系统问题。
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018)：分层编排、File-as-Bus 协调、渐进披露，以及薄控制层管理厚状态。
- [Stanford Encyclopedia of Philosophy: Imre Lakatos](https://plato.stanford.edu/archives/fall2020/entries/lakatos/)：帮助理解一个家族何时仍然 progressive，何时已经 degenerating，需要升级到 audit 或 frame break。

<sub>英文 README 为规范版本。中文翻译用于提升可访问性。</sub>
