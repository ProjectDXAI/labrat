#!/usr/bin/env python3
"""Universal judge for labrat v2.

Scores experiments against the current champion using the constitution's
scoring formula. Supports per-branch scoring overrides, effect size gates,
information gain, domain-specific calibration, diagnostic experiments,
and val/test decay tracking.

Usage:
    python judge.py --result result.json --champion state/champions.json --branch features
    python judge.py --result result.json --champion state/champions.json --branch execution --diagnostic
    python judge.py --result result.json --champion state/champions.json --branch model \
        --weights '{"D":0.50,"R":0.20,"G":0.15,"I":0.10,"C":0.00,"K":0.05}'
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


# ============================================================
# CUSTOMIZE THESE FOR YOUR DOMAIN
# ============================================================

BASELINE_METRIC = 0.50  # random baseline for your primary metric
DEFAULT_TARGET = 1.00   # normalization target for D component

DEFAULT_WEIGHTS = {
    "D": 0.35,  # deployment metric
    "R": 0.20,  # robustness
    "G": 0.15,  # generalization
    "I": 0.10,  # information gain (NEW: active in v2)
    "C": 0.10,  # calibration (NEW: computed per domain in v2)
    "K": 0.05,  # complexity penalty (subtracted)
}


def extract_primary_metric(result: dict) -> float:
    """Extract the primary metric from result. CUSTOMIZE THIS."""
    return result.get("metrics", {}).get("test", {}).get("primary_metric", 0.0)


def extract_robustness(result: dict) -> tuple[float, float]:
    """Extract robustness (R) and generalization (G) from CV folds."""
    folds = result.get("cv_folds", result.get("walk_forward", []))
    if len(folds) < 2:
        return 0.5, 0.5

    scores = [f.get("primary_metric", f.get("markout_sharpe_1bp", 0)) for f in folds]
    R = sum(1 for s in scores if s > 0) / len(scores)

    mean_s = float(np.mean(scores))
    std_s = float(np.std(scores))
    G = 1.0 - min(2.0, std_s / max(abs(mean_s), 0.001)) / 2.0

    return R, G


def extract_calibration(result: dict) -> float:
    """Extract calibration (C). CUSTOMIZE per domain.

    Classification: ECE (expected calibration error)
    Regression/Trading: prediction interval coverage
    Prediction markets: Brier reliability component
    Default: 0.5
    """
    test = result.get("metrics", {}).get("test", {})

    # Try ECE (classification)
    ece = test.get("ece")
    if ece is not None:
        return 1.0 - min(1.0, ece / 0.20)

    # Try prediction interval coverage (regression/trading)
    coverage = test.get("coverage_80pct")
    if coverage is not None:
        return 1.0 - abs(coverage - 0.80) / 0.80

    # Try Brier reliability (prediction markets)
    reliability = test.get("brier_reliability")
    if reliability is not None:
        return 1.0 - min(1.0, reliability / 0.05)

    return 0.5


def extract_complexity(result: dict) -> float:
    """Extract normalized complexity (K, 0-1). CUSTOMIZE THIS."""
    config = result.get("config", {})
    params = config.get("model", {}).get("params", {})
    return 0.5  # override with your complexity calculation


def extract_information_gain(result: dict, champion_preds_path: Path | None) -> float:
    """Compute information gain (I): how different are new predictions from champion?

    Returns 1 - rank_correlation(new_preds, champion_preds).
    High I = genuinely novel predictions. Low I = same model, different wrapper.
    """
    if champion_preds_path is None or not champion_preds_path.exists():
        return 0.5

    new_preds = result.get("predictions")
    if new_preds is None:
        return 0.5

    try:
        champion_preds = np.load(champion_preds_path)
        from scipy.stats import spearmanr
        corr, _ = spearmanr(new_preds, champion_preds)
        return max(0, 1.0 - abs(corr))
    except Exception:
        return 0.5


# ============================================================
# SCORING LOGIC
# ============================================================

def check_hard_gates(result: dict) -> tuple[bool, list[str]]:
    """Apply hard gates. Returns (passed, list_of_failures)."""
    failures = []
    metrics = result.get("metrics", {})

    if "error" in metrics:
        failures.append(f"Experiment errored: {metrics['error']}")
        return False, failures

    metric = extract_primary_metric(result)
    if metric <= BASELINE_METRIC:
        failures.append(f"Primary metric {metric:.4f} <= baseline {BASELINE_METRIC}")

    test = metrics.get("test", {})
    p = test.get("p_value", 1.0)
    if p > 0.10:
        failures.append(f"p-value {p:.4f} > 0.10")

    folds = result.get("cv_folds", result.get("walk_forward", []))
    if len(folds) >= 2:
        pos = sum(1 for f in folds if f.get("primary_metric", f.get("markout_sharpe_1bp", 0)) > 0)
        if pos <= len(folds) / 2:
            failures.append(f"CV: only {pos}/{len(folds)} folds above baseline")

    return len(failures) == 0, failures


def compute_score(
    result: dict,
    weights: dict | None = None,
    target: float | None = None,
    champion_preds_path: Path | None = None,
) -> dict[str, float]:
    """Compute all score components and composite."""
    w = weights or DEFAULT_WEIGHTS
    tgt = target or DEFAULT_TARGET

    metric = extract_primary_metric(result)
    D = min(1.5, max(0, metric / max(tgt, 0.001)))

    R, G = extract_robustness(result)
    I = extract_information_gain(result, champion_preds_path)
    C = extract_calibration(result)
    K = extract_complexity(result)

    composite = (
        w.get("D", 0.35) * D
        + w.get("R", 0.20) * R
        + w.get("G", 0.15) * G
        + w.get("I", 0.10) * I
        + w.get("C", 0.10) * C
        - w.get("K", 0.05) * K
    )

    return {
        "D": round(D, 4),
        "R": round(R, 4),
        "G": round(G, 4),
        "I": round(I, 4),
        "C": round(C, 4),
        "K": round(K, 4),
        "composite_score": round(composite, 4),
    }


def compute_effect_size(result: dict, champion_result_path: Path | None) -> float | None:
    """Compute Cohen's d between experiment and champion fold scores.

    Prevents promoting experiments that win by numerical noise.
    d > 0.2: meaningful. 0.05 < d < 0.2: small. d < 0.05: negligible.
    """
    folds = result.get("cv_folds", result.get("walk_forward", []))
    if len(folds) < 2:
        return None
    if champion_result_path is None or not champion_result_path.exists():
        return None

    try:
        with open(champion_result_path) as f:
            champ = json.load(f)
        champ_folds = champ.get("cv_folds", champ.get("walk_forward", []))
        if len(champ_folds) < 2:
            return None

        new_scores = [f.get("primary_metric", f.get("markout_sharpe_1bp", 0)) for f in folds]
        champ_scores = [f.get("primary_metric", f.get("markout_sharpe_1bp", 0)) for f in champ_folds]

        n1, n2 = len(new_scores), len(champ_scores)
        std1 = float(np.std(new_scores, ddof=1))
        std2 = float(np.std(champ_scores, ddof=1))
        pooled = math.sqrt(((n1 - 1) * std1**2 + (n2 - 1) * std2**2) / max(n1 + n2 - 2, 1))

        if pooled < 1e-10:
            return 0.0
        return float((np.mean(new_scores) - np.mean(champ_scores)) / pooled)
    except Exception:
        return None


def compute_decay_ratio(result: dict) -> float | None:
    """Track val-to-test performance decay.

    Returns test_metric / val_metric. Healthy: > 0.70. Red flag: < 0.50.
    If rolling average across experiments drops below 0.50, there's a
    systematic methodology problem (leakage, regime shift, etc).
    """
    metrics = result.get("metrics", {})
    val = metrics.get("val", {}).get("primary_metric")
    test = metrics.get("test", {}).get("primary_metric")
    if val is not None and test is not None and abs(val) > 1e-10:
        return float(test / val)
    return None


def judge(
    result: dict,
    champion_score: float = 0.0,
    branch: str = "",
    weights: dict | None = None,
    target: float | None = None,
    champion_preds_path: Path | None = None,
    champion_result_path: Path | None = None,
    diagnostic: bool = False,
) -> dict:
    """Full pipeline: hard gates + soft scoring + effect size + verdict."""
    exp_id = result.get("experiment_id", "unknown")

    # Diagnostic: extract insights only, no scoring
    if diagnostic:
        findings = result.get("findings", result.get("diagnostics", {}))
        return {
            "experiment_id": exp_id, "branch": branch,
            "verdict": "DIAGNOSTIC", "findings": findings,
            "reason": "Diagnostic experiment: insights only",
        }

    passed, failures = check_hard_gates(result)

    if not passed:
        return {
            "experiment_id": exp_id, "branch": branch,
            "passed_hard_gates": False, "hard_gate_failures": failures,
            "scores": {}, "verdict": "REJECT",
            "reason": "; ".join(failures),
        }

    scores = compute_score(result, weights, target, champion_preds_path)
    composite = scores["composite_score"]

    # Effect size gate
    effect_size = compute_effect_size(result, champion_result_path)
    scores["effect_size"] = round(effect_size, 4) if effect_size is not None else None

    # Decay ratio
    decay = compute_decay_ratio(result)
    scores["decay_ratio"] = round(decay, 4) if decay is not None else None

    # Verdict with effect size gate
    if composite >= champion_score:
        if effect_size is not None and effect_size < 0.05:
            v = "MARGINAL"
            r = f"score={composite:.4f} >= champion but effect_size={effect_size:.3f} < 0.05"
        else:
            v = "PROMOTE"
            r = f"score={composite:.4f} >= champion={champion_score:.4f}"
            if effect_size is not None:
                r += f" (d={effect_size:.3f})"
    elif composite >= champion_score - 0.05 and composite >= 0.30:
        v = "MARGINAL"
        r = f"score={composite:.4f} near champion={champion_score:.4f}"
    else:
        v = "REJECT"
        r = f"score={composite:.4f} < champion={champion_score:.4f}"

    return {
        "experiment_id": exp_id, "branch": branch,
        "passed_hard_gates": True, "scores": scores,
        "champion_score": champion_score,
        "delta": round(composite - champion_score, 4),
        "verdict": v, "reason": r,
    }


def main():
    parser = argparse.ArgumentParser(description="Labrat v2 experiment judge")
    parser.add_argument("--result", required=True, help="Path to result.json")
    parser.add_argument("--champion", required=True, help="Path to state/champions.json")
    parser.add_argument("--branch", required=True, help="Branch name")
    parser.add_argument("--diagnostic", action="store_true",
                        help="Diagnostic mode: extract insights, no scoring")
    parser.add_argument("--weights", type=str, default=None,
                        help="JSON string of per-branch weight overrides")
    parser.add_argument("--target", type=float, default=None,
                        help="D normalization target override")
    parser.add_argument("--champion-preds", type=str, default=None,
                        help="Path to champion predictions .npy for information gain")
    parser.add_argument("--champion-result", type=str, default=None,
                        help="Path to champion result.json for effect size")
    args = parser.parse_args()

    with open(args.result) as f:
        result = json.load(f)

    # Load champion score
    champ_score = 0.0
    champ_result_path = None
    with open(args.champion) as f:
        champions = json.load(f)
    bc = champions.get("branches", {}).get(args.branch, {})
    if bc and bc.get("scores"):
        champ_score = bc["scores"].get("composite_score", 0.0)
    if bc and bc.get("result_path"):
        champ_result_path = Path(bc["result_path"])

    weights = json.loads(args.weights) if args.weights else None
    champion_preds = Path(args.champion_preds) if args.champion_preds else None
    champion_result = Path(args.champion_result) if args.champion_result else champ_result_path

    verdict = judge(
        result, champ_score, args.branch,
        weights=weights,
        target=args.target,
        champion_preds_path=champion_preds,
        champion_result_path=champion_result,
        diagnostic=args.diagnostic,
    )

    # Write verdict file
    Path(args.result).parent.joinpath("verdict.json").write_text(
        json.dumps(verdict, indent=2)
    )

    # Print for orchestrator to grep
    if verdict["verdict"] == "DIAGNOSTIC":
        print(f"VERDICT: id={verdict['experiment_id']} verdict=DIAGNOSTIC")
        findings = verdict.get("findings", {})
        if isinstance(findings, dict):
            for k, v in list(findings.items())[:5]:
                print(f"  FINDING: {k}={v}")
    else:
        s = verdict.get("scores", {}).get("composite_score", 0)
        d = verdict.get("delta", 0)
        print(f"VERDICT: id={verdict['experiment_id']} score={s:.4f} "
              f"champion_score={champ_score:.4f} delta={d:+.4f} verdict={verdict['verdict']}")
        if not verdict.get("passed_hard_gates", True):
            for fail in verdict["hard_gate_failures"]:
                print(f"  GATE FAIL: {fail}")

    # Decay warning
    decay = verdict.get("scores", {}).get("decay_ratio")
    if decay is not None and decay < 0.50:
        print(f"  DECAY WARNING: ratio={decay:.2f} (test < half of val)")


if __name__ == "__main__":
    main()
