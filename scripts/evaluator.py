#!/usr/bin/env python3
"""Canonical evaluator for labrat vNext."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import yaml

from lab_core import write_json


# Canonical failure categories surfaced to the frontier + mutation workers.
FAILURE_CLASSES = {"overfit", "nan", "oom", "unstable", "data", "arch", "other"}


def load_json(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def lookup(data: dict[str, Any], path: str, default: float | None = None) -> float | None:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    if current is None:
        return default
    try:
        value = float(current)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return value


def score_from_spec(result: dict[str, Any], spec: dict[str, Any]) -> float | None:
    if not spec:
        return None
    direction = spec.get("direction", "maximize")
    if spec.get("path"):
        value = lookup(result, spec["path"])
        if value is None:
            return None
        return -value if direction == "minimize" else value

    blend = spec.get("blend", [])
    if not blend:
        return None
    total = 0.0
    weight_sum = 0.0
    for item in blend:
        value = lookup(result, item["path"])
        if value is None:
            continue
        weight = float(item.get("weight", 1.0))
        item_direction = item.get("direction", "maximize")
        total += (-value if item_direction == "minimize" else value) * weight
        weight_sum += weight
    if weight_sum <= 0:
        return None
    return total / weight_sum


def evaluate_prediction_tests(result: dict[str, Any], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for test in config.get("prediction_tests", []) or []:
        name = test.get("name")
        if not name:
            continue
        payload[name] = {
            "score": score_from_spec(result, test),
            "description": test.get("description"),
            "decisive": bool(test.get("decisive", True)),
        }
    return payload


def _load_checkpoint_series(artifact_dir: Path | None) -> list[dict[str, Any]]:
    if artifact_dir is None:
        return []
    path = artifact_dir / "checkpoints.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _summarise_checkpoints(series: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not series:
        return None

    def _score(row: dict[str, Any]) -> float | None:
        value = row.get("search_eval")
        if value is None:
            return None
        try:
            as_float = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(as_float):
            return None
        return as_float

    valid_scores = [_score(row) for row in series if row.get("valid", True)]
    valid_scores = [score for score in valid_scores if score is not None]
    if not valid_scores:
        trend = "collapsed" if any(row.get("valid") is False for row in series) else "no_signal"
        return {
            "checkpoints": len(series),
            "valid_checkpoints": 0,
            "trend": trend,
            "last_step": series[-1].get("step"),
            "last_valid": False,
        }

    first_third = valid_scores[: max(1, len(valid_scores) // 3)]
    last_third = valid_scores[-max(1, len(valid_scores) // 3) :]
    first_mean = sum(first_third) / len(first_third)
    last_mean = sum(last_third) / len(last_third)
    delta = last_mean - first_mean

    any_invalid_tail = any(row.get("valid") is False for row in series[max(0, len(series) // 2) :])

    if any_invalid_tail:
        trend = "collapsed"
    elif delta > 0.02:
        trend = "improving"
    elif delta < -0.02:
        trend = "regressing"
    else:
        trend = "plateau"

    return {
        "checkpoints": len(series),
        "valid_checkpoints": len(valid_scores),
        "first_mean": round(first_mean, 6),
        "last_mean": round(last_mean, 6),
        "delta": round(delta, 6),
        "trend": trend,
        "last_step": series[-1].get("step"),
        "last_valid": bool(series[-1].get("valid", True)),
    }


def _error_text(result: dict[str, Any]) -> str:
    metrics = result.get("metrics", {}) or {}
    error = metrics.get("error")
    if error is None:
        return ""
    return str(error).lower()


def infer_failure_class(result: dict[str, Any], checkpoint_summary: dict[str, Any] | None) -> str | None:
    """Map a result + checkpoint-summary pair to a canonical failure_class.

    Returns None when the run looks healthy (valid and not overfitting).
    """
    explicit = result.get("failure_class")
    if explicit and str(explicit).lower() in FAILURE_CLASSES:
        return str(explicit).lower()

    valid = bool(result.get("valid", True))
    error = _error_text(result)

    if "nan" in error or "non-finite" in error or "inf" in error:
        return "nan"
    if "oom" in error or "out of memory" in error or "cuda" in error:
        return "oom"
    if "d_model" in error or "divisible" in error or "mismatch" in error or "arch" in error:
        return "arch"
    if "data" in error or "corpus" in error or "missing" in error or "file not found" in error or "dataset" in error:
        return "data"

    if checkpoint_summary and checkpoint_summary.get("trend") == "collapsed":
        return "unstable"

    if not valid:
        return "other"

    # Overfit heuristic: training distribution score is materially higher than held-out.
    train_score = lookup(result, "metrics.search.primary_metric")
    holdout_score = lookup(result, "metrics.challenges.holdout_generalization.primary_metric")
    if train_score is not None and holdout_score is not None and train_score - holdout_score > 0.18:
        return "overfit"

    return None


def evaluate_result(
    result: dict[str, Any],
    config: dict[str, Any],
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    search_eval = score_from_spec(result, config.get("search_eval", {}))
    selection_eval = score_from_spec(result, config.get("selection_eval", {}))
    final_spec = config.get("final_eval", {})
    final_eval = score_from_spec(result, final_spec) if final_spec.get("enabled", False) else None
    prediction_tests = evaluate_prediction_tests(result, config)

    valid = bool(result.get("valid", True))
    if result.get("metrics", {}).get("error"):
        valid = False

    checkpoint_series = _load_checkpoint_series(artifact_dir)
    checkpoint_summary = _summarise_checkpoints(checkpoint_series)
    failure_class = infer_failure_class(result, checkpoint_summary)

    payload = {
        "valid": valid,
        "search_eval": search_eval,
        "selection_eval": selection_eval if selection_eval is not None else search_eval,
        "final_eval": final_eval,
        "proxy_metrics": result.get("proxy_metrics", {}),
        "resource_floor": result.get("resource_floor"),
        "finding": result.get("finding"),
        "metrics": result.get("metrics", {}),
        "prediction_tests": prediction_tests,
        "failure_class": failure_class,
    }
    if checkpoint_summary is not None:
        payload["checkpoint_summary"] = checkpoint_summary
        payload["checkpoint_count"] = checkpoint_summary.get("checkpoints")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a candidate result against evaluation.yaml")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=None,
        help="Optional artifact directory to look for checkpoints.jsonl. Defaults to the result file's parent.",
    )
    args = parser.parse_args(argv)

    result = load_json(args.result)
    with open(args.config) as f:
        config = yaml.safe_load(f) or {}

    artifact_dir = args.artifact_dir or args.result.parent
    payload = evaluate_result(result, config, artifact_dir=artifact_dir)
    if args.output:
        write_json(args.output, payload)
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
