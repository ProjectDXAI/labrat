# Labrat Deep Assessment: Failure Points, Gaps, and Opportunities

**Date**: 2026-03-31
**Scope**: Full architecture review of labrat, informed by the BTC microstructure research program (55 cycles, 47 experiments across v1-v3), the NLP-sentiment example (43 cycles, 147 experiments), and patterns from the Claude Code harness (nirholas/claude-code, ~512K lines TypeScript).

---

## 1. Hypothesis Discovery is Static (The Biggest Problem)

The single largest limitation: **labrat can only explore what's been pre-defined in branches.yaml**. It cannot discover genuinely new research directions autonomously.

**Evidence:**
- BTC `branches.yaml` (259 lines) has fixed `search_space` entries with explicit values
- `batch_runner.py` hardcodes all 60+ experiments in `EXPERIMENT_QUEUE` at line 38
- The "research scout" (`batch_runner.py` lines 444-470) is a stub -- it writes a JSON brief but never actually searches or generates new configs
- v3 "convergence" at cycle 11 was really just exhausting the predefined search space, not hitting a fundamental limit

**What Claude Code's harness gets right here**: It uses the LLM's reasoning to dynamically generate tool calls and change strategy mid-task. Labrat treats the LLM as a cycle executor, not a hypothesis generator.

**Opportunities:**
- Research scout should actually use WebSearch to find papers, then propose new branch entries
- After every N cycles of convergence, have the LLM reason about "what would a domain expert try next?" and generate new branches.yaml entries
- Support "emergent branches" -- the agent proposes a new axis based on patterns in experiment results (e.g., "I notice all promoted experiments have low complexity. Should I test an explicit simplicity-first branch?")
- Use LLM-generated counterfactuals: "What would have to be true for the current dead ends to work?"

---

## 2. Memory is Complete but Not Intelligent

State is well-structured and git-trackable, but there's no semantic compression or retrieval. The orchestrator reads ALL state every cycle.

**Evidence:**
- Read order (`orchestrator.md` lines 69-77) loads 7 files every cycle regardless of need
- `experiment_log.jsonl` grows unboundedly (147 entries in NLP example, would be 1000s for a real research program)
- `branch_beliefs.json` tracks numbers (n_experiments, EV, uncertainty) but loses the WHY
- No summarization happens between cycles -- cycle 43 reads the same volume as cycle 1
- `dead_ends.md` is static prose, not queryable or filterable

**Opportunities:**
- **Progressive summarization**: After every 10 cycles, compress experiment_log.jsonl into a branch-level summary ("Model branch: SVM wins, all tree models lose on sparse TF-IDF. 5 experiments, 2 promoted, 3 rejected.")
- **Semantic dead-end matching**: Right now dead end detection is string matching against experiment_log.jsonl. Should be embedding-based -- "is this new experiment semantically similar to a known dead end?"
- **Context budgeting**: Read the full state on cycle 0, then only read diffs/summaries on subsequent cycles. The orchestrator doesn't need to know the details of cycle 3 when running cycle 43.
- **Insight extraction**: Add a `finding` field per experiment that captures what was LEARNED, not just metrics. The BTC v3 delay audit (cycle 9) was the most valuable experiment but it has no composite_score.

---

## 3. Stuck Detection is Too Simplistic

`check_stuck_branches()` (`batch_runner.py` lines 422-441) checks if the last 3 experiments are non-PROMOTE. This misses several important failure modes.

**Evidence:**
- BTC v1: model branch waited 17 cycles before being explored (`FINDINGS.md` line 215)
- The recency_bonus (0.3 weight) wasn't strong enough to force exploration
- No detection of "diminishing returns" -- if last 5 improvements are all < 0.005 composite delta, the branch is effectively converged but won't be detected
- No detection of "circular exploration" -- testing depth=8 after depth=4 and depth=6 were identical (found identical results, wasted 2 experiments)
- No detection of "adversarial PROMOTE" -- where experiments promote because champion_score is low, not because they're actually good

**Opportunities:**
- Track improvement **magnitude**, not just PROMOTE/REJECT. `delta < epsilon` for N consecutive experiments = converged
- Implement a **diversity score**: prefer experiments maximally different from all past experiments in the same branch (not just single-delta from champion)
- Add **semantic dedup**: before running an experiment, check if a functionally equivalent config has been tested. depth=4/6/8 all identical should have been caught after depth=6
- **Automatic convergence detection** per-axis within a branch, not just per-branch

---

## 4. Experiment Type Rigidity

Labrat assumes all experiments follow the same pattern: config -> run -> metrics -> judge. The BTC run showed this breaks for several critical experiment types.

**Evidence:**
- BTC v3 execution branch had "phantom" experiments scored as `DIAGNOSTIC`, not PROMOTE/REJECT
- The delay audit (cycle 9) was a meta-experiment that changed the interpretation of ALL previous results
- The retrain experiment (cycle 6) was a completely different pipeline than standard config changes
- These experiments were the most valuable in the entire research program, but the framework doesn't have first-class support for them

**Opportunities:**
- First-class **diagnostic experiments** that inform future experiments without being scored
- **Meta-experiments** that re-evaluate previous results (delay audit should have triggered automatic re-scoring of cycles 3-8)
- **Experiment invalidation**: when a finding changes the scoring rubric, retroactively update verdicts
- **Experiment chains**: "run A; if A passes, run B with A's output as input"
- **Per-branch scoring rubrics**: execution branch should score on Sharpe@50ms, not IC

---

## 5. The Batch Runner / Orchestrator Split

Two execution modes that don't share logic.

**Evidence:**
- `batch_runner.py` hardcodes `EXPERIMENT_QUEUE` while orchestrator generates dynamically
- batch_runner doesn't use the allocator priority formula (lines 522-529 just pops from queue with budget check)
- batch_runner picks up to 4 experiments per cycle without consulting `branch_beliefs`
- The NLP example's 147 experiments were run through batch_runner, skipping intelligent allocation entirely

**Opportunities:**
- Extract the allocator into a shared Python module used by both modes
- Make batch_runner generate experiments using the same logic as the orchestrator (read branches.yaml, apply UCB1 priority, respect dead_ends)
- Support hybrid mode: batch_runner for the mechanical sweep, orchestrator picks up where batch_runner's predefined experiments end
- The batch_runner should be the "fast path" for deterministic experiments; the orchestrator should be the "creative path" for hypothesis-driven exploration

---

## 6. The Scoring Formula Has Dead Components

**Evidence** (`FINDINGS.md` lines 199-226, confirmed by reading `judge.py`):
- `C` (calibration) is hardcoded to 0.5 at `judge.py` line 57 -- always contributes 0.05 to every score, adds no discrimination
- `I` (information gain) mentioned in `ARCHITECTURE.md` but not implemented in `judge.py` at all
- The `K` (complexity) metric in the NLP judge is just `n_features / 50000` (line 60) -- a proxy at best, misleading at worst (50K features scored as "maximally complex" even if the model is trivial)
- Red team in batch_runner uses deterministic seeds: `42 + cycle` (line 501). Not truly independent.

**Opportunities:**
- Implement proper calibration: compare predicted probabilities vs actual outcomes
- Implement information gain: track whether each new experiment's predictions are actually different from champion's (avoid promoting "same model, different config")
- Use effect size (Cohen's d or similar) not just composite score for PROMOTE decisions
- Add confidence intervals to composite scores so marginal promotes are flagged
- Diversify red team methodology: vary seeds, vary test data splits, use bootstrap

---

## 7. No Cross-Lab Knowledge Transfer

Each lab is isolated. Findings from one lab don't transfer to another.

**Evidence:**
- BTC v1/v2/v3 were manually chained: v2's `branches.yaml` hardcodes v1 findings in comments (lines 1-12)
- The "12 book features are enough" finding was manually propagated
- NLP example has no way to inform a hypothetical second NLP lab
- No mechanism to share dead_ends across related labs

**Opportunities:**
- **Lab registry**: a meta-state file tracking all labs, their domains, and key findings
- **Lab inheritance**: new labs auto-inherit dead_ends and champion configs from parent labs
- **Lab forking**: a converged lab spawns sub-labs for specific follow-ups
- **Cross-domain transfer**: findings about scoring formula improvements in lab A automatically apply to lab B

---

## 8. No Belief Revision or Experiment Invalidation

When the agent discovers something that changes the research frame, there's no mechanism to act on it.

**Evidence (the most striking example):**
- BTC cycle 9 discovered phantom delay data has no sub-second resolution, meaning ALL phantom Sharpe numbers from cycles 3-8 were measuring the wrong thing
- The experiment log still contains the original (wrong) numbers
- No automatic re-evaluation was triggered
- The handoff mentions the correction but doesn't update previous verdicts

**Opportunities:**
- **Retroactive re-scoring**: when a finding changes the scoring rubric (like delay discovery), automatically re-judge all affected experiments
- **Belief chain**: track which findings depend on which assumptions. If assumption X is invalidated, flag all downstream findings
- **"What changed" alerts**: highlight when a new experiment's findings conflict with established beliefs (signal for the agent to investigate)

---

## 9. Single-Delta Constraint is Too Rigid for Combinatorics

**Evidence:**
- Capstone branch in NLP had to manually enumerate 30+ combinations in batch_runner
- BTC `branches.yaml` manually defines each capstone config (lines 91-133)
- Cycle 9 in NLP found "branch winners NOT additive" -- the most important finding about combinatorics was accidental
- No systematic way to detect interactions between branch axes

**Opportunities:**
- Support a **multi-delta mode** for capstone/interaction branches
- After branches converge individually, auto-generate a **2^N factorial design** testing all branch-winner combinations
- Use **fractional factorial** or **Latin hypercube** for large combinatorial spaces
- Track interaction effects explicitly: "bigrams help, balanced helps, but bigrams+balanced is WORSE than either alone"

---

## 10. Autonomy Boundaries Are Binary

The agent either has full autonomy or asks on cycle 0 and never again.

**Evidence:**
- Orchestrator asks about parallelism/interval on cycle 0, then runs indefinitely
- v3 BTC lab needed human judgment at multiple points (should we retrain? should we change the scoring metric? should we deploy?)
- No mechanism for the agent to say "I found something surprising -- should I change the research question?"
- No "pause and report" trigger for high-value findings

**Opportunities:**
- **Surprise detection**: if an experiment result is >3 sigma from expected, or if a PROMOTE candidate beats champion by >2x historical delta, flag for human review
- **Autonomy levels per branch**: some branches need human approval for PROMOTE, others are fully autonomous
- **Research pivot proposals**: the agent can propose adding new branches or changing the mission
- **Periodic human checkpoints**: every N cycles, produce a report and wait for human input before continuing

---

## 11. Subagent Failure Modes

The parallel execution model is clean but has no resilience.

**Evidence:**
- Orchestrator blocks on ALL subagents finishing before updating state
- No per-subagent timeout in `orchestrator.md`
- If one branch's experiment hangs (e.g., GPU OOM, infinite loop), the entire cycle stalls
- No health check or heartbeat mechanism
- `active_agents.json` is write-once-read-once -- if the orchestrator crashes mid-cycle, agents appear forever "running"

**Opportunities:**
- Per-subagent timeouts (configurable per branch based on expected experiment duration)
- Partial cycle completion: process finished agents, don't wait for stragglers
- Agent heartbeat: subagents write progress to a file every 30s, orchestrator can detect stalls
- Crash recovery: on startup, check for orphaned agent entries and clean up
- "Streaming" cycles: as soon as one experiment finishes, start the next branch exploration without waiting for the full batch

---

## 12. Dashboard Is View-Only

**Evidence:**
- No ability to pause/resume/skip branches from dashboard
- No way to inject new experiments
- No alerting on PROMOTE, convergence, or failures
- 30s polling refresh, no WebSocket

**Opportunities:**
- Basic controls: pause branch, skip experiment, add budget
- Notification hooks: Slack/email on PROMOTE, convergence, stuck detection
- "Research timeline" view showing the full experiment tree with links between parents and children
- Export findings as structured report (PDF, Notion page)

---

## 13. Provenance Gaps

**Evidence:**
- `experiment_log.jsonl` stores delta descriptions as free-text strings, not formal diffs
- No formal parent_id linking experiments to their parent configs
- Can't reproduce an exact experiment from the log alone (need the full config)
- batch_runner generates configs in memory, writes them to disk, but the generation logic isn't logged
- No environment tracking (Python version, package versions, hardware)

**Opportunities:**
- Store full config hash in experiment_log.jsonl
- Add explicit `parent_id` field for every experiment
- Add `--reproduce <experiment_id>` command that re-runs any experiment from its log entry
- Track environment fingerprint per experiment

---

## 14. The "Right Research Question" Problem

The most fundamental gap: labrat optimizes within a fixed research frame, but the BTC research program showed that the biggest wins came from changing the frame.

**Evidence:**
- v1 lab optimized IC and Sharpe@0ms. But the real metric was Sharpe@50ms (discovered in v3 cycle 7)
- The delay audit (cycle 9) was worth more than all 27 v1 experiments combined
- The finding "model is stale for Mar 2026" (cycle 4) invalidated the entire frozen-model approach
- None of these frame-changing discoveries were things labrat was designed to find

**This is the fundamental tension:** labrat excels at systematic exploration within a defined space, but the highest-value research happens when you realize you're in the wrong space.

**Opportunities:**
- After convergence, run a "frame challenge" cycle where the agent explicitly tries to falsify the mission statement
- Periodically ask: "Are we measuring the right thing?" as a first-class operation
- Support "meta-branches" that don't test configs but test assumptions (e.g., "does the scoring metric correlate with actual trading PnL?")
- Track the ratio of "frame-changing discoveries" vs "incremental improvements" as a health metric

---

## Patterns from the Claude Code Harness That Labrat Should Adopt

The Claude Code repo (nirholas/claude-code) is a ~512K line TypeScript codebase. Several of its patterns map directly onto labrat's gaps.

### 15. Graduated Compaction

Claude Code has **four levels** of context management, activated in order of increasing cost:

1. Session memory compact (reuse existing extractions -- free)
2. Microcompact (trim tokens before API call -- cheap)
3. Full compact (API summarization -- expensive)
4. Reactive compact (emergency, triggered by errors -- last resort)

**Labrat equivalent**: Right now, the orchestrator reads ALL state every cycle, with no compression strategy. Should have:
- Level 0: Read only `handoff.md` (last cycle summary) -- sufficient for 90% of cycles
- Level 1: Read handoff + branch_beliefs (for allocation decisions)
- Level 2: Read full state (only when needed for convergence detection or red team)
- Level 3: Read experiment_log.jsonl (only for stuck detection or research scout)

This alone would cut context consumption by 60-80% on most cycles.

### 16. Diminishing Returns Detection

Claude Code tracks delta tokens between continuations. If 3+ continuations each produce <500 new tokens, it stops -- the model is spinning.

**Labrat equivalent**: Track `composite_score_delta` per experiment. If the last N experiments across ALL branches produce delta < 0.005, the lab is effectively converged even if individual branches haven't hit the 3-consecutive-REJECT threshold. This catches the subtle "improving but not meaningfully" failure mode that the current stuck detection misses entirely.

### 17. The Coordinator's Synthesis Requirement

Claude Code's coordinator mode has an explicit rule: **the coordinator must understand findings before delegating follow-up work**. The phrase "based on your findings" is banned -- the coordinator must synthesize, not relay.

**Labrat equivalent**: The orchestrator currently launches subagents, collects RESULT/VERDICT lines, and updates state mechanically. It never synthesizes. After collecting results, add a **synthesis step**: "Given these N experiment results, what did we learn? Does this change our beliefs about which branches to explore next? Should we propose new hypotheses?"

This is the missing link between "config sweeper" and "research agent."

### 18. Forked Subagents with Restricted Tool Access

Claude Code spawns background agents (for memory extraction, auto-dream) with explicitly restricted tool sets. Dream agents get read-only bash. Session memory agents can't write code.

**Labrat equivalent**: Research scouts should be spawned with WebSearch/WebFetch access but NO write access to state files. Experiment runners should have write access to their own experiment directory but NOT to `state/` files. The orchestrator is the only agent that modifies shared state. This prevents a rogue subagent from corrupting the research program.

### 19. Auto-Dream: Background Memory Consolidation

Claude Code runs a "dream" agent on a 24h cycle that reviews past session transcripts and distills them into memory files. Time-gated (24h) + session-gated (5+ sessions) + lock-protected.

**Labrat equivalent**: After every 10 cycles (or at convergence), spawn a "consolidation agent" that:
- Reviews the full experiment_log.jsonl
- Updates FINDINGS.md with new scaling curves and dead ends
- Proposes updates to branches.yaml (new search space entries based on patterns)
- Writes a "research digest" summarizing the state of knowledge

This is the mechanism for turning raw experiment results into structured research knowledge -- the gap between labrat's mechanical state files and actual scientific understanding.

### 20. Explicit Transition Types in the Query Loop

Claude Code names every continuation and termination reason: `tool_use`, `blocking_limit`, `model_error`, `max_turns`, `diminishing_returns`, etc. Each is logged and handled separately.

**Labrat equivalent**: Right now a cycle ends with either "experiments done" or "converged." Should have explicit transition types:
- `experiments_complete` -- normal cycle end
- `budget_exhausted` -- all branches at 0
- `convergence` -- no branch can improve
- `surprise_detected` -- experiment result >3 sigma from expected
- `frame_invalidation` -- a finding changes the scoring rubric
- `human_checkpoint` -- periodic pause for review
- `stuck_all_branches` -- every active branch is stuck
- `new_hypothesis_proposed` -- agent wants to add a branch

This makes the research program's behavior auditable and debuggable.

---

## Priority Ranking

| Rank | Change | Category | Effort | Payoff |
|------|--------|----------|--------|--------|
| 1 | Dynamic hypothesis generation from LLM reasoning | Discovery | High | Transforms the tool |
| 2 | Belief revision / experiment invalidation | Correctness | Medium | Prevents wrong conclusions |
| 3 | Graduated context reading (handoff-first) | Efficiency | Low | 60-80% context savings |
| 4 | Synthesis step after result collection | Intelligence | Low | Bridges sweeper-to-researcher gap |
| 5 | Cross-lab knowledge transfer | Scale | High | Compounds across programs |
| 6 | Experiment type flexibility (diagnostic, meta, chain) | Coverage | Medium | Captures highest-value research |
| 7 | Diminishing returns detection | Stuck avoidance | Low | Catches subtle convergence |
| 8 | Consolidation agent (auto-dream equivalent) | Memory | Medium | Turns data into knowledge |
| 9 | Per-branch scoring rubrics | Correctness | Medium | Prevents optimizing wrong metric |
| 10 | Restricted subagent tool access | Safety | Low | Prevents state corruption |

The low-effort / high-payoff sweet spot is items **3, 4, and 7** -- graduated context, synthesis step, and diminishing returns detection. These three changes together would make the next labrat run meaningfully more autonomous without requiring architectural rewrites.
