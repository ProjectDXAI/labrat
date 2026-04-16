# labrat

[English](README.md) | [简体中文](README.zh-CN.md)

`labrat` 是一个本地优先的研究运行时，用来把 Claude Code 或 Codex 放到一个真实研究问题前：有问题定义、有基线、有计分板，也有足够的结构让它持续跑上几个小时。

用更直白的话说：

- 你先定义问题和基线
- 智能体会探索多个思路家族
- 运行时负责持续调度队列
- 评估器负责稳定、一致地打分
- 一个家族真正获得“地位”，不只是因为它更贴合已知数据，而是因为它赢下了一个不属于局部爬山目标的困难保留测试

![labrat dashboard](docs/dash-sample.png)

<sub>示例截图来自一次真实运行：主选择指标上的全局冠军仍然是 baseline，但 `classifier_search` 已经赢下了两个决定性保留挑战，并因此获得了额外 funding。</sub>

## 它解决什么问题

- **异步人口式搜索**：没有全局 cycle barrier；只要 worker 空闲，就继续评估新后代。
- **按家族 funding**：credits 由稳定、可复现的进展铸造，再花到新后代上。
- **外部一致评估**：worker 只产出 artifact，不负责最终裁决。
- **Supervisor + Worker 模式**：智能体负责监督运行时，而 probe / mutation / crossover / audit worker 执行边界清晰的任务。
- **File-as-Bus 工作区**：持久化文件和追加式日志承载长期状态，让 supervisor 用很薄的控制层管理很厚的项目状态。
- **决定性挑战**：某个家族如果赢下了一个并非局部搜索目标本身的保留挑战，就会获得额外状态与 funding。

这意味着：一个家族即使还不是全局 selection champion，也可能已经在战略上变得重要。仪表盘会同时显示主冠军和“决定性挑战”的领先者。

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
- 比较若干 workflow 变体，其中某个家族应该赢下某个特定困难切片，而不是只提升平均分

如果你第一次打开仓库，只看这三个入口：

- [program.md](program.md)
- [examples/nlp-sentiment/research_lab](examples/nlp-sentiment/research_lab)
- [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md)

## 一个有用的理解框架

`labrat` 并不是一个“科学哲学引擎”，但 Lakatos 很适合用来理解它的运行逻辑。

当一个家族还能持续产出真实信号时，就继续在家族内部推进；当局部修补已经不再值得继续投入时，就升级到 audit 或 frame break。Lakatos 的经典说法是：一个研究纲领如果在理论上和经验上都在前进，就是 progressive；否则就是 degenerating。

这里不只是“在已知数据上分数涨了一点”。一个更强的家族还应该赢下某个对手没有赢下的、明确而困难的测试。Halley 彗星预测之所以重要，不是因为 Newton 只是在旧观测上拟合得更好，而是因为它给出了一个精确的新预测。

这与 `labrat` 的搜索阶梯是对应的：

- cheap probes 和 mutation 用来检验当前家族是否仍在前进
- implementation audit 用来区分：问题出在实现，还是方向本身
- 当局部搜索已经不再值得继续时，再进入 frame break 和 expansion

## 5 分钟跑起来

先从旗舰示例开始：

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

如果用 Codex，把 `--runner claude` 换成 `--runner codex`。

这个示例会给你：

- 一个正在运行的 dashboard
- 一个完整脚手架化的 lab
- 建立在 search / selection 指标之上的 held-out decisive challenges
- 一个可以直接复制到新实验中的 supervisor + worker 参考流程

## 创建你自己的 lab

默认流程是先做 deep research，再启动运行时。

```bash
python scripts/new_lab.py my_lab
cd my_lab
python scripts/operator_helper.py next-prompt --runner claude --phase design
python scripts/operator_helper.py check-readiness
python scripts/bootstrap.py
python -m http.server 8787
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Phase 0 必须产出：

- `branches.yaml`
- `dead_ends.md`
- `research_brief.md`
- `research_sources.md`
- `evaluation.yaml`
- `runtime.yaml`

`evaluation.yaml` 现在至少要包含一个 held-out `prediction_tests` challenge。这就是运行时区分“只是把已知指标抬高了一点”和“这个家族真的预测到了困难现象”的关键。

## 运行时模型

权威状态文件是：

- `state/runtime.json`
- `state/candidates.jsonl`
- `state/jobs.json`
- `state/workers.json`
- `state/evaluations.jsonl`
- `state/frontier.json`
- `state/checkpoints.jsonl`

运行时的核心机制包括：

- 带温度的 steady-state dispatch
- 用 family credits 替代隔离式 branch budgets
- promotion 前做 rerun / stability 检查
- 对 invalid-fast 或不稳定 near-miss 候选触发 audit
- 只有当 cheap probes 和 audit 都不再支持继续局部搜索时，才进入 frame break

## 新 lab 必备文件

每个新 lab 都会包含：

- `evaluation.yaml`
- `runtime.yaml`
- bootstrap 后生成的 `coordination/workspace_map.md`
- `coordination/prioritized_tasks.md`
- `coordination/implementation_log.md`
- `coordination/experiment_log.md`
- `orchestrator.md`
- `probe_worker.md`
- `mutation_worker.md`
- `crossover_worker.md`
- `implementation_audit.md`
- `frame_break.md`
- `expansion_scout.md`
- `agent_prompts/`

`run_experiment.py` 负责生成 artifact 和指标。

`evaluator.py` 是以下指标的唯一权威来源：

- `search_eval`
- `selection_eval`
- `final_eval`

## UI

当前追踪的 UI 是静态 dashboard：`templates/dashboard.html`。

它围绕 runtime 状态组织：

- worker pool 健康度
- 队列深度
- family funding
- candidate frontier
- audit 队列
- expansion 状态

## 背景

`labrat` 来自 DXRG。我们最早在内部用它来探索不同的金融 world-model 架构以及其他研究工作流，后来把那些能明显泛化到更广问题上的部分整理并开源。

## 仓库地图

- [program.md](program.md)：仓库级入口
- [docs/getting-started.md](docs/getting-started.md)：实操启动流程
- [docs/runners.md](docs/runners.md)：Claude Code 和 Codex 的使用方式
- [docs/DEEP_RESEARCH.md](docs/DEEP_RESEARCH.md)：真实 lab 的设计指导
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)：运行时模型
- [examples/nlp-sentiment/research_lab](examples/nlp-sentiment/research_lab)：规范参考示例

## 参考来源

`labrat` 是一个独立系统，但当前形态明显受到这些项目和论文的启发：

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)：最直接的祖先之一，展示了“固定评估 + 智能体持续实验”的极简模式。
- [AIRA_2](https://arxiv.org/abs/2603.26499)：人口式搜索、严格评估纪律、以及把 operator 质量视为系统问题。
- [Toward Autonomous Long-Horizon Engineering for ML Research](https://arxiv.org/abs/2604.13018)：分层编排、File-as-Bus 协调、渐进披露、以及“薄控制层管理厚状态”。
- [Stanford Encyclopedia of Philosophy: Imre Lakatos](https://plato.stanford.edu/archives/fall2020/entries/lakatos/)：帮助理解一个家族何时仍然 progressive，何时已经 degenerating，需要升级到 audit 或 frame break。

<sub>英文 README 为规范版本。中文翻译仅用于提升可访问性，内容可能会略晚于英文更新。</sub>
