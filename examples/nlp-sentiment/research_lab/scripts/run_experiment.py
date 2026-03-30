#!/usr/bin/env python3
"""Run a sentiment classification experiment on SST-5.

Loads data from HuggingFace, trains model, evaluates, cross-validates.
All CPU, all <3 min per experiment on M4 MacBook Pro.

Usage:
    python research_lab/scripts/run_experiment.py \
        --config research_lab/experiments/model/model_catboost_c1/config.yaml \
        --output-dir research_lab/experiments/model/model_catboost_c1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline

warnings.filterwarnings("ignore")

# Cache dataset globally
_DATASET_CACHE = {}


def load_sst5():
    """Load SST-5 from HuggingFace (cached)."""
    if "sst5" not in _DATASET_CACHE:
        from datasets import load_dataset
        ds = load_dataset("SetFit/sst5")
        _DATASET_CACHE["sst5"] = ds
    ds = _DATASET_CACHE["sst5"]
    return (
        list(ds["train"]["text"]), list(ds["train"]["label"]),
        list(ds["test"]["text"]), list(ds["test"]["label"]),
    )


def build_vectorizer(config: dict) -> TfidfVectorizer:
    """Build TF-IDF vectorizer from config."""
    feat_cfg = config.get("features", {})
    ngram_min = feat_cfg.get("ngram_min", 1)
    ngram_max = feat_cfg.get("ngram_max", 1)
    return TfidfVectorizer(
        ngram_range=(ngram_min, ngram_max),
        max_features=feat_cfg.get("max_features", 10000),
        sublinear_tf=feat_cfg.get("sublinear_tf", True),
        analyzer=feat_cfg.get("analyzer", "word"),
        min_df=feat_cfg.get("min_df", 2),
        max_df=feat_cfg.get("max_df", 0.95),
        strip_accents="unicode",
        lowercase=config.get("preprocessing", {}).get("lowercase", True),
        stop_words="english" if config.get("preprocessing", {}).get("stop_words", False) else None,
    )


def build_model(config: dict):
    """Build classifier from config."""
    model_cfg = config.get("model", {})
    model_type = model_cfg.get("type", "logistic")
    params = model_cfg.get("params", {})

    if model_type == "logistic":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(
            C=params.get("C", 1.0),
            max_iter=params.get("max_iter", 1000),
            class_weight=params.get("class_weight", None),
            solver="lbfgs", multi_class="multinomial",
        )
    elif model_type == "svm":
        from sklearn.svm import LinearSVC
        from sklearn.calibration import CalibratedClassifierCV
        svc = LinearSVC(
            C=params.get("C", 1.0),
            max_iter=params.get("max_iter", 2000),
            class_weight=params.get("class_weight", None),
        )
        return CalibratedClassifierCV(svc, cv=3)
    elif model_type == "catboost":
        from catboost import CatBoostClassifier
        return CatBoostClassifier(
            iterations=params.get("iterations", 500),
            depth=params.get("depth", 6),
            learning_rate=params.get("learning_rate", 0.1),
            verbose=0, random_seed=42,
            auto_class_weights=params.get("auto_class_weights", None),
        )
    elif model_type == "lightgbm":
        from lightgbm import LGBMClassifier
        return LGBMClassifier(
            n_estimators=params.get("n_estimators", 500),
            max_depth=params.get("max_depth", -1),
            learning_rate=params.get("learning_rate", 0.1),
            class_weight=params.get("class_weight", None),
            verbose=-1, random_state=42, n_jobs=-1,
        )
    elif model_type == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=params.get("n_estimators", 300),
            max_depth=params.get("max_depth", None),
            class_weight=params.get("class_weight", None),
            random_state=42, n_jobs=-1,
        )
    elif model_type == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(
            n_estimators=params.get("n_estimators", 200),
            max_depth=params.get("max_depth", 5),
            learning_rate=params.get("learning_rate", 0.1),
            random_state=42,
        )
    elif model_type == "voting_soft":
        from sklearn.ensemble import VotingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.svm import LinearSVC
        from sklearn.calibration import CalibratedClassifierCV
        estimators = [
            ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight=params.get("class_weight"), solver="lbfgs", multi_class="multinomial")),
            ("svm", CalibratedClassifierCV(LinearSVC(C=1.0, max_iter=2000, class_weight=params.get("class_weight")), cv=3)),
            ("lr2", LogisticRegression(C=0.5, max_iter=1000, class_weight=params.get("class_weight"), solver="lbfgs", multi_class="multinomial")),
        ]
        return VotingClassifier(estimators=estimators, voting="soft")
    elif model_type == "stacking":
        from sklearn.ensemble import StackingClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.svm import LinearSVC
        from sklearn.calibration import CalibratedClassifierCV
        estimators = [
            ("lr", LogisticRegression(C=1.0, max_iter=1000, class_weight=params.get("class_weight"), solver="lbfgs", multi_class="multinomial")),
            ("svm", CalibratedClassifierCV(LinearSVC(C=1.0, max_iter=2000, class_weight=params.get("class_weight")), cv=3)),
        ]
        return StackingClassifier(
            estimators=estimators,
            final_estimator=LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs", multi_class="multinomial"),
            cv=3,
        )
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def run_permutation_test(X, y, model_cls_fn, vectorizer_fn, n_perms: int = 50) -> float:
    """Quick permutation test: shuffle labels, measure F1 drop."""
    # Get real score
    vec = vectorizer_fn()
    X_tf = vec.fit_transform(X)
    clf = model_cls_fn()
    clf.fit(X_tf, y)
    real_f1 = f1_score(y, clf.predict(X_tf), average="macro")

    rng = np.random.RandomState(42)
    count_better = 0
    for _ in range(n_perms):
        y_shuf = rng.permutation(y)
        clf_s = model_cls_fn()
        clf_s.fit(X_tf, y_shuf)
        shuf_f1 = f1_score(y_shuf, clf_s.predict(X_tf), average="macro")
        if shuf_f1 >= real_f1:
            count_better += 1

    return count_better / n_perms


def cross_validate(X_text, y, config, n_folds: int = 3) -> list[dict]:
    """Quick stratified CV."""
    y_arr = np.array(y)
    folds = []
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)

    for fold_i, (train_idx, val_idx) in enumerate(skf.split(X_text, y_arr)):
        X_train = [X_text[i] for i in train_idx]
        X_val = [X_text[i] for i in val_idx]
        y_train, y_val = y_arr[train_idx], y_arr[val_idx]

        vec = build_vectorizer(config)
        X_tr_tf = vec.fit_transform(X_train)
        X_va_tf = vec.transform(X_val)

        clf = build_model(config)
        clf.fit(X_tr_tf, y_train)
        preds = clf.predict(X_va_tf)

        folds.append({
            "fold": fold_i,
            "primary_metric": float(f1_score(y_val, preds, average="macro")),
            "accuracy": float(accuracy_score(y_val, preds)),
            "n_train": len(train_idx),
            "n_val": len(val_idx),
        })

    return folds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    exp_id = config.get("experiment_id", "unknown")
    t0 = time.time()

    # Load data
    X_train, y_train, X_test, y_test = load_sst5()

    # Build pipeline
    vec = build_vectorizer(config)
    clf = build_model(config)

    # Train
    X_tr_tf = vec.fit_transform(X_train)
    X_te_tf = vec.transform(X_test)
    clf.fit(X_tr_tf, np.array(y_train))

    # Predict
    preds = clf.predict(X_te_tf)
    y_test_arr = np.array(y_test)

    # Metrics
    acc = float(accuracy_score(y_test_arr, preds))
    f1 = float(f1_score(y_test_arr, preds, average="macro"))
    per_class = f1_score(y_test_arr, preds, average=None).tolist()

    # Cross-validate
    cv_folds = cross_validate(X_train, y_train, config, n_folds=3)

    # Quick permutation test (on train set for speed)
    p_value = run_permutation_test(
        X_train[:2000], y_train[:2000],
        lambda: build_model(config),
        lambda: build_vectorizer(config),
        n_perms=30,
    )

    elapsed = time.time() - t0

    result = {
        "experiment_id": exp_id,
        "config": config,
        "metrics": {
            "test": {
                "primary_metric": f1,
                "accuracy": acc,
                "f1_macro": f1,
                "f1_per_class": per_class,
                "p_value": p_value,
            }
        },
        "cv_folds": cv_folds,
        "diagnostics": {
            "n_train": len(X_train),
            "n_test": len(X_test),
            "n_features": X_tr_tf.shape[1],
            "pred_std": float(np.std([f["primary_metric"] for f in cv_folds])),
        },
        "elapsed_sec": round(elapsed, 1),
    }

    result_path = output_dir / "result.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    cv_mean = np.mean([f["primary_metric"] for f in cv_folds])
    cv_pos = sum(1 for f in cv_folds if f["primary_metric"] > 0.20)

    print(
        f"RESULT: id={exp_id} "
        f"f1={f1:.4f} acc={acc:.4f} "
        f"cv_mean={cv_mean:.4f} cv_pos={cv_pos}/{len(cv_folds)} "
        f"p_value={p_value:.4f} "
        f"elapsed={elapsed:.0f}s"
    )


if __name__ == "__main__":
    main()
