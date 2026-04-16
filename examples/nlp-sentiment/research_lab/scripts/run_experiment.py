#!/usr/bin/env python3
"""Toy sentiment experiment runner for the labrat vNext reference lab."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC


def load_candidate(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_rows(dataset_path: Path) -> list[dict]:
    rows = []
    with open(dataset_path) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_features(config: dict) -> tuple[TfidfVectorizer, TfidfVectorizer | None]:
    features = config["features"]
    word_vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, int(features.get("word_ngram_max", 1))),
        max_features=int(features.get("max_features", 800)),
        min_df=int(features.get("min_df", 1)),
    )
    char_vectorizer = None
    if features.get("char_ngrams"):
        char_vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, int(features.get("char_ngram_max", 4))),
            max_features=int(features.get("max_features", 800) // 2),
            min_df=1,
        )
    return word_vectorizer, char_vectorizer


def vectorize(config: dict, rows: list[dict]) -> tuple[dict[str, sparse.spmatrix], dict[str, np.ndarray], dict[str, list[str]]]:
    dataset_path = Path(config["data"]["dataset_path"])
    _ = dataset_path  # kept for config completeness
    splits = {"train": [], "search": [], "selection": [], "final": []}
    labels = {"train": [], "search": [], "selection": [], "final": []}
    for row in rows:
        split = row["split"]
        splits[split].append(row["text"])
        labels[split].append(int(row["label"]))

    word_vectorizer, char_vectorizer = build_features(config)
    X_train_word = word_vectorizer.fit_transform(splits["train"])
    matrices = {"train": X_train_word}
    for split in ("search", "selection", "final"):
        matrices[split] = word_vectorizer.transform(splits[split])

    if char_vectorizer is not None:
        X_train_char = char_vectorizer.fit_transform(splits["train"])
        matrices["train"] = sparse.hstack([matrices["train"], X_train_char]).tocsr()
        for split in ("search", "selection", "final"):
            matrices[split] = sparse.hstack(
                [matrices[split], char_vectorizer.transform(splits[split])]
            ).tocsr()

    y = {split: np.array(values) for split, values in labels.items()}
    return matrices, y, splits


def build_estimator(config: dict):
    model = config["model"]
    model_type = model.get("type", "logreg")
    class_weight = model.get("class_weight")
    if model_type == "logreg":
        estimator = LogisticRegression(
            C=float(model.get("C", 1.0)),
            class_weight=class_weight,
            max_iter=2000,
            multi_class="auto",
            random_state=int(config["training"].get("seed", 1337)),
        )
    elif model_type == "linearsvc":
        estimator = LinearSVC(
            C=float(model.get("C", 1.0)),
            class_weight=class_weight,
            random_state=int(config["training"].get("seed", 1337)),
        )
    elif model_type == "nb":
        estimator = MultinomialNB(alpha=float(model.get("alpha", 0.7)))
    else:
        raise ValueError(f"Unsupported model type: {model_type}")

    calibration = config.get("calibration", {})
    if calibration.get("enabled"):
        estimator = CalibratedClassifierCV(estimator, cv=2, method=calibration.get("method", "sigmoid"))
    return estimator


def score_split(estimator, X, y) -> dict:
    preds = estimator.predict(X)
    return {
        "primary_metric": float(f1_score(y, preds, average="macro")),
        "accuracy": float(accuracy_score(y, preds)),
    }


def score_slice(estimator, X, y) -> dict:
    if len(y) == 0:
        return {"primary_metric": 0.0, "accuracy": 0.0, "count": 0}
    preds = estimator.predict(X)
    return {
        "primary_metric": float(f1_score(y, preds, average="macro")),
        "accuracy": float(accuracy_score(y, preds)),
        "count": int(len(y)),
    }


def challenge_metrics(estimator, matrices, labels, texts) -> dict:
    challenge_X = sparse.vstack([matrices["selection"], matrices["final"]]).tocsr()
    challenge_y = np.concatenate([labels["selection"], labels["final"]])
    challenge_texts = texts["selection"] + texts["final"]

    extreme_mask = np.isin(challenge_y, [0, 4])
    mixed_tokens = ("still", "mostly", "acceptable", "partial", "rough", "yet", "but")
    mixed_mask = np.array([any(token in text for token in mixed_tokens) for text in challenge_texts])

    return {
        "extreme_polarity": score_slice(estimator, challenge_X[extreme_mask], challenge_y[extreme_mask]),
        "mixed_signal": score_slice(estimator, challenge_X[mixed_mask], challenge_y[mixed_mask]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a toy sentiment experiment.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    candidate = load_candidate(args.candidate)
    config = candidate["resolved_config"]
    dataset_path = args.candidate.parents[3] / config["data"]["dataset_path"]

    try:
        rows = load_rows(dataset_path)
        matrices, labels, texts = vectorize(config, rows)
        estimator = build_estimator(config)
        estimator.fit(matrices["train"], labels["train"])

        search_metrics = score_split(estimator, matrices["search"], labels["search"])
        selection_metrics = score_split(estimator, matrices["selection"], labels["selection"])
        final_metrics = score_split(estimator, matrices["final"], labels["final"])
        challenges = challenge_metrics(estimator, matrices, labels, texts)

        feature_count = int(matrices["train"].shape[1])
        elapsed = time.perf_counter() - started
        payload = {
            "candidate_id": candidate["candidate_id"],
            "valid": True,
            "proxy_metrics": {
                "feature_count": feature_count,
                "elapsed_seconds": round(elapsed, 4),
            },
            "metrics": {
                "search": search_metrics,
                "selection": selection_metrics,
                "final": final_metrics,
                "challenges": challenges,
            },
            "finding": (
                f"{config['model']['type']} with word_ngram_max={config['features']['word_ngram_max']} "
                f"and char_ngrams={config['features'].get('char_ngrams', False)}"
            ),
            "resource_floor": round(feature_count / 4000.0, 4),
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "candidate_id": candidate["candidate_id"],
            "valid": False,
            "proxy_metrics": {},
            "metrics": {
                "search": {"primary_metric": 0.0},
                "selection": {"primary_metric": 0.0},
                "final": {"primary_metric": 0.0},
                "error": str(exc),
            },
            "finding": "experiment crashed",
            "resource_floor": None,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
