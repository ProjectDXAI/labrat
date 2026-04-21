#!/usr/bin/env python3
"""Transformer-arch experiment runner for labrat vNext.

This profile ships a synthetic-only runner. It reads the candidate's
`resolved_config`, produces realistic-shape metrics (three canonical scores,
two decisive-challenge scores, a per-step `checkpoints.jsonl` trajectory,
and an auto-classified failure mode for configurations that would collapse),
all without a training framework. Running an architecture search against
synthetic metrics still exercises the full labrat loop — dispatch, evaluator,
mutation worker reading sibling failure_class, Pareto labelling, consolidation.

When you're ready to move to real training, replace this file with a runner
that honours the same contract. See docs/PROFILES.md for the contract and
docs/LONG_HORIZON.md for the `checkpoints.jsonl` shape.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from lab_core import write_json


def load_candidate(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def clear_checkpoint_log(path: Path) -> None:
    if path.exists():
        path.unlink()


def append_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(payload))
        f.write("\n")


def _lognormal_score(value: float, center: float, sigma: float) -> float:
    if value <= 0 or center <= 0:
        return 0.0
    return math.exp(-((math.log(value) - math.log(center)) ** 2) / (2 * sigma * sigma))


def _gaussian_score(value: float, center: float, sigma: float) -> float:
    return math.exp(-((value - center) ** 2) / (2 * sigma * sigma))


def config_target_score(config: dict) -> float:
    """Synthetic goal: reward intermediate depth/width, punish obvious dead ends."""
    model = config.get("model", {})
    training = config.get("training", {})
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    heads = int(model.get("heads", 2))
    lr = float(training.get("lr", 0.003))
    steps = int(training.get("steps", 100))
    warmup = int(training.get("warmup_steps", 10))
    dropout = float(model.get("dropout", 0.0))

    depth_score = _gaussian_score(depth, 4, 2)
    width_score = _gaussian_score(d_model, 64, 28)
    heads_score = _gaussian_score(heads, 4, 2)
    lr_score = _lognormal_score(lr, 0.003, 0.7)
    steps_score = _lognormal_score(steps, 120, 0.5)

    base = 0.35 * depth_score * width_score + 0.25 * heads_score + 0.2 * lr_score + 0.2 * steps_score
    if dropout > 0.1:
        base -= dropout * 0.4
    if warmup > 25:
        base -= 0.1
    return max(0.0, min(1.0, base))


def synthetic_trajectory(config: dict, rng: random.Random) -> list[dict]:
    model = config.get("model", {})
    training = config.get("training", {})
    steps = int(training.get("steps", 100))
    checkpoint_every = max(1, int(training.get("checkpoint_every", max(1, steps // 5))))
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    dropout = float(model.get("dropout", 0.0))
    warmup_steps = int(training.get("warmup_steps", 0))
    lr = float(training.get("lr", 0.003))

    final_score = config_target_score(config)
    collapse_step: int | None = None
    if depth >= 6 and d_model <= 48:
        collapse_step = int(steps * rng.uniform(0.6, 0.9))
    elif lr > 0.008 and warmup_steps < 5:
        collapse_step = int(steps * rng.uniform(0.05, 0.2))

    trajectory: list[dict] = []
    for step in range(checkpoint_every, steps + 1, checkpoint_every):
        progress = step / max(1, steps)
        warmup_penalty = max(0.0, 1 - (step / max(1, warmup_steps))) if warmup_steps > 0 else 0.0
        interim = final_score * (1 - math.exp(-3.0 * progress)) - 0.05 * warmup_penalty
        interim = max(0.0, min(1.0, interim + rng.gauss(0, 0.01)))
        loss = max(0.01, 2.5 * (1 - interim) + rng.gauss(0, 0.02))
        trajectory.append({"step": step, "search_eval": round(interim, 6), "loss": round(loss, 6), "valid": True})
        if collapse_step is not None and step >= collapse_step:
            trajectory[-1].update({"valid": False, "search_eval": 0.0, "loss": None, "note": "training collapsed"})
            break

    if dropout > 0.1:
        for checkpoint in trajectory:
            if checkpoint.get("valid"):
                checkpoint["search_eval"] = round(max(0.0, checkpoint["search_eval"] - dropout * 0.3), 6)

    return trajectory


def infer_failure(trajectory: list[dict]) -> tuple[bool, str | None, str | None]:
    if not trajectory:
        return False, "other", "empty trajectory"
    last = trajectory[-1]
    if not last.get("valid", True):
        loss = last.get("loss")
        if loss is None or (isinstance(loss, float) and math.isnan(loss)):
            return False, "nan", "training collapsed mid-run"
        return False, "unstable", "training instability mid-run"
    return True, None, "training ran to completion"


def summarise(trajectory: list[dict]) -> dict:
    valid_scores = [c["search_eval"] for c in trajectory if c.get("valid")]
    if not valid_scores:
        return {"final": 0.0, "peak": 0.0, "late_stability": 0.0}
    tail = valid_scores[max(0, 2 * len(valid_scores) // 3) :]
    return {
        "final": round(valid_scores[-1], 6),
        "peak": round(max(valid_scores), 6),
        "late_stability": round(max(0.0, 1.0 - (max(tail) - min(tail))), 6),
    }


def estimate_param_count(config: dict) -> int:
    model = config.get("model", {})
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    block = int(config.get("data", {}).get("block_size", 32))
    vocab = 96  # rough character vocab
    per_layer = 4 * d_model * d_model + 8 * d_model * d_model + 4 * d_model
    embed = vocab * d_model + block * d_model
    head = d_model * vocab
    return int(embed + depth * per_layer + head)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic transformer-arch runner for labrat vNext.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    candidate = load_candidate(args.candidate)
    config = candidate["resolved_config"]
    checkpoints_path = args.output.parent / "checkpoints.jsonl"
    clear_checkpoint_log(checkpoints_path)

    rng = random.Random(int(config.get("training", {}).get("seed", 1337)) ^ (hash(candidate["candidate_id"]) & 0xFFFF))
    trajectory = synthetic_trajectory(config, rng)
    for checkpoint in trajectory:
        append_checkpoint(checkpoints_path, checkpoint)

    valid, failure_class, note = infer_failure(trajectory)
    summary = summarise(trajectory)

    final_score = summary["final"]
    selection_score = max(0.0, final_score - 0.01 - abs(rng.gauss(0, 0.01)))
    final_eval = max(0.0, final_score - 0.02 - abs(rng.gauss(0, 0.01)))

    model = config.get("model", {})
    training = config.get("training", {})
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    steps = int(training.get("steps", 100))

    ood_penalty = 0.0
    if d_model > 96:
        ood_penalty += (d_model - 96) * 0.006
    if depth >= 6 and d_model >= 64:
        ood_penalty += 0.08
    if steps > 300:
        ood_penalty += 0.05
    holdout_generalization = max(0.0, final_score - ood_penalty - abs(rng.gauss(0, 0.02)))

    peak = summary["peak"]
    holdout_stability = 0.0 if peak == 0.0 else max(0.0, min(1.0, final_score / peak - abs(rng.gauss(0, 0.02))))

    elapsed = time.perf_counter() - started
    param_count = estimate_param_count(config)

    shape = f"d={depth} h={model.get('heads', '?')} w={d_model} lr={training.get('lr', '?')} steps={steps}"
    finding = (
        f"{shape} {failure_class or 'other'}: {note or 'run failed'}"
        if not valid
        else f"{shape} final={final_score} peak={peak}"
    )

    payload = {
        "candidate_id": candidate["candidate_id"],
        "valid": valid,
        "proxy_metrics": {
            "elapsed_seconds": round(elapsed, 4),
            "param_count": param_count,
            "steps_completed": trajectory[-1]["step"] if trajectory else 0,
            "late_stability": summary["late_stability"],
        },
        "metrics": {
            "search": {"primary_metric": round(final_score, 6)},
            "selection": {"primary_metric": round(selection_score, 6)},
            "final": {"primary_metric": round(final_eval, 6)},
            "challenges": {
                "holdout_generalization": {"primary_metric": round(holdout_generalization, 6)},
                "holdout_stability": {"primary_metric": round(holdout_stability, 6)},
            },
        },
        "finding": finding,
        "resource_floor": round(param_count / 400_000.0, 4),
    }
    if failure_class:
        payload["failure_class"] = failure_class
    if not valid:
        payload["metrics"]["error"] = note or "training failed"

    write_json(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
