#!/usr/bin/env python3
"""Shared helpers for deep-research-first lab scaffolds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


PLACEHOLDER_TOKEN = "LABRAT_PLACEHOLDER"
DEFAULT_SCOUT_THRESHOLD = 4
DEFAULT_EXPANSION_WINDOW = 8
DEFAULT_SMALL_DELTA = 0.005
CHECKPOINT_INTERVAL = 15


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with open(path) as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_yaml(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with open(path) as f:
        return yaml.safe_load(f) or ({} if default is None else default)


def load_lab_state(lab_root: Path) -> dict[str, Any]:
    state_dir = lab_root / "state"
    branches_config = load_yaml(lab_root / "branches.yaml", {})
    beliefs = load_json(state_dir / "branch_beliefs.json", {"branches": {}})
    budget = load_json(state_dir / "budget.json", {})
    cycle_counter = load_json(state_dir / "cycle_counter.json", {})
    champions = load_json(state_dir / "champions.json", {})
    active_agents = load_json(state_dir / "active_agents.json", {"agents": {}})
    experiments = load_jsonl(state_dir / "experiment_log.jsonl")
    return {
        "branches_config": branches_config,
        "branch_beliefs": beliefs,
        "budget": budget,
        "cycle_counter": cycle_counter,
        "champions": champions,
        "active_agents": active_agents,
        "experiments": experiments,
        "state_dir_exists": state_dir.exists(),
    }


def scored_experiments(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        exp
        for exp in state.get("experiments", [])
        if exp.get("composite_score") is not None and exp.get("verdict") not in {"DIAGNOSTIC", "CRASHED"}
    ]


def find_readiness_issues(lab_root: Path) -> list[str]:
    issues: list[str] = []

    branches_path = lab_root / "branches.yaml"
    if not branches_path.exists():
        issues.append("Missing branches.yaml.")
    else:
        text = branches_path.read_text()
        if PLACEHOLDER_TOKEN in text:
            issues.append(
                "branches.yaml still contains scaffold placeholders. Replace every "
                f"`{PLACEHOLDER_TOKEN}` value with a real mission, baseline, and branch search space."
            )

    brief_path = lab_root / "research_brief.md"
    if not brief_path.exists():
        issues.append("Missing research_brief.md.")
    elif PLACEHOLDER_TOKEN in brief_path.read_text():
        issues.append("research_brief.md is still a scaffold placeholder.")

    sources_path = lab_root / "research_sources.md"
    if not sources_path.exists():
        issues.append("Missing research_sources.md.")
    elif PLACEHOLDER_TOKEN in sources_path.read_text():
        issues.append("research_sources.md is still a scaffold placeholder.")

    return issues


def scout_threshold(config: dict[str, Any]) -> int:
    return (
        config.get("external_research", {})
        .get("scout_trigger", {})
        .get("consecutive_non_improvements", DEFAULT_SCOUT_THRESHOLD)
    )


def max_stale_cycles(config: dict[str, Any]) -> int:
    return config.get("budget_rules", {}).get("max_stale_cycles", 8)


def active_branch_names(state: dict[str, Any]) -> list[str]:
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    budget = state.get("budget", {})
    names: list[str] = []
    for name, belief in beliefs.items():
        status = belief.get("status", "active")
        if status in {"exhausted", "converged", "blocked"}:
            continue
        if budget.get(name, 0) <= 0:
            continue
        names.append(name)
    return names


def exhausted_branch_names(state: dict[str, Any]) -> list[str]:
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    return [
        name
        for name, belief in beliefs.items()
        if belief.get("status") in {"exhausted", "converged"}
    ]


def find_stuck_branches(state: dict[str, Any]) -> list[str]:
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    experiments = state.get("experiments", [])
    threshold = scout_threshold(state.get("branches_config", {}))
    stuck: list[str] = []

    for name, belief in beliefs.items():
        if belief.get("status") in {"blocked", "exhausted", "converged"}:
            continue
        branch_runs = [
            exp
            for exp in experiments
            if exp.get("branch") == name and exp.get("verdict") and exp.get("verdict") != "DIAGNOSTIC"
        ]
        if len(branch_runs) < threshold:
            continue
        if all(exp.get("verdict") != "PROMOTE" for exp in branch_runs[-threshold:]):
            stuck.append(name)

    return stuck


def find_invalid_fast_branches(
    state: dict[str, Any],
    *,
    window: int = DEFAULT_EXPANSION_WINDOW,
    speedup_margin: float = 1.05,
) -> list[str]:
    experiments = state.get("experiments", [])
    if not experiments:
        return []

    prod = state.get("champions", {}).get("production_champion", {})
    champion_speedup = float(prod.get("scores", {}).get("speedup", 0.0) or 0.0)
    if champion_speedup <= 0:
        champion_speedup = 1.0

    suspicious: list[str] = []
    seen: set[str] = set()
    for exp in experiments[-window:]:
        branch = exp.get("branch")
        if not branch or branch in seen:
            continue
        valid = exp.get("valid")
        speedup = float(exp.get("speedup", 0.0) or 0.0)
        verdict = exp.get("verdict")
        if valid is False and verdict == "REJECT" and speedup >= champion_speedup * speedup_margin:
            suspicious.append(branch)
            seen.add(branch)
    return suspicious


def find_audit_branches(state: dict[str, Any]) -> list[str]:
    return find_invalid_fast_branches(state)


def recent_small_deltas(state: dict[str, Any], *, window: int = DEFAULT_EXPANSION_WINDOW) -> bool:
    experiments = scored_experiments(state)
    if len(experiments) < window:
        return False

    recent = experiments[-window:]
    scores = [exp.get("composite_score") for exp in recent if exp.get("composite_score") is not None]
    if not scores:
        return False

    best = max(scores)
    worst = min(scores)
    no_recent_promotes = all(exp.get("verdict") != "PROMOTE" for exp in recent[-min(4, len(recent)):])
    return abs(best - worst) < DEFAULT_SMALL_DELTA or no_recent_promotes


def exhausted_majority(state: dict[str, Any]) -> bool:
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    if not beliefs:
        return False
    exhausted = exhausted_branch_names(state)
    return len(exhausted) * 2 >= len(beliefs)


def determine_next_phase(lab_root: Path, state: dict[str, Any] | None = None) -> str:
    issues = find_readiness_issues(lab_root)
    if issues:
        return "design"

    state = state or load_lab_state(lab_root)
    counter = state.get("cycle_counter", {})
    cycle = counter.get("cycle", 0)
    last_transition = counter.get("last_transition")
    frontier_state = counter.get("frontier_state")

    if cycle > 0 and cycle % CHECKPOINT_INTERVAL == 0:
        return "checkpoint"
    if find_audit_branches(state):
        return "audit"
    if frontier_state == "pending_frame_break":
        if last_transition == "frame_break":
            return "expansion"
        if last_transition == "expansion":
            return "cycle"
        return "frame_break"
    if exhausted_majority(state) or recent_small_deltas(state):
        if last_transition == "frame_break":
            return "expansion"
        if last_transition == "expansion":
            return "cycle"
        return "frame_break"
    if find_stuck_branches(state):
        return "scout"
    return "cycle"


def summarize_lab(lab_root: Path) -> dict[str, Any]:
    state = load_lab_state(lab_root)
    summary = {
        "lab_root": str(lab_root),
        "ready": not find_readiness_issues(lab_root),
        "readiness_issues": find_readiness_issues(lab_root),
        "bootstrapped": state.get("state_dir_exists", False),
        "cycle": state.get("cycle_counter", {}).get("cycle"),
        "active_branches": active_branch_names(state),
        "stuck_branches": find_stuck_branches(state),
        "audit_branches": find_audit_branches(state),
        "invalid_fast_branches": find_invalid_fast_branches(state),
        "exhausted_branches": exhausted_branch_names(state),
        "next_phase": determine_next_phase(lab_root, state),
        "active_agents": sorted(state.get("active_agents", {}).get("agents", {}).keys()),
        "max_stale_cycles": max_stale_cycles(state.get("branches_config", {})),
    }
    return summary
