#!/usr/bin/env python3
"""Compute Pareto ranks for the current candidate population.

labrat's runtime decision tree is deliberately scalar. This helper adds a
Pareto-rank *label* alongside the scalar selection_eval without changing how
promotion is gated. The mutation_worker and crossover_worker prompts can read
`state/pareto.json` to prefer diverse frontier parents over dominated ones.

Enable by declaring `pareto_metrics` in `evaluation.yaml`:

    pareto_metrics:
      - path: "metrics.selection.primary_metric"
        direction: "maximize"
        label: "held_out_score"
      - path: "metrics.challenges.holdout_generalization.primary_metric"
        direction: "maximize"
        label: "ood_score"
      - path: "proxy_metrics.elapsed_seconds"
        direction: "minimize"
        label: "elapsed_sec"
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from lab_core import write_json


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def lookup(data: dict[str, Any], path: str) -> float | None:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    if current is None:
        return None
    try:
        value = float(current)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def latest_by_candidate(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        latest[candidate_id] = row
    return latest


def extract_vector(evaluation_row: dict[str, Any], metrics_spec: list[dict[str, Any]]) -> list[float | None]:
    vector: list[float | None] = []
    for item in metrics_spec:
        value = lookup(evaluation_row, item["path"])
        if value is None:
            vector.append(None)
            continue
        if item.get("direction", "maximize") == "minimize":
            value = -value
        vector.append(value)
    return vector


def dominates(a: list[float | None], b: list[float | None]) -> bool:
    """a dominates b iff a is no worse on every objective and strictly better on at least one."""
    if any(x is None for x in a) or any(x is None for x in b):
        return False
    strictly_better = False
    for x, y in zip(a, b):
        if x < y:
            return False
        if x > y:
            strictly_better = True
    return strictly_better


def non_dominated_sort(vectors: dict[str, list[float | None]]) -> tuple[list[list[str]], dict[str, list[str]]]:
    """Return (fronts, dominated_by) where fronts[i] is the list of candidate_ids at rank i."""
    remaining = {cid: vec for cid, vec in vectors.items() if all(x is not None for x in vec)}
    dominated_by: dict[str, list[str]] = {cid: [] for cid in vectors}
    fronts: list[list[str]] = []

    while remaining:
        current_front: list[str] = []
        for cid, vec in remaining.items():
            beaten = [other_cid for other_cid, other_vec in remaining.items() if other_cid != cid and dominates(other_vec, vec)]
            dominated_by[cid] = beaten
            if not beaten:
                current_front.append(cid)
        if not current_front:
            # No non-dominated candidate — break to avoid infinite loop. Should not happen.
            break
        fronts.append(sorted(current_front))
        for cid in current_front:
            remaining.pop(cid, None)

    for cid, vec in vectors.items():
        if any(x is None for x in vec):
            dominated_by.setdefault(cid, [])

    return fronts, dominated_by


def compute_pareto(lab_root: Path) -> dict[str, Any]:
    evaluation_cfg = load_yaml(lab_root / "evaluation.yaml")
    metrics_spec = evaluation_cfg.get("pareto_metrics") or []
    if not metrics_spec:
        return {
            "generated_at": now_iso(),
            "enabled": False,
            "note": "evaluation.yaml has no `pareto_metrics` block; Pareto labelling is off.",
            "metrics": [],
            "fronts": [],
            "candidates": {},
        }

    state_dir = lab_root / "state"
    candidate_rows = load_jsonl(state_dir / "candidates.jsonl")
    evaluation_rows = load_jsonl(state_dir / "evaluations.jsonl")
    latest_candidates = latest_by_candidate(candidate_rows)
    latest_evaluations = latest_by_candidate(evaluation_rows)

    vectors: dict[str, list[float | None]] = {}
    labels: dict[str, dict[str, float | None]] = {}
    for candidate_id, evaluation_row in latest_evaluations.items():
        candidate_row = latest_candidates.get(candidate_id, {})
        status = candidate_row.get("status", "unknown")
        if status not in {"promoted", "evaluating", "rejected", "running"}:
            # Skip invalidated or placeholder rows so the front is not polluted.
            if status not in {"queued", "invalid"}:
                continue
        vec = extract_vector(evaluation_row, metrics_spec)
        vectors[candidate_id] = vec
        labels[candidate_id] = {
            item.get("label") or item["path"]: (
                (-v if item.get("direction", "maximize") == "minimize" else v)
                if v is not None else None
            )
            for item, v in zip(metrics_spec, vec)
        }

    fronts, dominated_by = non_dominated_sort(vectors)
    rank_of = {cid: rank for rank, front in enumerate(fronts) for cid in front}

    candidates_payload: dict[str, dict[str, Any]] = {}
    for candidate_id, vec in vectors.items():
        candidate_row = latest_candidates.get(candidate_id, {})
        candidates_payload[candidate_id] = {
            "family": candidate_row.get("family"),
            "status": candidate_row.get("status"),
            "rank": rank_of.get(candidate_id),
            "dominated_by": dominated_by.get(candidate_id, []),
            "values": labels[candidate_id],
            "missing_objectives": sum(1 for x in vec if x is None),
        }

    payload = {
        "generated_at": now_iso(),
        "enabled": True,
        "metrics": metrics_spec,
        "fronts": fronts,
        "front_count": len(fronts),
        "candidates": candidates_payload,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute Pareto ranks and write state/pareto.json.")
    parser.add_argument("--lab-dir", type=Path, default=None, help="Lab root. Defaults to the script's parent.parent.")
    parser.add_argument("--output", type=Path, default=None, help="Override output path. Defaults to <lab>/state/pareto.json.")
    args = parser.parse_args(argv)

    lab_root = args.lab_dir.resolve() if args.lab_dir else Path(__file__).resolve().parent.parent
    output_path = args.output or (lab_root / "state" / "pareto.json")

    payload = compute_pareto(lab_root)
    write_json(output_path, payload)
    if payload.get("enabled"):
        print(f"Wrote {output_path} ({payload['front_count']} fronts, {len(payload['candidates'])} candidates).")
    else:
        print(f"Wrote {output_path} (Pareto labelling disabled; add `pareto_metrics` to evaluation.yaml to enable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
