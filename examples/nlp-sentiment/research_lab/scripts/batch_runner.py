#!/usr/bin/env python3
"""Batch experiment runner for labrat lab.

Generates experiment configs, runs them, judges them, updates state.
Designed to burn through many cycles autonomously.

Usage:
    python research_lab/scripts/batch_runner.py --cycles 30
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
STATE = LAB / "state"
SCRIPTS = LAB / "scripts"

# Production baseline config
BASELINE = {
    "features": {
        "ngram_min": 1, "ngram_max": 1, "max_features": 10000,
        "sublinear_tf": True, "analyzer": "word", "min_df": 2, "max_df": 0.95,
    },
    "preprocessing": {"lowercase": True, "stop_words": False},
    "model": {"type": "logistic", "params": {"C": 1.0, "max_iter": 1000}},
}

# Experiment queue: (branch, experiment_id, description, config_overrides)
# These are all the combinations worth testing
EXPERIMENT_QUEUE = [
    # === CAPSTONE: cross-branch combinations ===
    ("capstone", "capstone_bigram_svm_bal_stop_c13", "bigrams+SVM+balanced+stopwords",
     {"features.ngram_max": 2, "model.type": "svm", "model.params.C": 1.0,
      "model.params.max_iter": 2000, "model.params.class_weight": "balanced",
      "preprocessing.stop_words": True}),
    ("capstone", "capstone_bigram_bal_5k_c14", "bigrams+balanced+5K features",
     {"features.ngram_max": 2, "features.max_features": 5000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_bigram_bal_20k_c15", "bigrams+balanced+20K features",
     {"features.ngram_max": 2, "features.max_features": 20000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_svm_bal_nostop_c16", "SVM+balanced (no bigrams, no stopwords)",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_bigram_svm_c17", "bigrams+SVM (no balanced, no stopwords)",
     {"features.ngram_max": 2, "model.type": "svm",
      "model.params.C": 1.0, "model.params.max_iter": 2000}),
    ("capstone", "capstone_bigram_stop_c18", "bigrams+stopwords (no balanced, no SVM)",
     {"features.ngram_max": 2, "preprocessing.stop_words": True}),
    ("capstone", "capstone_bal_stop_c19", "balanced+stopwords (no bigrams, no SVM)",
     {"model.params.class_weight": "balanced", "preprocessing.stop_words": True}),
    ("capstone", "capstone_bigram_bal_mindf5_c20", "bigrams+balanced+min_df=5",
     {"features.ngram_max": 2, "features.min_df": 5,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_trigram_bal_c21", "trigrams+balanced",
     {"features.ngram_max": 3, "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_bigram_svm_bal_5k_c22", "bigrams+SVM+balanced+5K",
     {"features.ngram_max": 2, "features.max_features": 5000, "model.type": "svm",
      "model.params.C": 1.0, "model.params.max_iter": 2000,
      "model.params.class_weight": "balanced"}),

    # === FEATURES: interactions with other branch winners ===
    ("features", "features_bigram_stop_c13", "bigrams+stopwords",
     {"features.ngram_max": 2, "preprocessing.stop_words": True}),
    ("features", "features_bigram_5k_c14", "bigrams+5K features",
     {"features.ngram_max": 2, "features.max_features": 5000}),
    ("features", "features_bigram_mindf5_c15", "bigrams+min_df=5",
     {"features.ngram_max": 2, "features.min_df": 5}),
    ("features", "features_5k_c16", "5K features (unigram)",
     {"features.max_features": 5000}),
    ("features", "features_50k_c17", "50K features (unigram)",
     {"features.max_features": 50000}),

    # === MODEL: interactions ===
    ("model", "model_svm_bal_c13", "SVM+balanced",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "model.params.class_weight": "balanced"}),
    ("model", "model_svm_bigram_c14", "SVM+bigrams",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "features.ngram_max": 2}),
    ("model", "model_svm_stop_c15", "SVM+stopwords",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "preprocessing.stop_words": True}),
    ("model", "model_catboost_bal_c16", "CatBoost+balanced",
     {"model.type": "catboost", "model.params.iterations": 500,
      "model.params.depth": 6, "model.params.learning_rate": 0.1,
      "model.params.auto_class_weights": "Balanced"}),
    ("model", "model_rf_bal_c17", "RandomForest+balanced",
     {"model.type": "random_forest", "model.params.n_estimators": 300,
      "model.params.class_weight": "balanced"}),

    # === PREPROCESSING: interactions ===
    ("preprocessing", "preprocessing_stop_bigram_c13", "stopwords+bigrams",
     {"preprocessing.stop_words": True, "features.ngram_max": 2}),
    ("preprocessing", "preprocessing_stop_mindf10_c14", "stopwords+min_df=10",
     {"preprocessing.stop_words": True, "features.min_df": 10}),
    ("preprocessing", "preprocessing_stop_5k_c15", "stopwords+5K features",
     {"preprocessing.stop_words": True, "features.max_features": 5000}),

    # === OBJECTIVES: interactions ===
    ("objectives", "objectives_bal_bigram_c13", "balanced+bigrams",
     {"model.params.class_weight": "balanced", "features.ngram_max": 2}),
    ("objectives", "objectives_bal_stop_c14", "balanced+stopwords",
     {"model.params.class_weight": "balanced", "preprocessing.stop_words": True}),
    ("objectives", "objectives_bal_svm_c15", "balanced+SVM",
     {"model.params.class_weight": "balanced", "model.type": "svm",
      "model.params.C": 1.0, "model.params.max_iter": 2000}),
    ("objectives", "objectives_bal_bigram_stop_c16", "balanced+bigrams+stopwords",
     {"model.params.class_weight": "balanced", "features.ngram_max": 2,
      "preprocessing.stop_words": True}),
    ("objectives", "objectives_bal_svm_bigram_c17", "balanced+SVM+bigrams",
     {"model.params.class_weight": "balanced", "model.type": "svm",
      "model.params.C": 1.0, "model.params.max_iter": 2000,
      "features.ngram_max": 2}),

    # === ENSEMBLE: now supported ===
    ("ensemble", "ensemble_voting_soft_c23", "soft voting: LR+SVM+LR(C=0.5)",
     {"model.type": "voting_soft"}),
    ("ensemble", "ensemble_stacking_c24", "stacking: LR+SVM -> LR meta",
     {"model.type": "stacking"}),
    ("ensemble", "ensemble_voting_bal_c25", "soft voting+balanced",
     {"model.type": "voting_soft", "model.params.class_weight": "balanced"}),
    ("ensemble", "ensemble_stacking_bal_c26", "stacking+balanced",
     {"model.type": "stacking", "model.params.class_weight": "balanced"}),
    ("ensemble", "ensemble_voting_bigram_c27", "soft voting+bigrams",
     {"model.type": "voting_soft", "features.ngram_max": 2}),
    ("ensemble", "ensemble_stacking_bigram_c28", "stacking+bigrams",
     {"model.type": "stacking", "features.ngram_max": 2}),
    ("ensemble", "ensemble_voting_bal_bigram_c29", "voting+balanced+bigrams",
     {"model.type": "voting_soft", "model.params.class_weight": "balanced",
      "features.ngram_max": 2}),
    ("ensemble", "ensemble_stacking_bal_bigram_c30", "stacking+balanced+bigrams",
     {"model.type": "stacking", "model.params.class_weight": "balanced",
      "features.ngram_max": 2}),
    ("ensemble", "ensemble_voting_bal_bigram_mindf5_c31", "voting+balanced+bigrams+min_df=5",
     {"model.type": "voting_soft", "model.params.class_weight": "balanced",
      "features.ngram_max": 2, "features.min_df": 5}),
    ("ensemble", "ensemble_stacking_bal_bigram_mindf5_c32", "stacking+balanced+bigrams+min_df=5",
     {"model.type": "stacking", "model.params.class_weight": "balanced",
      "features.ngram_max": 2, "features.min_df": 5}),

    # === WAVE 2: Exploit new champion (bigram+balanced+min_df=5) ===
    # Vary around the champion config
    ("capstone", "capstone_champ_stop_c23", "champion+stopwords",
     {"features.ngram_max": 2, "features.min_df": 5,
      "model.params.class_weight": "balanced", "preprocessing.stop_words": True}),
    ("capstone", "capstone_champ_svm_c24", "champion+SVM",
     {"features.ngram_max": 2, "features.min_df": 5,
      "model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_5k_c25", "champion but 5K features",
     {"features.ngram_max": 2, "features.min_df": 5, "features.max_features": 5000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_20k_c26", "champion but 20K features",
     {"features.ngram_max": 2, "features.min_df": 5, "features.max_features": 20000,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_C05_c27", "champion with C=0.5",
     {"features.ngram_max": 2, "features.min_df": 5,
      "model.params.class_weight": "balanced", "model.params.C": 0.5}),
    ("capstone", "capstone_champ_C2_c28", "champion with C=2.0",
     {"features.ngram_max": 2, "features.min_df": 5,
      "model.params.class_weight": "balanced", "model.params.C": 2.0}),
    ("capstone", "capstone_champ_mindf3_c29", "champion but min_df=3",
     {"features.ngram_max": 2, "features.min_df": 3,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_mindf10_c30", "champion but min_df=10",
     {"features.ngram_max": 2, "features.min_df": 10,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_trigram_c31", "champion but trigrams",
     {"features.ngram_max": 3, "features.min_df": 5,
      "model.params.class_weight": "balanced"}),
    ("capstone", "capstone_champ_maxdf80_c32", "champion+max_df=0.80",
     {"features.ngram_max": 2, "features.min_df": 5, "features.max_df": 0.80,
      "model.params.class_weight": "balanced"}),

    # === WAVE 2: More feature experiments ===
    ("features", "features_bigram_5k_mindf5_c18", "bigrams+5K+min_df=5",
     {"features.ngram_max": 2, "features.max_features": 5000, "features.min_df": 5}),
    ("features", "features_bigram_20k_c19", "bigrams+20K features",
     {"features.ngram_max": 2, "features.max_features": 20000}),
    ("features", "features_bigram_maxdf80_c20", "bigrams+max_df=0.80",
     {"features.ngram_max": 2, "features.max_df": 0.80}),

    # === WAVE 2: More model experiments ===
    ("model", "model_svm_bigram_bal_c18", "SVM+bigrams+balanced",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "model.params.class_weight": "balanced", "features.ngram_max": 2}),
    ("model", "model_svm_bigram_stop_c19", "SVM+bigrams+stopwords",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "features.ngram_max": 2, "preprocessing.stop_words": True}),
    ("model", "model_svm_5k_c20", "SVM+5K features",
     {"model.type": "svm", "model.params.C": 1.0, "model.params.max_iter": 2000,
      "features.max_features": 5000}),

    # === WAVE 2: More preprocessing ===
    ("preprocessing", "preprocessing_stop_bigram_5k_c16", "stopwords+bigrams+5K",
     {"preprocessing.stop_words": True, "features.ngram_max": 2,
      "features.max_features": 5000}),
    ("preprocessing", "preprocessing_stop_bigram_mindf5_c17", "stopwords+bigrams+min_df=5",
     {"preprocessing.stop_words": True, "features.ngram_max": 2, "features.min_df": 5}),

    # === WAVE 2: More objectives ===
    ("objectives", "objectives_bal_bigram_mindf5_c18", "balanced+bigrams+min_df=5",
     {"model.params.class_weight": "balanced", "features.ngram_max": 2,
      "features.min_df": 5}),
    ("objectives", "objectives_bal_bigram_5k_c19", "balanced+bigrams+5K",
     {"model.params.class_weight": "balanced", "features.ngram_max": 2,
      "features.max_features": 5000}),
    ("objectives", "objectives_bal_stop_5k_c20", "balanced+stopwords+5K",
     {"model.params.class_weight": "balanced", "preprocessing.stop_words": True,
      "features.max_features": 5000}),
    ("objectives", "objectives_bal_svm_stop_c21", "balanced+SVM+stopwords",
     {"model.params.class_weight": "balanced", "model.type": "svm",
      "model.params.C": 1.0, "model.params.max_iter": 2000,
      "preprocessing.stop_words": True}),
]


def build_config(branch: str, exp_id: str, desc: str, overrides: dict) -> dict:
    """Build a full config from baseline + overrides."""
    config = copy.deepcopy(BASELINE)
    config["experiment_id"] = exp_id
    config["branch"] = branch
    config["delta"] = desc

    for key, val in overrides.items():
        parts = key.split(".")
        d = config
        for p in parts[:-1]:
            if p not in d:
                d[p] = {}
            d = d[p]
        d[parts[-1]] = val

    return config


def run_experiment(config: dict, exp_dir: Path) -> dict | None:
    """Run one experiment. Returns result dict or None on failure."""
    import yaml
    exp_dir.mkdir(parents=True, exist_ok=True)
    config_path = exp_dir / "config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    log_path = exp_dir / "run.log"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "run_experiment.py"),
         "--config", str(config_path), "--output-dir", str(exp_dir)],
        capture_output=True, text=True, timeout=600,
    )
    log_path.write_text(result.stdout + result.stderr)

    result_path = exp_dir / "result.json"
    if not result_path.exists():
        return None
    with open(result_path) as f:
        return json.load(f)


def judge_experiment(exp_dir: Path, branch: str) -> dict | None:
    """Score an experiment. Returns verdict dict."""
    result_path = exp_dir / "result.json"
    if not result_path.exists():
        return None

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "judge.py"),
         "--result", str(result_path),
         "--champion", str(STATE / "champions.json"),
         "--branch", branch],
        capture_output=True, text=True,
    )

    verdict_path = exp_dir / "verdict.json"
    if verdict_path.exists():
        with open(verdict_path) as f:
            return json.load(f)
    return None


def update_state(cycle: int, branch: str, exp_id: str, desc: str,
                 result: dict, verdict: dict):
    """Update all state files for one experiment."""
    now = datetime.now(UTC).isoformat()

    # Experiment log
    test = result.get("metrics", {}).get("test", {})
    entry = {
        "cycle": cycle,
        "branch": branch,
        "experiment_id": exp_id,
        "delta": desc,
        "f1": test.get("f1_macro", test.get("primary_metric", 0)),
        "accuracy": test.get("accuracy", 0),
        "p_value": test.get("p_value", 1.0),
        "composite_score": verdict.get("scores", {}).get("composite_score", 0),
        "champion_score": verdict.get("champion_score", 0),
        "verdict": verdict.get("verdict", "ERROR"),
        "timestamp": now,
    }
    with open(STATE / "experiment_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

    # Branch beliefs
    with open(STATE / "branch_beliefs.json") as f:
        beliefs = json.load(f)
    b = beliefs["branches"].get(branch, {})
    n = b.get("n_experiments", 0) + 1
    is_promote = verdict.get("verdict") == "PROMOTE"
    old_ev = b.get("current_ev", 0)
    b["n_experiments"] = n
    b["n_improvements"] = b.get("n_improvements", 0) + (1 if is_promote else 0)
    b["current_ev"] = round(0.7 * old_ev + 0.3 * (1 if is_promote else 0), 4)
    b["uncertainty"] = round(1.0 / (1 + n) ** 0.5, 4)
    b["last_explored_cycle"] = cycle
    if is_promote:
        score = verdict.get("scores", {}).get("composite_score", 0)
        b["best_composite_score"] = max(b.get("best_composite_score") or 0, score)
    b["status"] = "active"
    beliefs["branches"][branch] = b
    beliefs["updated_at"] = now
    with open(STATE / "branch_beliefs.json", "w") as f:
        json.dump(beliefs, f, indent=2)

    # Champions
    if is_promote:
        with open(STATE / "champions.json") as f:
            champions = json.load(f)
        exp_dir_rel = f"research_lab/experiments/{branch}/{exp_id}"
        champ_entry = {
            "experiment_id": exp_id,
            "scores": verdict.get("scores", {}),
            "result_path": f"{exp_dir_rel}/result.json",
        }
        champions["branches"][branch] = champ_entry
        # Update production champion if this is the highest score
        prod_score = 0
        if champions.get("production_champion", {}).get("scores"):
            prod_score = champions["production_champion"]["scores"].get("composite_score", 0)
        new_score = verdict.get("scores", {}).get("composite_score", 0)
        if new_score > prod_score:
            champions["production_champion"] = champ_entry
        champions["updated_at"] = now
        with open(STATE / "champions.json", "w") as f:
            json.dump(champions, f, indent=2)

    # Budget
    with open(STATE / "budget.json") as f:
        budget = json.load(f)
    budget[branch] = max(0, budget.get(branch, 0) - 1)
    with open(STATE / "budget.json", "w") as f:
        json.dump(budget, f, indent=2)


def update_cycle_counter(cycle: int, total: int):
    with open(STATE / "cycle_counter.json") as f:
        cc = json.load(f)
    cc["cycle"] = cycle
    cc["total_experiments"] = total
    cc["last_run_at"] = datetime.now(UTC).isoformat()
    with open(STATE / "cycle_counter.json", "w") as f:
        json.dump(cc, f, indent=2)


def update_agents(agents: dict):
    with open(STATE / "active_agents.json", "w") as f:
        json.dump({"updated_at": datetime.now(UTC).isoformat(), "agents": agents}, f, indent=2)


def run_red_team(cycle: int, seed: int) -> bool:
    """Run red team check. Returns True if PASS."""
    import numpy as np
    from datasets import load_dataset
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score

    ds = load_dataset("SetFit/sst5")
    X_train = list(ds["train"]["text"])
    y_train = np.array(ds["train"]["label"])
    X_test = list(ds["test"]["text"])
    y_test = np.array(ds["test"]["label"])

    rng = np.random.RandomState(seed)
    y_shuffled = rng.permutation(y_train)

    vec = TfidfVectorizer(max_features=10000, sublinear_tf=True)
    X_tr = vec.fit_transform(X_train)
    X_te = vec.transform(X_test)

    clf = LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")
    clf.fit(X_tr, y_shuffled)
    preds = clf.predict(X_te)
    f1 = float(f1_score(y_test, preds, average="macro"))

    passed = f1 < 0.25
    rt_dir = LAB / "experiments" / "red_team" / f"red_team_c{cycle}"
    rt_dir.mkdir(parents=True, exist_ok=True)
    with open(rt_dir / "result.json", "w") as f:
        json.dump({"cycle": cycle, "seed": seed, "f1_shuffled": round(f1, 4),
                    "threshold": 0.25, "integrity_pass": passed}, f, indent=2)

    entry = {"cycle": cycle, "type": "red_team", "seed": seed,
             "f1_shuffled": round(f1, 4), "integrity_pass": passed,
             "timestamp": datetime.now(UTC).isoformat()}
    with open(STATE / "experiment_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"  RED TEAM cycle {cycle}: F1_shuffled={f1:.4f} {'PASS' if passed else 'FAIL'}")
    return passed


def check_stuck_branches() -> list[str]:
    """Identify branches with 3+ consecutive non-improvements."""
    with open(STATE / "branch_beliefs.json") as f:
        beliefs = json.load(f)
    with open(STATE / "experiment_log.jsonl") as f:
        lines = [json.loads(l) for l in f if l.strip()]

    stuck = []
    for name, b in beliefs["branches"].items():
        if b.get("status") in ("blocked", "exhausted"):
            continue
        if b.get("n_experiments", 0) < 3:
            continue
        # Check last 3 experiments for this branch
        branch_exps = [e for e in lines if e.get("branch") == name and e.get("verdict")]
        if len(branch_exps) >= 3:
            last3 = branch_exps[-3:]
            if all(e["verdict"] != "PROMOTE" for e in last3):
                stuck.append(name)
    return stuck


def research_scout(branch: str, notes: str) -> str:
    """Write a research brief for a stuck branch.

    In a full deployment, this would use WebSearch/WebFetch to find papers.
    Here we log the request so the orchestrator agent can pick it up.
    """
    scout_dir = LAB / "experiments" / branch / "research_scout"
    scout_dir.mkdir(parents=True, exist_ok=True)
    brief = {
        "branch": branch,
        "status": "stuck",
        "notes": notes,
        "request": (
            f"Branch '{branch}' has had 3+ consecutive non-improvements. "
            f"Search for recent papers (2024-2026) on approaches to improve "
            f"SST-5 sentiment classification with TF-IDF features. "
            f"Look for: novel feature engineering, loss functions, "
            f"data augmentation, or model architectures that work on small "
            f"datasets (~8.5K samples) with CPU-only constraints."
        ),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    path = scout_dir / f"scout_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w") as f:
        json.dump(brief, f, indent=2)
    print(f"  RESEARCH SCOUT: {branch} flagged for external research. Brief at {path}")
    return str(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=30)
    args = parser.parse_args()

    with open(STATE / "cycle_counter.json") as f:
        cc = json.load(f)
    start_cycle = cc["cycle"] + 1
    total_experiments = cc.get("total_experiments", 0)

    queue = list(EXPERIMENT_QUEUE)
    exp_idx = 0

    # Check for stuck branches at start
    stuck = check_stuck_branches()
    if stuck:
        print(f"STUCK BRANCHES DETECTED: {stuck}")
        for br in stuck:
            research_scout(br, f"3+ consecutive non-improvements on branch {br}")

    for cycle_offset in range(args.cycles):
        cycle = start_cycle + cycle_offset
        print(f"\n{'='*60}")
        print(f"CYCLE {cycle}")
        print(f"{'='*60}")

        # Red team every 5th cycle
        if cycle % 5 == 0 and cycle > 0:
            run_red_team(cycle, 42 + cycle)

        # Budget replenishment every 10th cycle
        if cycle % 10 == 0 and cycle > 0:
            with open(STATE / "budget.json") as f:
                budget = json.load(f)
            with open(STATE / "branch_beliefs.json") as f:
                beliefs = json.load(f)
            for br in budget:
                budget[br] += 5
                if beliefs["branches"].get(br, {}).get("n_improvements", 0) > 0:
                    budget[br] += 3
            with open(STATE / "budget.json", "w") as f:
                json.dump(budget, f, indent=2)
            entry = {"cycle": cycle, "type": "budget_replenishment",
                     "timestamp": datetime.now(UTC).isoformat()}
            with open(STATE / "experiment_log.jsonl", "a") as f:
                f.write(json.dumps(entry) + "\n")
            print(f"  BUDGET REPLENISHED: {budget}")

        # Pick up to 4 experiments from queue
        batch = []
        with open(STATE / "budget.json") as f:
            budget = json.load(f)

        while len(batch) < 4 and exp_idx < len(queue):
            branch, exp_id, desc, overrides = queue[exp_idx]
            if budget.get(branch, 0) > 0:
                batch.append((branch, exp_id, desc, overrides))
            exp_idx += 1

        if not batch:
            print("  No more experiments in queue. Stopping.")
            break

        # Update agent status
        agents = {}
        for branch, exp_id, desc, _ in batch:
            agents[branch] = {"status": "running", "experiment_id": exp_id,
                              "started_at": datetime.now(UTC).isoformat()}
        update_agents(agents)

        # Run batch
        for branch, exp_id, desc, overrides in batch:
            config = build_config(branch, exp_id, desc, overrides)
            exp_dir = LAB / "experiments" / branch / exp_id

            print(f"  [{branch}] {exp_id}: {desc}")
            t0 = time.time()
            result = run_experiment(config, exp_dir)
            if result is None:
                print(f"    CRASHED")
                total_experiments += 1
                continue

            verdict = judge_experiment(exp_dir, branch)
            if verdict is None:
                print(f"    JUDGE FAILED")
                total_experiments += 1
                continue

            elapsed = time.time() - t0
            total_experiments += 1
            v = verdict.get("verdict", "?")
            sc = verdict.get("scores", {}).get("composite_score", 0)
            f1 = result.get("metrics", {}).get("test", {}).get("f1_macro", 0)
            print(f"    F1={f1:.4f} score={sc:.4f} -> {v} ({elapsed:.1f}s)")

            update_state(cycle, branch, exp_id, desc, result, verdict)

        # Clear agents, update counter
        update_agents({})
        update_cycle_counter(cycle, total_experiments)

        # Check for stuck branches every 5 cycles
        if cycle % 5 == 0:
            stuck = check_stuck_branches()
            for br in stuck:
                research_scout(br, f"Still stuck at cycle {cycle}")

    print(f"\n{'='*60}")
    print(f"BATCH COMPLETE: cycles {start_cycle}-{start_cycle + args.cycles - 1}")
    print(f"Total experiments: {total_experiments}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
