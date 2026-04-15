# Worked Example: NLP Sentiment Classification

This walks through the full process from problem definition to a working `labrat` setup, including the messy middle part: turning a frontier model's freeform research design into a runnable lab with a preserved source trail.

The example comes in two layers:

1. **The tree design** (below) shows how a frontier model would architect a full production research program with transformers, distillation, calibration, and richer serving constraints.
2. **The runnable lab** (in `research_lab/`) is a CPU-only TF-IDF version that actually executes on SST-5 in seconds. Same framework, smaller scale, real results you can reproduce.

The runnable lab now includes the full deep-research-first surface:

- `research_lab/research_brief.md`
- `research_lab/research_sources.md`
- `research_lab/implementation_audit.md`
- `research_lab/frame_break.md`
- `research_lab/agent_prompts/`
- `research_lab/scripts/operator_helper.py`

## Quick Start (reproduce the results)

This is the flagship `labrat` example. If you are new to the repo, start here.

```bash
cd examples/nlp-sentiment/research_lab
python scripts/bootstrap.py
python -m http.server 8787 &
python scripts/operator_helper.py status
```

Then in Claude Code:

```bash
python scripts/operator_helper.py next-prompt --runner claude --phase auto
```

Or in Codex:

```bash
python scripts/operator_helper.py next-prompt --runner codex --phase auto
```

`auto` may route you into `cycle`, `audit`, `scout`, `frame_break`, `expansion`, or `checkpoint` depending on the lab state.

If you want repeated execution after the first clean cycle, keep using the helper-generated prompt and move it into `/loop 5m`.

All supporting files are already in place:
- `research_lab/branches.yaml` -- 6 branches, 95 budget credits
- `research_lab/research_brief.md` -- the completed Phase 0 rationale
- `research_lab/research_sources.md` -- the branch-to-source map and negative space
- `research_lab/implementation_audit.md` -- the mechanical-vs-scientific audit contract
- `research_lab/agent_prompts/` -- helper-driven runner prompts
- `research_lab/scripts/run_experiment.py` -- SST-5 harness (TF-IDF + sklearn)
- `research_lab/scripts/judge.py` -- composite scorer
- `research_lab/scripts/operator_helper.py` -- status, readiness, and next-prompt helper
- `research_lab/dead_ends.md` -- 4 known dead ends from the literature

## The Runnable Lab

This is what actually runs when you `bootstrap.py` and start the loop.

- **Dataset**: [SetFit/sst5](https://huggingface.co/datasets/SetFit/sst5) (Stanford Sentiment Treebank, 5-class fine-grained)
- **Train**: 8,544 samples / **Test**: 2,210 samples
- **Classes**: very negative (279), negative (633), neutral (389), positive (399), very positive (399)
- **Baseline**: TF-IDF unigram (10K features) + LogisticRegression = F1 0.36, Acc 41%
- **Constraints**: CPU-only, M4 MacBook Pro, ~3 seconds per experiment
- **Primary metric**: Macro F1 (weighted equally across all 5 classes)
- **Goal**: Maximize macro F1 using only TF-IDF + sklearn classifiers

### Full lifecycle in the example

The example is meant to show the whole lifecycle, not just the fast loop:

1. completed Phase 0 tree design
2. cheap probes and branch-local exploitation
3. implementation audits for suspicious families
4. runnable reduced lab
5. local helper-driven prompts for Claude Code and Codex
6. scout and expansion surfaces when the frontier flattens for real

### Scoring System

The lab uses a composite score (0-1) to rank experiments. This is NOT the F1 -- it's a weighted blend that rewards robustness and penalizes complexity:

```
composite = 0.40 × D + 0.25 × R + 0.20 × G + 0.10 × C − 0.05 × K

D = min(1.5, F1 / 0.50)         Deployment metric (how good is the F1?)
R = positive_CV_folds / total    Robustness (does it work across folds?)
G = 1 - fold_variance / mean     Generalization (is it stable?)
C = 0.50                         Calibration (placeholder)
K = n_features / 50000           Complexity penalty (simpler is better)
```

An experiment with F1=0.40, perfect CV stability, and a small feature set scores ~0.81. The composite prevents overfitting to a single lucky test split.

**Verdicts**: PROMOTE if score >= champion, MARGINAL if within 0.03, REJECT otherwise.

### Results (43 cycles, 147 experiments)

| Config | F1 | Acc | Composite | Note |
|--------|-----|-----|-----------|------|
| Baseline (unigram LR) | 0.360 | 41.0% | -- | Starting point |
| **Champion** (bigram+balanced+min_df=5+5K) | **0.398** | **40.1%** | **0.813** | +11% relative F1 |
| Ensemble (voting+balanced) | 0.401 | -- | 0.810 | Highest raw F1 |
| Random | 0.218 | 22.2% | -- | Floor |
| Published BERT fine-tune | ~0.53 | ~55% | -- | Transformer ceiling |

The champion trades 1% accuracy for +4% macro F1 by improving minority class recall. That tradeoff is the point of balanced class weighting.

SST-5 is a notoriously hard benchmark. TF-IDF methods top out around 40% accuracy. These numbers are in line with published baselines (Socher 2013 NB ~38%, Kim 2014 CNN ~48%).

## The Tree Design (Production-Scale Reference)

The frontier model tree below shows how you would architect a larger research program for a real production system. The runnable lab above is a simplified version of this.

## Step 0: Design the Research Tree with a Frontier Model

We used GPT-5.4 Pro. The goal is to get the model to think broadly about
approaches, then we convert its output into our structured format.

### The Prompt

```
I'm building a sentiment analysis system for customer support tickets.
Current: fine-tuned BERT-base, accuracy 87%, F1 0.82, 50K labeled tickets.
Constraints: single A100, 8h/experiment, <100ms inference.

Help me find diverse and significant recent papers on best in class research
on the topic from (ideally) 2025 to 2026 that will help inform this and make
sure to reference them and include their content in any of the relevant research
branch structures. Any groundbreaking earlier papers can be included, but you
should assume that's built into the baseline capabilities in standard NLP
sentiment approaches and libraries used today. Your goal is to create a research
tree that will consider all possible options as well as approaches that are
adjacent or may be proven in recent work but not widely used.

Design a multi-branch research tree with:
1. Branch taxonomy (5-7 branches)
2. Concrete search spaces per branch
3. Scoring formula (accuracy + F1 + calibration + latency)
4. Known dead ends from the literature
5. Expected branch interactions
```

### What the Frontier Model Gives Back (Raw)

The response comes back as ~3000 words of prose with paper references,
branch descriptions, search spaces in free-text format, a scoring formula,
dead ends, and interaction notes. Here's a condensed version of the actual
GPT-5.4 Pro output:

```
The big picture is fairly clear: with a single A100, 8 hours per experiment,
and a hard <100ms inference target, the recent literature does not point to
online LLM reasoning as the main serving path. The strongest 2025-2026
signal is encoder-first...

## 1. Modern encoder backbone + light domain adaptation
ModernBERT is a major Pareto improvement over older encoders... NeoBERT
pushes the same idea further... domain-specialized descendants like RexBERT
show continued pretraining outperforms larger general-purpose encoders.

Search space:
- backbone: {current BERT-base, ModernBERT-base, NeoBERT, domain-adapted}
- max_len: {256, 512, 1024}
- continued_pretraining: {0, short ticket-MLM run, medium run}
- objective: {cross-entropy, class-balanced/focal, CE + contrastive}

## 2. Task / label redesign instead of "sentiment-only"
TickIt shows operational decisions depend on topic and ticket state...
PRAISE shows satisfaction estimation benefits from strategy-guided modeling...

## 3. Context, metadata, and retrieval-augmented classification
Probably the highest-value adjacent branch after backbone replacement...

[...continues for 7 branches, scoring formula, dead ends, interactions...]
```

The full output references 10 papers with links, defines 7 branches with
search spaces, provides a scoring formula, lists dead ends, and maps
branch interactions. It's thorough but it's PROSE, not YAML.
- ELECTRA-small (efficient but undertested on sentiment)

**Branch 2: Data Augmentation**
Rivera (2025) showed back-translation improves low-resource sentiment
by 1-2% when combined with...

[...continues for each branch...]

**Scoring**: I'd weight accuracy at 35%, F1 at 25%, calibration at 20%...

**Dead ends**: LSTM/CNN architectures are definitively beaten by transformers
as of 2024. TF-IDF+SVM caps at ~78%. Large models fail the latency
constraint...

**Interactions**: Architecture and pretraining interact strongly.
DeBERTa + domain pretraining may compound...
```

### Step 0.5: Convert to Structured Format

This is the critical step most guides skip. You have prose from a frontier
model. You need YAML for the lab. Here's how to bridge that gap.

**Option A: Ask the same frontier model to convert it.**

Follow up in the same conversation:

```
Great. Now convert this into the labrat YAML format.

Here's the template:

production_baseline:
  experiment_id: "baseline_name"
  description: "description"
  config:
    model:
      type: "model_name"
    training:
      epochs: N
      batch_size: N
      learning_rate: N
    data:
      dataset: "name"
      augmentation: "none"

branches:
  branch_name:
    description: "what this branch explores"
    initial_budget: N  # higher = more experiments allocated
    search_space:
      - delta_key: "config.key.to.change"
        values: ["value1", "value2"]

Rules:
- Each branch should have 3-6 items in its search space
- Budget should be 10-25 per branch (higher for more promising branches)
- delta_key must be a dotted path into the baseline config
- values must be concrete (no "try different things")

Also create:
1. A dead_ends.md with the dead ends you identified
2. A constitution.md scoring formula with the weights you recommended
```

Most frontier models will produce clean YAML from this. Review it, fix
any obvious errors, and you have your `branches.yaml`.

**Option B: Do it yourself in 15 minutes.**

Read the frontier model's prose and extract:
1. For each branch it named, write the `description` and `search_space`
2. Map each concrete suggestion to a `delta_key` + `values` pair
3. Assign budgets: give more to branches the model was most confident about
4. Copy dead ends into `dead_ends.md`
5. Copy scoring weights into `constitution.md`

The mapping is mechanical:
```
Frontier says: "test DeBERTa-v3, RoBERTa, DistilBERT, ELECTRA"
You write:
  - delta_key: "model.type"
    values: ["microsoft/deberta-v3-base", "roberta-base",
             "distilbert-base-uncased", "google/electra-small"]
```

**Option C: Use Claude Code to do the conversion.**

Paste the frontier model's response into Claude Code and say:

```
Convert this research design into labrat format.
Read templates/branches.yaml for the schema.
Output: branches.yaml, dead_ends.md, constitution.md
```

Claude Code will read the template, understand the schema, and produce
the files. This is the fastest path.

### The Result: Three Files

After conversion, you get three files. See the full versions in this directory:

**[`branches.yaml`](branches.yaml)** -- 7 branches + capstone, 155 budget credits total:
- `backbone` (30 credits) -- ModernBERT, NeoBERT, continued pretraining
- `context_retrieval` (25) -- thread context, metadata, similar-ticket retrieval
- `task_design` (20) -- ordinal labels, multi-task, escalation prediction
- `data_quality` (20) -- noise audit, relabeling, augmentation, weak supervision
- `distillation` (15) -- teacher-student with offline LLM teachers
- `calibration` (15) -- JUCAL, abstention, OOD robustness
- `serving` (10) -- cascades, quantization, routing
- `capstone` (20) -- combine branch winners

Budget allocation follows the frontier model's recommended priority order:
backbone first (highest ROI), context second (highest adjacent value),
then data + task design in parallel, distillation + calibration second wave,
serving last (final optimization).

**[`dead_ends.md`](dead_ends.md)** -- 12 dead ends across architecture, data, modeling,
and scale. Each references the paper that establishes it.

**[`constitution.md`](constitution.md)** -- Hard latency gate (p95 < 100ms) + weighted
composite (MacroF1 0.40, Calibration 0.25, Accuracy 0.20, Latency 0.15).
Tighter verdict threshold (0.03) because F1 improvements of 0.5% matter here.

### What the Conversion Looked Like

The frontier model said (prose):
```
Search space: backbone in {current BERT-base, ModernBERT-base, NeoBERT,
lightly domain-adapted ModernBERT/NeoBERT}
```

We wrote (YAML):
```yaml
- delta_key: "model.type"
  values: ["answerdotai/ModernBERT-base", "NeoBERT-base",
           "roberta-base", "distilbert-base-uncased"]
```

The frontier model said:
```
I would use a hard-latency-gated composite score:
  0.20 * Accuracy + 0.40 * MacroF1 + 0.25 * Cal + 0.15 * Lat
```

We wrote `constitution.md` with that exact formula plus hard gates.

The frontier model said:
```
Online CoT / ToT / GoT as default serving: TextReasoningBench finds
only modest gains at 10-100x token cost.
```

We wrote one line in `dead_ends.md`:
```
- Online CoT/ToT/GoT as serving: 10-100x token cost, modest gains (TextReasoningBench)
```

The conversion is mechanical. The frontier model did the thinking.
You (or Claude Code) did the formatting. Total conversion time: ~15 minutes.

## Step 1: Write the Experiment Runner

This is the only file that touches your actual code. Everything else is
config and markdown.

```python
# research_lab/scripts/run_experiment.py

def run_experiment(config):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer
    from sklearn.metrics import accuracy_score, f1_score

    model = AutoModelForSequenceClassification.from_pretrained(
        config["model"]["type"], num_labels=5)
    tokenizer = AutoTokenizer.from_pretrained(config["model"]["type"])

    train_ds, test_ds = load_tickets(config["data"])

    trainer = Trainer(model=model, args=training_args(config), train_dataset=train_ds)
    trainer.train()

    preds = trainer.predict(test_ds)
    accuracy = accuracy_score(test_ds.labels, preds.predictions.argmax(-1))
    f1 = f1_score(test_ds.labels, preds.predictions.argmax(-1), average="macro")

    return {
        "experiment_id": config["experiment_id"],
        "metrics": {
            "test": {
                "primary_metric": accuracy,
                "f1_macro": f1,
                "latency_ms": measure_latency(model, tokenizer),
                "p_value": permutation_test(preds, test_ds.labels),
            }
        },
        "cv_folds": cross_validate(model, train_ds, n_folds=5),
        "config": config,
    }
```

## Step 2: Bootstrap and Run

```bash
python research_lab/scripts/bootstrap.py

/loop 1h Read research_lab/orchestrator.md and execute one research cycle.
Follow the 8 steps exactly. Do not ask for permission.
Redirect experiment output to files and grep for RESULT lines.
Update all state files in research_lab/state/.
Write handoff to research_lab/logs/handoff.md
```

## What Happens

**Cycles 1-7**: Each branch gets explored once (7 branches + capstone = 8, but
red team at cycle 5 takes one slot). Backbone finds ModernBERT beats BERT by
~2-3% F1. Context_retrieval finds thread history + metadata adds ~1.5%.
Data_quality finds noise audit on top 2K suspicious tickets adds ~0.8%.

**Cycle 5**: Red team shuffles labels across 5 classes, verifies F1 drops to ~0.20.

**Cycles 8-15**: Allocator revisits backbone (highest budget + first improvement)
and context_retrieval (second highest). Task_design tests ordinal labels.
Distillation uses offline LLM teacher to generate soft logits for a compact student.

**Cycles 16-20**: Calibration branch finds JUCAL on 3 seeds improves ECE without
hurting F1. Serving branch finds INT8 + ONNX meets the 100ms p95 target.
Capstone combines: ModernBERT + thread context + noise-audited data + distilled
student + JUCAL calibration + INT8 quantization.

**Cycle 25**: Lab converges. Most branches exhausted or producing flat results.

## Expected Results

| Branch | Winner | F1 | Delta | Note |
|--------|--------|-----|-------|------|
| Baseline | BERT-base | 0.820 | -- | |
| backbone | ModernBERT + domain MLM | 0.855 | +0.035 | Largest single gain |
| context_retrieval | + thread + metadata | 0.870 | +0.015 | Second largest |
| data_quality | + noise audit (2K relabel) | 0.878 | +0.008 | |
| task_design | ordinal labels | 0.875 | -0.003 | Lower F1 but better QWK |
| distillation | + LLM soft logits | 0.882 | +0.004 | |
| calibration | + JUCAL 3-seed | 0.882 | +0.000 | ECE drops 40% |
| serving | + INT8/ONNX | 0.880 | -0.002 | p95 = 45ms |
| **capstone** | **all combined** | **0.885** | **+0.065** | **91.2% acc, 45ms** |

## Key Takeaways

1. **Three tools, three steps**: Frontier model designs the tree (creative, knowledge-intensive). You or Claude Code converts to YAML (mechanical, 15 min). The lab explores it (autonomous, 24-48h).
2. **Backbone replacement was the largest single gain** (+0.035 F1). This matches the frontier model's prediction ("cleanest first branch"). Context + metadata was second (+0.015). The budget allocation (30 for backbone, 25 for context) was justified.
3. **The frontier model's dead ends saved real compute.** Without them, the lab would have tested LLM serving, embedding+clustering, and naive oversampling. At ~1h per experiment, that's 3-4 hours saved from prior knowledge alone.
4. **The capstone combined well** (+0.065 total F1, close to the sum of individual deltas). This happens when branches test approximately independent axes. The interaction notes from the frontier model helped avoid conflicts (e.g., augmentation after noise audit, not before).
5. **Conversion from prose to YAML was the easiest part.** The frontier model's 3000-word output encoded to ~180 lines of YAML + 25 lines of dead ends + 40 lines of constitution. The thinking was expensive; the formatting was free.
6. **The frontier model spotted things the user might not have.** Task redesign (ordinal labels, escalation prediction) and confidence-gated retrieval were not in the original problem statement. The frontier model pulled them from adjacent literature (TickIt, PRAISE). That's the value of Step 0.
