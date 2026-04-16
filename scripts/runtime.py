#!/usr/bin/env python3
"""Async population runtime for labrat vNext."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from lab_core import (
    append_jsonl,
    find_readiness_issues,
    has_pending_runtime_work,
    latest_records,
    load_json,
    load_jsonl,
    load_yaml,
    now_iso,
    write_json,
)
from evaluator import evaluate_result


def state_dir(lab_root: Path) -> Path:
    return lab_root / "state"


def load_state(lab_root: Path) -> dict[str, Any]:
    sdir = state_dir(lab_root)
    candidate_rows = load_jsonl(sdir / "candidates.jsonl")
    evaluation_rows = load_jsonl(sdir / "evaluations.jsonl")
    return {
        "branches_config": load_yaml(lab_root / "branches.yaml", {}),
        "runtime_config": load_yaml(lab_root / "runtime.yaml", {}),
        "evaluation_config": load_yaml(lab_root / "evaluation.yaml", {}),
        "runtime": load_json(sdir / "runtime.json", {}),
        "jobs": load_json(sdir / "jobs.json", {"queued": [], "leased": [], "finished": []}),
        "workers": load_json(sdir / "workers.json", {"workers": {}}),
        "frontier": load_json(
            sdir / "frontier.json",
            {
                "global_champion": None,
                "family_champions": {},
                "elite_archive": {"global": [], "families": {}},
                "family_funding": {},
                "audit_queue": [],
                "invalid_fast_candidates": [],
                "unstable_candidates": [],
                "pending_expansion": None,
                "frame_break_required": False,
            },
        ),
        "candidate_rows": candidate_rows,
        "candidates": latest_records(candidate_rows, "candidate_id"),
        "evaluation_rows": evaluation_rows,
    }


def dashboard_payload(state: dict[str, Any]) -> dict[str, Any]:
    branches = state.get("branches_config", {})
    baseline = branches.get("production_baseline", {})
    families = branches.get("families") or {}
    return {
        "mission": branches.get("mission"),
        "baseline_description": baseline.get("description"),
        "baseline_experiment_id": baseline.get("experiment_id"),
        "families": {
            family_name: {
                "description": family.get("description"),
                "resource_class": family.get("resource_class", "cpu"),
            }
            for family_name, family in families.items()
        },
        "updated_at": now_iso(),
    }


def workspace_map_payload(lab_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    frontier = state.get("frontier", {})
    runtime = state.get("runtime", {})
    return {
        "lab_root": str(lab_root),
        "mission": state.get("branches_config", {}).get("mission"),
        "active_phase": runtime.get("active_phase"),
        "step_count": int(runtime.get("step_count", 0) or 0),
        "global_champion": frontier.get("global_champion"),
        "audit_queue": frontier.get("audit_queue", []),
        "pending_expansion": frontier.get("pending_expansion"),
        "artifact_regions": {
            "design": [
                "branches.yaml",
                "dead_ends.md",
                "research_brief.md",
                "research_sources.md",
                "evaluation.yaml",
                "runtime.yaml",
            ],
            "coordination": [
                "coordination/workspace_map.md",
                "coordination/prioritized_tasks.md",
                "coordination/implementation_log.md",
                "coordination/experiment_log.md",
            ],
            "runtime_state": [
                "state/runtime.json",
                "state/frontier.json",
                "state/jobs.json",
                "state/workers.json",
                "state/dashboard.json",
                "state/workspace_map.json",
            ],
            "artifact_streams": [
                "state/candidates.jsonl",
                "state/evaluations.jsonl",
                "state/checkpoints.jsonl",
            ],
            "candidate_artifacts": [
                "experiments/<family>/<candidate>/candidate.json",
                "experiments/<family>/<candidate>/result.json",
            ],
            "prompts": [
                "orchestrator.md",
                "probe_worker.md",
                "mutation_worker.md",
                "crossover_worker.md",
                "implementation_audit.md",
                "frame_break.md",
                "expansion_scout.md",
            ],
        },
        "updated_at": now_iso(),
    }


def render_workspace_map(payload: dict[str, Any]) -> str:
    champion = payload.get("global_champion")
    champion_line = "none"
    if champion:
        champion_line = (
            f"{champion.get('candidate_id')} "
            f"(selection={champion.get('selection_eval')}, family={champion.get('family')})"
        )
    lines = [
        "# Workspace Map",
        "",
        f"- mission: {payload.get('mission') or 'unset'}",
        f"- active_phase: {payload.get('active_phase') or 'idle'}",
        f"- step_count: {payload.get('step_count', 0)}",
        f"- global_champion: {champion_line}",
        f"- audit_queue: {', '.join(payload.get('audit_queue', [])) or 'none'}",
        f"- pending_expansion: {payload.get('pending_expansion') or 'none'}",
        "",
        "## Artifact Regions",
    ]
    for region, items in payload.get("artifact_regions", {}).items():
        lines.append(f"### {region}")
        for item in items:
            lines.append(f"- `{item}`")
        lines.append("")
    lines.append("Use this map as the default control surface. Read deeper artifacts only when the current phase requires them.")
    return "\n".join(lines).rstrip() + "\n"


def append_coordination_log(lab_root: Path, name: str, message: str) -> None:
    coordination = lab_root / "coordination"
    coordination.mkdir(parents=True, exist_ok=True)
    path = coordination / name
    with open(path, "a") as f:
        f.write(message.rstrip() + "\n")


def save_runtime_files(lab_root: Path, state: dict[str, Any]) -> None:
    sdir = state_dir(lab_root)
    write_json(sdir / "runtime.json", state["runtime"])
    write_json(sdir / "jobs.json", state["jobs"])
    write_json(sdir / "workers.json", state["workers"])
    write_json(sdir / "frontier.json", state["frontier"])
    write_json(sdir / "dashboard.json", dashboard_payload(state))
    workspace_payload = workspace_map_payload(lab_root, state)
    write_json(sdir / "workspace_map.json", workspace_payload)
    coordination = lab_root / "coordination"
    coordination.mkdir(parents=True, exist_ok=True)
    (coordination / "workspace_map.md").write_text(render_workspace_map(workspace_payload))


def append_candidate(lab_root: Path, candidate: dict[str, Any]) -> None:
    append_jsonl(state_dir(lab_root) / "candidates.jsonl", candidate)


def append_evaluation(lab_root: Path, evaluation: dict[str, Any]) -> None:
    append_jsonl(state_dir(lab_root) / "evaluations.jsonl", evaluation)


def append_checkpoint(lab_root: Path, payload: dict[str, Any]) -> None:
    append_jsonl(state_dir(lab_root) / "checkpoints.jsonl", payload)


def hash_payload(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


def family_defaults(runtime_cfg: dict[str, Any]) -> dict[str, Any]:
    funding = runtime_cfg.get("funding", {})
    return {
        "promote_credit": int(funding.get("promote_credit", 3)),
        "stable_credit": int(funding.get("stable_credit", 1)),
        "novelty_credit": int(funding.get("novelty_credit", 1)),
        "dispatch_cost": int(funding.get("dispatch_cost", 1)),
        "crossover_probability": float(runtime_cfg.get("selection", {}).get("crossover_probability", 0.2)),
        "max_lineage": int(runtime_cfg.get("selection", {}).get("max_concurrent_per_lineage", 3)),
        "global_top_k": int(runtime_cfg.get("selection", {}).get("elite_archive", {}).get("global_top_k", 20)),
        "family_top_k": int(runtime_cfg.get("selection", {}).get("elite_archive", {}).get("family_top_k", 3)),
    }


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def resolve_candidate_config(
    candidate: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    resolved = copy.deepcopy(baseline)
    for parent_id in candidate.get("parent_ids", []):
        parent = candidates.get(parent_id)
        if parent:
            resolved = deep_merge(resolved, resolve_candidate_config(parent, candidates, baseline))
            resolved = deep_merge(resolved, parent.get("config_patch", {}))
    return deep_merge(resolved, candidate.get("config_patch", {}))


def worker_pool_map(runtime_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pools = runtime_cfg.get("workers", {}).get("pools", [])
    workers: dict[str, dict[str, Any]] = {}
    for pool in pools:
        resource_class = pool["resource_class"]
        slots = int(pool.get("slots", 1))
        for index in range(slots):
            worker_id = f"{resource_class}-{index + 1}"
            workers[worker_id] = {
                "worker_id": worker_id,
                "resource_class": resource_class,
                "status": "idle",
                "lease_timeout_seconds": int(pool.get("lease_timeout_seconds", 1800)),
                "heartbeat_timeout_seconds": int(pool.get("heartbeat_timeout_seconds", 900)),
                "current_job_id": None,
                "current_candidate_id": None,
                "leased_at": None,
                "last_heartbeat_at": None,
            }
    return workers


def bootstrap_runtime(lab_root: Path) -> dict[str, Any]:
    issues = find_readiness_issues(lab_root)
    if issues:
        raise RuntimeError("Phase 0 is incomplete:\n- " + "\n- ".join(issues))

    config = load_yaml(lab_root / "branches.yaml", {})
    runtime_cfg = load_yaml(lab_root / "runtime.yaml", {})
    defaults = family_defaults(runtime_cfg)
    sdir = state_dir(lab_root)
    sdir.mkdir(parents=True, exist_ok=True)
    (lab_root / "logs" / "expansions").mkdir(parents=True, exist_ok=True)
    (lab_root / "logs" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (lab_root / "experiments").mkdir(parents=True, exist_ok=True)
    coordination = lab_root / "coordination"
    coordination.mkdir(parents=True, exist_ok=True)
    placeholder_files = {
        "prioritized_tasks.md": "# Prioritized Tasks\n\nUse this file for concise supervisor directives.\n",
        "implementation_log.md": "# Implementation Log\n\nAppend durable implementation notes here.\n",
        "experiment_log.md": "# Experiment Log\n\nAppend durable experiment summaries here.\n",
    }
    for name, body in placeholder_files.items():
        path = coordination / name
        if not path.exists():
            path.write_text(body)

    runtime_state = {
        "version": "vnext",
        "status": "idle",
        "active_phase": "supervisor",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "last_supervisor_action": "bootstrap-runtime",
        "stagnation_counter": 0,
        "step_count": 0,
        "last_checkpoint_at": None,
    }
    workers = {"updated_at": now_iso(), "workers": worker_pool_map(runtime_cfg)}
    frontier = {
        "updated_at": now_iso(),
        "global_champion": None,
        "family_champions": {},
        "elite_archive": {"global": [], "families": {}},
        "family_funding": {},
        "audit_queue": [],
        "invalid_fast_candidates": [],
        "unstable_candidates": [],
        "pending_expansion": None,
        "frame_break_required": False,
    }
    for family_name, family in (config.get("families") or {}).items():
        frontier["family_funding"][family_name] = {
            "credits": int(family.get("funding", {}).get("initial_credits", family.get("initial_credits", 6))),
            "spent": 0,
            "minted": 0,
            "remaining_cheap_probes": len(family.get("cheap_probes", [])),
            "tried_signatures": [],
            "queued_signatures": [],
            "tried_probe_signatures": [],
            "queued_probe_signatures": [],
            "plateau_counter": 0,
            "last_promoted_at": None,
            "status": "active",
            "exhausted": False,
        }
    jobs = {"updated_at": now_iso(), "queued": [], "leased": [], "finished": []}

    baseline = config.get("production_baseline", {})
    if baseline:
        baseline_candidate = {
            "candidate_id": baseline.get("experiment_id", "baseline"),
            "family": "baseline",
            "operator_type": "baseline",
            "parent_ids": [],
            "status": "promoted",
            "resource_class": baseline.get("resource_class", "cpu"),
            "config_patch": {},
            "proxy_metrics": {},
            "search_eval": baseline.get("seed_metrics", {}).get("search_eval"),
            "selection_eval": baseline.get("seed_metrics", {}).get("selection_eval"),
            "final_eval": baseline.get("seed_metrics", {}).get("final_eval"),
            "stability": {"runs": 0, "stable": True, "relative_std": 0.0},
            "resource_floor": baseline.get("seed_metrics", {}).get("resource_floor"),
            "finding": baseline.get("description"),
            "artifact_dir": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        append_candidate(lab_root, baseline_candidate)
        if baseline_candidate["selection_eval"] is not None:
            frontier["global_champion"] = {
                "candidate_id": baseline_candidate["candidate_id"],
                "selection_eval": baseline_candidate["selection_eval"],
                "search_eval": baseline_candidate["search_eval"],
                "family": "baseline",
            }

    write_json(sdir / "runtime.json", runtime_state)
    write_json(sdir / "jobs.json", jobs)
    write_json(sdir / "workers.json", workers)
    write_json(sdir / "frontier.json", frontier)
    if not (sdir / "candidates.jsonl").exists():
        (sdir / "candidates.jsonl").write_text("")
    if not (sdir / "evaluations.jsonl").exists():
        (sdir / "evaluations.jsonl").write_text("")
    if not (sdir / "checkpoints.jsonl").exists():
        (sdir / "checkpoints.jsonl").write_text("")
    (lab_root / "logs" / "handoff.md").write_text(
        "# labrat vNext Handoff\n\n"
        "Runtime bootstrapped.\n\n"
        f"- families: {', '.join((config.get('families') or {}).keys())}\n"
        f"- workers: {', '.join(workers['workers'].keys())}\n"
        "- next step: dispatch the first wave of candidates\n"
    )
    return load_state(lab_root)


def lineage_depth(candidate_id: str, candidates: dict[str, dict[str, Any]]) -> int:
    candidate = candidates.get(candidate_id)
    if not candidate or not candidate.get("parent_ids"):
        return 1
    return 1 + max(lineage_depth(parent_id, candidates) for parent_id in candidate["parent_ids"])


def build_signature(family: str, operator_type: str, patch: dict[str, Any], parent_ids: list[str]) -> str:
    return hash_payload(
        {
            "family": family,
            "operator_type": operator_type,
            "patch": patch,
            "parents": sorted(parent_ids),
        }
    )


def family_priority(family_name: str, state: dict[str, Any]) -> float:
    frontier = state["frontier"]
    family_state = frontier["family_funding"][family_name]
    credits = float(family_state.get("credits", 0))
    plateau_penalty = float(family_state.get("plateau_counter", 0)) * 0.25
    cheap_bonus = 1.0 if family_state.get("remaining_cheap_probes", 0) > 0 else 0.0
    family_champion = frontier.get("family_champions", {}).get(family_name, {})
    selection_eval = float(family_champion.get("selection_eval", 0.0) or 0.0)
    return credits + cheap_bonus + selection_eval - plateau_penalty


def next_probe_candidate(family_name: str, family: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    family_state = state["frontier"]["family_funding"][family_name]
    tried = set(family_state.get("tried_signatures", [])) | set(family_state.get("queued_signatures", []))
    for probe in family.get("cheap_probes", []):
        patch = probe.get("config_patch", {})
        signature = build_signature(family_name, "probe", patch, [])
        if signature in tried:
            continue
        return {
            "family": family_name,
            "operator_type": "probe",
            "parent_ids": [],
            "resource_class": family.get("resource_class", "cpu"),
            "config_patch": patch,
            "finding": probe.get("description"),
            "signature": signature,
        }
    return None


def candidate_parent_for_family(family_name: str, state: dict[str, Any]) -> list[str]:
    family_champion = state["frontier"].get("family_champions", {}).get(family_name)
    if family_champion:
        return [family_champion["candidate_id"]]
    global_champion = state["frontier"].get("global_champion")
    if global_champion:
        return [global_champion["candidate_id"]]
    baseline = state["branches_config"].get("production_baseline", {}).get("experiment_id")
    return [baseline] if baseline else []


def next_mutation_candidate(family_name: str, family: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    axes = family.get("mutation_policy", {}).get("axes", [])
    if not axes:
        return None
    parent_ids = [pid for pid in candidate_parent_for_family(family_name, state) if pid]
    family_state = state["frontier"]["family_funding"][family_name]
    tried = set(family_state.get("tried_signatures", [])) | set(family_state.get("queued_signatures", []))
    for axis in axes:
        path = axis.get("path")
        if not path:
            continue
        for option in axis.get("values", []):
            if isinstance(option, dict):
                patch = option.get("config_patch", {})
                description = option.get("description", option.get("name", path))
            else:
                patch = nested_patch(path, option)
                description = f"{path} -> {option}"
            signature = build_signature(family_name, "mutation", patch, parent_ids)
            if signature in tried:
                continue
            return {
                "family": family_name,
                "operator_type": "mutation",
                "parent_ids": parent_ids,
                "resource_class": family.get("resource_class", "cpu"),
                "config_patch": patch,
                "finding": description,
                "signature": signature,
            }
    return None


def next_crossover_candidate(family_name: str, family: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    crossover = family.get("crossover_policy", {})
    if not crossover.get("enabled"):
        return None
    compatible = crossover.get("compatible_families", [])
    family_champions = state["frontier"].get("family_champions", {})
    available = [other_family for other_family in compatible if other_family in family_champions]
    if len(available) < 2:
        return None
    for index, left_family in enumerate(available):
        for right_family in available[index + 1 :]:
            parent_ids = [
                family_champions[left_family]["candidate_id"],
                family_champions[right_family]["candidate_id"],
            ]
            patch = crossover.get("config_patch", {})
            signature = build_signature(family_name, "crossover", patch, parent_ids)
            family_state = state["frontier"]["family_funding"][family_name]
            tried = set(family_state.get("tried_signatures", [])) | set(family_state.get("queued_signatures", []))
            if signature in tried:
                continue
            return {
                "family": family_name,
                "operator_type": "crossover",
                "parent_ids": parent_ids,
                "resource_class": family.get("resource_class", "cpu"),
                "config_patch": patch,
                "finding": f"crossover {left_family} x {right_family}",
                "signature": signature,
            }
    return None


def nested_patch(path: str, value: Any) -> dict[str, Any]:
    keys = path.split(".")
    patch: Any = value
    for key in reversed(keys):
        patch = {key: patch}
    return patch


def create_candidate_record(candidate_spec: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    candidate_id = f"{candidate_spec['family']}_{candidate_spec['operator_type']}_{candidate_spec['signature']}"
    return {
        "candidate_id": candidate_id,
        "signature": candidate_spec["signature"],
        "family": candidate_spec["family"],
        "operator_type": candidate_spec["operator_type"],
        "parent_ids": candidate_spec["parent_ids"],
        "status": "queued",
        "resource_class": candidate_spec["resource_class"],
        "config_patch": candidate_spec["config_patch"],
        "proxy_metrics": {},
        "search_eval": None,
        "selection_eval": None,
        "final_eval": None,
        "stability": {"runs": 0, "stable": False, "relative_std": None},
        "resource_floor": None,
        "finding": candidate_spec.get("finding"),
        "artifact_dir": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "suspicion": None,
    }


def materialize_candidate(lab_root: Path, candidate: dict[str, Any], state: dict[str, Any]) -> None:
    baseline = state["branches_config"].get("production_baseline", {}).get("config", {})
    resolved = resolve_candidate_config(candidate, state["candidates"], baseline)
    artifact_dir = lab_root / "experiments" / candidate["family"] / candidate["candidate_id"]
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "candidate_id": candidate["candidate_id"],
        "family": candidate["family"],
        "operator_type": candidate["operator_type"],
        "parent_ids": candidate["parent_ids"],
        "config_patch": candidate["config_patch"],
        "resolved_config": resolved,
    }
    with open(artifact_dir / "candidate.json", "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    candidate["artifact_dir"] = str(artifact_dir.relative_to(lab_root))


def generate_candidate_spec(family_name: str, state: dict[str, Any]) -> dict[str, Any] | None:
    families = state["branches_config"].get("families") or {}
    family = families[family_name]
    for builder in (next_probe_candidate, next_mutation_candidate, next_crossover_candidate):
        spec = builder(family_name, family, state)
        if spec:
            return spec
    has_future_crossover = family.get("crossover_policy", {}).get("enabled", False)
    has_mutations = bool(family.get("mutation_policy", {}).get("axes", []))
    has_probes = bool(family.get("cheap_probes", []))
    if not has_future_crossover and not has_mutations and not has_probes:
        state["frontier"]["family_funding"][family_name]["exhausted"] = True
    return None


def top_up_queue(lab_root: Path, state: dict[str, Any], queue_depth: int | None = None) -> int:
    runtime_cfg = state["runtime_config"]
    defaults = family_defaults(runtime_cfg)
    workers = state["workers"]["workers"]
    target = queue_depth or max(len(workers), 1)
    created = 0

    while len(state["jobs"]["queued"]) + len(state["jobs"]["leased"]) < target:
        active_families = [
            family_name
            for family_name, family_state in state["frontier"]["family_funding"].items()
            if family_state.get("credits", 0) >= defaults["dispatch_cost"] and not family_state.get("exhausted")
        ]
        if not active_families:
            if not has_pending_runtime_work(state):
                state["frontier"]["frame_break_required"] = True
                state["runtime"]["active_phase"] = "frame_break_needed"
            break

        active_families.sort(key=lambda name: family_priority(name, state), reverse=True)
        chosen_family = None
        candidate_spec = None
        for family_name in active_families:
            spec = generate_candidate_spec(family_name, state)
            if spec is not None:
                chosen_family = family_name
                candidate_spec = spec
                break
        if candidate_spec is None or chosen_family is None:
            if not has_pending_runtime_work(state):
                state["frontier"]["frame_break_required"] = True
                state["runtime"]["active_phase"] = "frame_break_needed"
            break

        candidate = create_candidate_record(candidate_spec, state)
        materialize_candidate(lab_root, candidate, state)
        append_candidate(lab_root, candidate)
        state["candidates"][candidate["candidate_id"]] = candidate

        job = {
            "job_id": f"job_{candidate['candidate_id']}_1",
            "candidate_id": candidate["candidate_id"],
            "family": candidate["family"],
            "resource_class": candidate["resource_class"],
            "status": "queued",
            "attempt": 1,
            "queued_at": now_iso(),
            "leased_at": None,
            "worker_id": None,
            "artifact_dir": candidate["artifact_dir"],
        }
        state["jobs"]["queued"].append(job)
        family_state = state["frontier"]["family_funding"][chosen_family]
        family_state["credits"] -= defaults["dispatch_cost"]
        family_state["spent"] += defaults["dispatch_cost"]
        family_state["queued_signatures"].append(candidate_spec["signature"])
        if candidate_spec["operator_type"] == "probe":
            family_state.setdefault("queued_probe_signatures", []).append(candidate_spec["signature"])
        total_probes = len(state["branches_config"]["families"][chosen_family].get("cheap_probes", []))
        family_state["remaining_cheap_probes"] = max(
            0,
            total_probes
            - len(family_state.get("tried_probe_signatures", []))
            - len(family_state.get("queued_probe_signatures", [])),
        )
        created += 1

    state["jobs"]["updated_at"] = now_iso()
    state["frontier"]["updated_at"] = now_iso()
    state["runtime"]["updated_at"] = now_iso()
    return created


def parse_iso(value: str | None) -> float:
    if not value:
        return 0.0
    return datetime_from_iso(value).timestamp()


def datetime_from_iso(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def lease_job(lab_root: Path, state: dict[str, Any], worker_id: str) -> dict[str, Any] | None:
    worker = state["workers"]["workers"].get(worker_id)
    if worker is None:
        raise RuntimeError(f"Unknown worker {worker_id}")
    if worker["status"] == "leased":
        raise RuntimeError(f"Worker {worker_id} already has job {worker['current_job_id']}")

    compatible = [
        job for job in state["jobs"]["queued"] if job["resource_class"] == worker["resource_class"]
    ]
    if not compatible:
        return None
    compatible.sort(key=lambda job: (job["attempt"], job["queued_at"]))
    job = compatible[0]
    state["jobs"]["queued"] = [item for item in state["jobs"]["queued"] if item["job_id"] != job["job_id"]]
    job["status"] = "leased"
    job["leased_at"] = now_iso()
    job["worker_id"] = worker_id
    state["jobs"]["leased"].append(job)

    worker["status"] = "leased"
    worker["current_job_id"] = job["job_id"]
    worker["current_candidate_id"] = job["candidate_id"]
    worker["leased_at"] = now_iso()
    worker["last_heartbeat_at"] = now_iso()

    candidate = state["candidates"][job["candidate_id"]]
    candidate["status"] = "running"
    candidate["updated_at"] = now_iso()
    append_candidate(lab_root, candidate)
    state["runtime"]["status"] = "running"
    state["runtime"]["last_supervisor_action"] = f"leased {job['job_id']} to {worker_id}"
    save_runtime_files(lab_root, state)
    return job


def complete_job(lab_root: Path, state: dict[str, Any], candidate_id: str, result_path: Path, worker_id: str | None) -> dict[str, Any]:
    candidate = state["candidates"].get(candidate_id)
    if candidate is None:
        raise RuntimeError(f"Unknown candidate {candidate_id}")

    leased_jobs = state["jobs"]["leased"]
    matching_job = None
    for job in leased_jobs:
        if job["candidate_id"] == candidate_id and (worker_id is None or job["worker_id"] == worker_id):
            matching_job = job
            break
    if matching_job is None:
        raise RuntimeError(f"No leased job found for {candidate_id}")

    with open(result_path) as f:
        result = json.load(f)
    evaluation = evaluate_result(result, state["evaluation_config"])
    evaluation_record = {
        "candidate_id": candidate_id,
        "attempt": matching_job["attempt"],
        "result_path": str(result_path),
        "evaluated_at": now_iso(),
        **evaluation,
    }
    append_evaluation(lab_root, evaluation_record)
    state["evaluation_rows"].append(evaluation_record)

    candidate["proxy_metrics"] = evaluation_record.get("proxy_metrics", {})
    candidate["resource_floor"] = evaluation_record.get("resource_floor")
    candidate["finding"] = evaluation_record.get("finding") or candidate.get("finding")
    candidate["updated_at"] = now_iso()

    family_name = candidate["family"]
    family_cfg = (state["branches_config"].get("families") or {}).get(family_name, {})
    family_state = state["frontier"]["family_funding"].get(family_name, {})
    signature = candidate.get("signature")
    if signature in family_state.get("queued_signatures", []):
        family_state["queued_signatures"] = [value for value in family_state["queued_signatures"] if value != signature]
    if signature and signature not in family_state.get("tried_signatures", []):
        family_state.setdefault("tried_signatures", []).append(signature)
    if candidate["operator_type"] == "probe":
        if signature in family_state.get("queued_probe_signatures", []):
            family_state["queued_probe_signatures"] = [
                value for value in family_state["queued_probe_signatures"] if value != signature
            ]
        if signature and signature not in family_state.get("tried_probe_signatures", []):
            family_state.setdefault("tried_probe_signatures", []).append(signature)
        total_probes = len(family_cfg.get("cheap_probes", []))
        family_state["remaining_cheap_probes"] = max(
            0,
            total_probes
            - len(family_state.get("tried_probe_signatures", []))
            - len(family_state.get("queued_probe_signatures", [])),
        )
    rerun_cfg = state["evaluation_config"].get("rerun_policy", {})
    min_reruns = int(rerun_cfg.get("min_reruns_for_promotion", 2))
    max_relative_std = float(rerun_cfg.get("max_relative_std", 0.05))
    suspicious_margin = float(rerun_cfg.get("suspicious_improvement_margin", 0.02))
    invalid_fast_margin = float(rerun_cfg.get("invalid_fast_margin", 0.02))

    prior_family = state["frontier"].get("family_champions", {}).get(family_name, {})
    prior_search = float(prior_family.get("search_eval", -math.inf) or -math.inf)
    prior_selection = float(prior_family.get("selection_eval", -math.inf) or -math.inf)

    candidate_evals = [
        row for row in state["evaluation_rows"] if row.get("candidate_id") == candidate_id
    ]
    search_scores = [row["search_eval"] for row in candidate_evals if row.get("search_eval") is not None]
    selection_scores = [row["selection_eval"] for row in candidate_evals if row.get("selection_eval") is not None]
    valid_runs = [row.get("valid", False) for row in candidate_evals]

    relative_std = None
    if len(selection_scores) >= 2:
        mean = sum(selection_scores) / len(selection_scores)
        variance = sum((value - mean) ** 2 for value in selection_scores) / len(selection_scores)
        relative_std = (math.sqrt(variance) / abs(mean)) if abs(mean) > 1e-9 else 0.0
    stability = {
        "runs": len(candidate_evals),
        "stable": relative_std is None or relative_std <= max_relative_std,
        "relative_std": relative_std,
    }
    candidate["stability"] = stability
    candidate["search_eval"] = sum(search_scores) / len(search_scores) if search_scores else None
    candidate["selection_eval"] = sum(selection_scores) / len(selection_scores) if selection_scores else None
    candidate["final_eval"] = selection_scores[-1] if selection_scores else None

    promotable = (
        candidate["selection_eval"] is not None
        and all(valid_runs)
        and candidate["selection_eval"] > prior_selection + suspicious_margin
    )
    invalid_fast = (
        not all(valid_runs)
        and candidate["search_eval"] is not None
        and candidate["search_eval"] > prior_search + invalid_fast_margin
    )

    if promotable and len(candidate_evals) < min_reruns:
        rerun_job = copy.deepcopy(matching_job)
        rerun_job["job_id"] = f"job_{candidate_id}_{matching_job['attempt'] + 1}"
        rerun_job["attempt"] = matching_job["attempt"] + 1
        rerun_job["status"] = "queued"
        rerun_job["queued_at"] = now_iso()
        rerun_job["leased_at"] = None
        rerun_job["worker_id"] = None
        state["jobs"]["queued"].append(rerun_job)
        candidate["status"] = "evaluating"
    elif invalid_fast:
        candidate["status"] = "invalidated"
        candidate["suspicion"] = "invalid_fast"
        enqueue_unique(state["frontier"]["audit_queue"], candidate_id)
        enqueue_unique(state["frontier"]["invalid_fast_candidates"], candidate_id)
    elif promotable and stability["stable"]:
        candidate["status"] = "promoted"
        promote_candidate(state, candidate)
        family_state["plateau_counter"] = 0
    elif promotable:
        candidate["status"] = "rejected"
        candidate["suspicion"] = "unstable_frontier"
        enqueue_unique(state["frontier"]["audit_queue"], candidate_id)
        enqueue_unique(state["frontier"]["unstable_candidates"], candidate_id)
    else:
        candidate["status"] = "rejected"
        family_state["plateau_counter"] = int(family_state.get("plateau_counter", 0)) + 1

    matching_job["status"] = "finished"
    matching_job["finished_at"] = now_iso()
    state["jobs"]["leased"] = [job for job in state["jobs"]["leased"] if job["job_id"] != matching_job["job_id"]]
    state["jobs"]["finished"].append(matching_job)

    if matching_job.get("worker_id"):
        worker = state["workers"]["workers"][matching_job["worker_id"]]
        worker["status"] = "idle"
        worker["current_job_id"] = None
        worker["current_candidate_id"] = None
        worker["leased_at"] = None
        worker["last_heartbeat_at"] = now_iso()

    append_candidate(lab_root, candidate)
    state["candidates"][candidate_id] = candidate
    append_coordination_log(
        lab_root,
        "experiment_log.md",
        (
            f"- [{now_iso()}] `{candidate_id}` -> {candidate['status']} | "
            f"family={family_name} | search={candidate.get('search_eval')} | "
            f"selection={candidate.get('selection_eval')} | finding={candidate.get('finding') or 'none'}"
        ),
    )
    state["runtime"]["step_count"] = int(state["runtime"].get("step_count", 0) or 0) + 1
    state["runtime"]["updated_at"] = now_iso()
    state["runtime"]["last_supervisor_action"] = f"completed {candidate_id}"
    state["runtime"]["status"] = "idle"
    if family_state.get("plateau_counter", 0) >= int(
        family_cfg.get("frame_break", {}).get(
            "plateau_window",
            state["runtime_config"].get("plateau", {}).get("window", 6),
        )
    ):
        if not has_pending_runtime_work(state):
            state["frontier"]["frame_break_required"] = True
            state["runtime"]["active_phase"] = "frame_break_needed"
            state["runtime"]["stagnation_counter"] = int(state["runtime"].get("stagnation_counter", 0) or 0) + 1
        else:
            state["runtime"]["active_phase"] = "supervisor"
    else:
        state["runtime"]["active_phase"] = "supervisor"

    save_runtime_files(lab_root, state)
    maybe_checkpoint(lab_root, state)
    return candidate


def enqueue_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def promote_candidate(state: dict[str, Any], candidate: dict[str, Any]) -> None:
    frontier = state["frontier"]
    runtime_cfg = state["runtime_config"]
    defaults = family_defaults(runtime_cfg)
    family_name = candidate["family"]
    candidate_summary = {
        "candidate_id": candidate["candidate_id"],
        "family": family_name,
        "selection_eval": candidate["selection_eval"],
        "search_eval": candidate["search_eval"],
        "operator_type": candidate["operator_type"],
    }
    frontier["family_champions"][family_name] = candidate_summary
    if frontier.get("global_champion") is None or float(candidate["selection_eval"] or -math.inf) > float(
        frontier["global_champion"].get("selection_eval", -math.inf) or -math.inf
    ):
        frontier["global_champion"] = candidate_summary

    global_archive = frontier["elite_archive"].setdefault("global", [])
    family_archive = frontier["elite_archive"].setdefault("families", {}).setdefault(family_name, [])
    global_archive.append(candidate_summary)
    family_archive.append(candidate_summary)
    global_archive.sort(key=lambda item: item.get("selection_eval") or -math.inf, reverse=True)
    family_archive.sort(key=lambda item: item.get("selection_eval") or -math.inf, reverse=True)
    del global_archive[defaults["global_top_k"] :]
    del family_archive[defaults["family_top_k"] :]

    family_state = frontier["family_funding"][family_name]
    minted = defaults["promote_credit"]
    if candidate["stability"].get("stable"):
        minted += defaults["stable_credit"]
    if candidate["operator_type"] in {"crossover", "frame_break_spawn"}:
        minted += defaults["novelty_credit"]
    family_state["credits"] += minted
    family_state["minted"] += minted
    family_state["last_promoted_at"] = now_iso()


def maybe_checkpoint(lab_root: Path, state: dict[str, Any]) -> None:
    interval = int(state["runtime_config"].get("checkpoint_interval", 12))
    step_count = int(state["runtime"].get("step_count", 0) or 0)
    if interval <= 0 or step_count <= 0 or step_count % interval != 0:
        return
    payload = {
        "checkpoint_at": now_iso(),
        "step_count": step_count,
        "global_champion": state["frontier"].get("global_champion"),
        "audit_queue": list(state["frontier"].get("audit_queue", [])),
        "family_credits": {
            name: family_state.get("credits", 0)
            for name, family_state in state["frontier"].get("family_funding", {}).items()
        },
        "queued_jobs": len(state["jobs"].get("queued", [])),
        "leased_jobs": len(state["jobs"].get("leased", [])),
    }
    append_checkpoint(lab_root, payload)
    state["runtime"]["last_checkpoint_at"] = payload["checkpoint_at"]


def reap_orphans(lab_root: Path, state: dict[str, Any]) -> int:
    requeued = 0
    now = datetime_from_iso(now_iso()).timestamp()
    leased_jobs = list(state["jobs"].get("leased", []))
    remaining: list[dict[str, Any]] = []
    for job in leased_jobs:
        worker_id = job.get("worker_id")
        worker = state["workers"]["workers"].get(worker_id, {})
        timeout = int(worker.get("lease_timeout_seconds", 1800))
        leased_at = parse_iso(job.get("leased_at"))
        if leased_at and now - leased_at > timeout:
            job["status"] = "queued"
            job["queued_at"] = now_iso()
            job["leased_at"] = None
            job["worker_id"] = None
            state["jobs"]["queued"].append(job)
            if worker:
                worker["status"] = "idle"
                worker["current_job_id"] = None
                worker["current_candidate_id"] = None
                worker["leased_at"] = None
            candidate = state["candidates"].get(job["candidate_id"])
            if candidate:
                candidate["status"] = "queued"
                candidate["updated_at"] = now_iso()
                append_candidate(lab_root, candidate)
            requeued += 1
        else:
            remaining.append(job)
    state["jobs"]["leased"] = remaining
    state["jobs"]["updated_at"] = now_iso()
    save_runtime_files(lab_root, state)
    return requeued


def summary_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_count": state["runtime"].get("step_count", 0),
        "active_phase": state["runtime"].get("active_phase"),
        "global_champion": state["frontier"].get("global_champion"),
        "queued_jobs": len(state["jobs"].get("queued", [])),
        "leased_jobs": len(state["jobs"].get("leased", [])),
        "audit_queue": state["frontier"].get("audit_queue", []),
        "invalid_fast_candidates": state["frontier"].get("invalid_fast_candidates", []),
        "pending_expansion": state["frontier"].get("pending_expansion"),
        "family_credits": {
            name: family_state.get("credits", 0)
            for name, family_state in state["frontier"].get("family_funding", {}).items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="labrat runtime controller")
    parser.add_argument("--lab-dir", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("bootstrap-runtime")

    summary = subparsers.add_parser("summary")
    summary.add_argument("--json", action="store_true")

    dispatch = subparsers.add_parser("dispatch")
    dispatch.add_argument("--queue-depth", type=int, default=None)

    lease = subparsers.add_parser("lease")
    lease.add_argument("--worker-id", required=True)

    complete = subparsers.add_parser("complete")
    complete.add_argument("--candidate-id", required=True)
    complete.add_argument("--result", type=Path, required=True)
    complete.add_argument("--worker-id", default=None)

    subparsers.add_parser("reap")

    args = parser.parse_args(argv)
    lab_root = args.lab_dir.resolve()

    if args.command == "bootstrap-runtime":
        state = bootstrap_runtime(lab_root)
        created = top_up_queue(lab_root, state)
        save_runtime_files(lab_root, state)
        print(f"Bootstrapped runtime at {lab_root}")
        print(f"Queued initial jobs: {created}")
        return 0

    state = load_state(lab_root)
    if args.command == "summary":
        payload = summary_payload(state)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"step_count: {payload['step_count']}")
            print(f"active_phase: {payload['active_phase']}")
            print(f"queued_jobs: {payload['queued_jobs']}")
            print(f"leased_jobs: {payload['leased_jobs']}")
            print(f"audit_queue: {', '.join(payload['audit_queue']) or 'none'}")
            print(f"family_credits: {payload['family_credits']}")
            print(f"global_champion: {payload['global_champion']}")
        return 0

    if args.command == "dispatch":
        created = top_up_queue(lab_root, state, args.queue_depth)
        save_runtime_files(lab_root, state)
        print(json.dumps({"queued_created": created, **summary_payload(state)}, indent=2))
        return 0

    if args.command == "lease":
        job = lease_job(lab_root, state, args.worker_id)
        if job is None:
            print("{}")
            return 0
        print(json.dumps(job, indent=2))
        return 0

    if args.command == "complete":
        candidate = complete_job(lab_root, state, args.candidate_id, args.result.resolve(), args.worker_id)
        print(json.dumps(candidate, indent=2))
        return 0

    if args.command == "reap":
        count = reap_orphans(lab_root, state)
        print(json.dumps({"requeued": count}, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
