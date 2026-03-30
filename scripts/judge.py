#!/usr/bin/env python3
"""Mechanical judge: scores experiments against champion using formula from constitution.md.

Customize the weights and metric extraction for your domain.

Usage:
    python research_lab/scripts/judge.py \
        --result research_lab/experiments/arch/arch_v2_c1/confirm/result.json \
        --champion research_lab/state/champions.json \
        --branch architecture
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


# ========== CUSTOMIZE THESE FOR YOUR DOMAIN ==========

def extract_primary_metric(result: dict) -> float:
    """Extract your primary deployment metric from result dict."""
    return result.get("metrics", {}).get("test", {}).get("primary_metric", 0.0)


def extract_robustness(result: dict) -> float:
    """Fraction of cross-validation folds with positive metric."""
    folds = result.get("cv_folds", result.get("walk_forward", []))
    if not folds:
        return 0.5
    positive = sum(1 for f in folds if f.get("primary_metric", f.get("markout_sharpe_1bp", 0)) > 0)
    return positive / len(folds)


def extract_complexity(result: dict) -> float:
    """Normalized complexity (0-1). Higher = more complex."""
    config = result.get("config", {})
    params = config.get("model", {}).get("params", {})
    # Customize: compute complexity from your model's parameters
    return 0.5  # default


BASELINE_METRIC = 0.50  # Your random-baseline metric (e.g., 50% accuracy)
WEIGHTS = {"D": 0.40, "R": 0.25, "G": 0.15, "C": 0.10, "I": 0.10, "K": 0.05}

# ========== END CUSTOMIZATION ==========


def check_hard_gates(result: dict) -> tuple[bool, list[str]]:
    """Apply hard gates. Returns (passed, failures)."""
    failures = []
    if "error" in result.get("metrics", {}):
        failures.append(f"Experiment errored: {result['metrics']['error']}")
        return False, failures

    metric = extract_primary_metric(result)
    if metric <= BASELINE_METRIC:
        failures.append(f"Primary metric {metric:.4f} <= baseline {BASELINE_METRIC}")

    p_value = result.get("metrics", {}).get("test", {}).get("p_value", 1.0)
    if p_value > 0.10:
        failures.append(f"p-value {p_value:.4f} > 0.10")

    return len(failures) == 0, failures


def compute_score(result: dict) -> dict[str, float]:
    """Compute soft score from constitution.md."""
    D = min(1.5, max(0, extract_primary_metric(result) / max(BASELINE_METRIC, 0.01)))
    R = extract_robustness(result)

    folds = result.get("cv_folds", result.get("walk_forward", []))
    if len(folds) >= 2:
        import numpy as np
        scores = [f.get("primary_metric", 0) for f in folds]
        mean_s = np.mean(scores)
        std_s = np.std(scores)
        G = 1.0 - min(2.0, std_s / max(abs(mean_s), 0.01)) / 2.0
    else:
        G = 0.5

    C = 0.5  # Override with your calibration metric
    I = 0.5  # Override with champion prediction comparison
    K = extract_complexity(result)

    w = WEIGHTS
    composite = w["D"]*D + w["R"]*R + w["G"]*G + w["C"]*C + w["I"]*I - w["K"]*K

    return {
        "D": round(D, 4), "R": round(R, 4), "G": round(G, 4),
        "C": round(C, 4), "I": round(I, 4), "K": round(K, 4),
        "composite_score": round(composite, 4),
    }


def judge(result: dict, champion_score: float = 0.0, branch: str = "") -> dict:
    """Full pipeline: hard gates + soft scoring + verdict."""
    exp_id = result.get("experiment_id", "unknown")
    passed, failures = check_hard_gates(result)

    if not passed:
        return {"experiment_id": exp_id, "branch": branch,
                "passed_hard_gates": False, "hard_gate_failures": failures,
                "scores": {}, "verdict": "REJECT", "reason": "; ".join(failures)}

    scores = compute_score(result)
    composite = scores["composite_score"]

    if composite >= champion_score:
        verdict, reason = "PROMOTE", f"score={composite:.4f} >= champion={champion_score:.4f}"
    elif composite >= champion_score - 0.05 and composite >= 0.30:
        verdict, reason = "MARGINAL", f"score={composite:.4f} within 0.05 of champion"
    else:
        verdict, reason = "REJECT", f"score={composite:.4f} < champion={champion_score:.4f}"

    return {"experiment_id": exp_id, "branch": branch,
            "passed_hard_gates": True, "scores": scores,
            "champion_score": champion_score,
            "delta": round(composite - champion_score, 4),
            "verdict": verdict, "reason": reason}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--champion", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()

    with open(args.result) as f:
        result = json.load(f)

    champ_score = 0.0
    with open(args.champion) as f:
        champions = json.load(f)
    branch_champ = champions.get("branches", {}).get(args.branch, {})
    if branch_champ and branch_champ.get("scores"):
        champ_score = branch_champ["scores"].get("composite_score", 0.0)

    verdict = judge(result, champ_score, args.branch)

    Path(args.result).parent.joinpath("verdict.json").write_text(
        json.dumps(verdict, indent=2))

    v = verdict["verdict"]
    s = verdict.get("scores", {}).get("composite_score", 0)
    d = verdict.get("delta", 0)
    print(f"VERDICT: id={verdict['experiment_id']} score={s:.4f} "
          f"champion_score={champ_score:.4f} delta={d:+.4f} verdict={v}")

    if not verdict["passed_hard_gates"]:
        for f in verdict["hard_gate_failures"]:
            print(f"  GATE FAIL: {f}")


if __name__ == "__main__":
    main()
