#!/usr/bin/env python3
"""Canonical evaluator for labrat vNext."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


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
    return float(current)


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


def evaluate_result(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    search_eval = score_from_spec(result, config.get("search_eval", {}))
    selection_eval = score_from_spec(result, config.get("selection_eval", {}))
    final_spec = config.get("final_eval", {})
    final_eval = score_from_spec(result, final_spec) if final_spec.get("enabled", False) else None
    prediction_tests = evaluate_prediction_tests(result, config)

    valid = bool(result.get("valid", True))
    if result.get("metrics", {}).get("error"):
        valid = False

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
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a candidate result against evaluation.yaml")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    result = load_json(args.result)
    with open(args.config) as f:
        config = yaml.safe_load(f) or {}

    payload = evaluate_result(result, config)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
