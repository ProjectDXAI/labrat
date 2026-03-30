#!/usr/bin/env python3
"""Judge for SST-5 sentiment experiments. Scores on macro F1."""

from __future__ import annotations

import argparse
import json
import numpy as np
from pathlib import Path
from typing import Any

BASELINE_F1 = 0.20  # random baseline for 5 classes
WEIGHTS = {"D": 0.40, "R": 0.25, "G": 0.20, "C": 0.10, "K": 0.05}


def check_hard_gates(result: dict) -> tuple[bool, list[str]]:
    failures = []
    metrics = result.get("metrics", {})
    if "error" in metrics:
        failures.append(f"Errored: {metrics['error']}")
        return False, failures

    test = metrics.get("test", {})
    f1 = test.get("primary_metric", test.get("f1_macro", 0))
    if f1 <= BASELINE_F1:
        failures.append(f"F1={f1:.4f} <= baseline {BASELINE_F1}")

    p = test.get("p_value", 1.0)
    if p > 0.10:
        failures.append(f"p={p:.4f} > 0.10")

    folds = result.get("cv_folds", [])
    if len(folds) >= 2:
        pos = sum(1 for f in folds if f.get("primary_metric", 0) > BASELINE_F1)
        if pos <= len(folds) / 2:
            failures.append(f"CV: only {pos}/{len(folds)} folds > baseline")

    return len(failures) == 0, failures


def compute_score(result: dict) -> dict[str, float]:
    test = result.get("metrics", {}).get("test", {})
    folds = result.get("cv_folds", [])

    f1 = test.get("primary_metric", test.get("f1_macro", 0))
    D = min(1.5, max(0, f1 / 0.50))  # normalize against 0.50 F1

    if len(folds) >= 2:
        R = sum(1 for f in folds if f.get("primary_metric", 0) > BASELINE_F1) / len(folds)
        scores = [f.get("primary_metric", 0) for f in folds]
        mean_s = np.mean(scores)
        std_s = np.std(scores)
        G = 1.0 - min(2.0, std_s / max(abs(mean_s), 0.01)) / 2.0
    else:
        R, G = 0.5, 0.5

    C = 0.5  # default calibration
    config = result.get("config", {})
    n_feat = config.get("features", {}).get("max_features", 10000)
    K = min(1.0, n_feat / 50000)

    w = WEIGHTS
    composite = w["D"] * D + w["R"] * R + w["G"] * G + w["C"] * C - w["K"] * K

    return {
        "D": round(D, 4), "R": round(R, 4), "G": round(G, 4),
        "C": round(C, 4), "K": round(K, 4),
        "composite_score": round(composite, 4),
    }


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
    bc = champions.get("branches", {}).get(args.branch, {})
    if bc and bc.get("scores"):
        champ_score = bc["scores"].get("composite_score", 0.0)

    exp_id = result.get("experiment_id", "?")
    passed, failures = check_hard_gates(result)

    if not passed:
        verdict = {"experiment_id": exp_id, "branch": args.branch,
                    "passed_hard_gates": False, "hard_gate_failures": failures,
                    "scores": {}, "verdict": "REJECT", "reason": "; ".join(failures)}
    else:
        scores = compute_score(result)
        composite = scores["composite_score"]
        if composite >= champ_score:
            v, r = "PROMOTE", f"score={composite:.4f} >= champion={champ_score:.4f}"
        elif composite >= champ_score - 0.03 and composite >= 0.30:
            v, r = "MARGINAL", f"score={composite:.4f} near champion={champ_score:.4f}"
        else:
            v, r = "REJECT", f"score={composite:.4f} < champion={champ_score:.4f}"
        verdict = {"experiment_id": exp_id, "branch": args.branch,
                    "passed_hard_gates": True, "scores": scores,
                    "champion_score": champ_score,
                    "delta": round(composite - champ_score, 4),
                    "verdict": v, "reason": r}

    Path(args.result).parent.joinpath("verdict.json").write_text(json.dumps(verdict, indent=2))

    s = verdict.get("scores", {}).get("composite_score", 0)
    d = verdict.get("delta", 0)
    print(f"VERDICT: id={exp_id} score={s:.4f} champion_score={champ_score:.4f} "
          f"delta={d:+.4f} verdict={verdict['verdict']}")
    if not verdict.get("passed_hard_gates", True):
        for fail in verdict["hard_gate_failures"]:
            print(f"  GATE FAIL: {fail}")


if __name__ == "__main__":
    main()
