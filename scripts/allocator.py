#!/usr/bin/env python3
"""Shared allocation logic for labrat.

Used by both the orchestrator (via LLM) and the batch_runner (via Python).
Extracts the UCB1-inspired branch selection, diminishing returns detection,
semantic dedup, and convergence checks into reusable functions.

Usage:
    from allocator import select_branches, detect_diminishing_returns, check_convergence
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def load_state(lab_dir: Path) -> dict[str, Any]:
    """Load all state files into a single dict."""
    state_dir = lab_dir / "state"
    state = {}
    for name in ["cycle_counter", "branch_beliefs", "champions", "budget"]:
        path = state_dir / f"{name}.json"
        if path.exists():
            with open(path) as f:
                state[name] = json.load(f)
    # Load experiment log
    log_path = state_dir / "experiment_log.jsonl"
    if log_path.exists():
        with open(log_path) as f:
            state["experiments"] = [json.loads(l) for l in f if l.strip()]
    else:
        state["experiments"] = []
    return state


def compute_priority(
    branch_name: str,
    beliefs: dict,
    current_cycle: int,
    budget: dict,
) -> float | None:
    """Compute UCB1-inspired priority for a branch.

    Returns None if branch should be skipped (exhausted, no budget).

    priority = 0.3 * ev + 0.4 * uncertainty + 0.3 * recency_bonus
    """
    b = beliefs.get("branches", {}).get(branch_name, {})
    if b.get("status") in ("exhausted", "converged"):
        return None
    if budget.get(branch_name, 0) <= 0:
        return None

    ev = b.get("current_ev", 0.0)
    n = b.get("n_experiments", 0)
    uncertainty = 1.0 / math.sqrt(1 + n)
    last_cycle = b.get("last_explored_cycle", 0)
    recency_bonus = min(1.0, (current_cycle - last_cycle) / 3.0)

    return 0.3 * ev + 0.4 * uncertainty + 0.3 * recency_bonus


def select_branches(
    state: dict,
    max_branches: int | None = None,
) -> list[tuple[str, float]]:
    """Select branches to explore this cycle, ranked by priority.

    Returns list of (branch_name, priority) tuples, highest priority first.

    Implements:
    - UCB1-inspired priority formula
    - Max-stale rule: branches unvisited for 10+ cycles get picked immediately
    - Budget filtering: skip branches with 0 budget
    - Exhaustion filtering: skip exhausted/converged branches
    """
    beliefs = state.get("branch_beliefs", {})
    budget = state.get("budget", {})
    cycle = state.get("cycle_counter", {}).get("cycle", 0)

    candidates = []
    stale = []

    for name in beliefs.get("branches", {}):
        priority = compute_priority(name, beliefs, cycle, budget)
        if priority is None:
            continue

        b = beliefs["branches"][name]
        last_cycle = b.get("last_explored_cycle", 0)

        # Max-stale rule: 10+ cycles since last visit -> immediate pick
        if cycle - last_cycle >= 10 and b.get("status") == "active":
            stale.append((name, 999.0))  # sentinel priority
        else:
            candidates.append((name, priority))

    # Sort by priority desc, then by n_experiments asc (prefer less explored)
    candidates.sort(key=lambda x: (
        -x[1],
        beliefs["branches"][x[0]].get("n_experiments", 0),
        -budget.get(x[0], 0),
    ))

    # Stale branches go first
    result = stale + candidates

    if max_branches is not None:
        result = result[:max_branches]

    return result


def detect_diminishing_returns(
    experiments: list[dict],
    window: int = 8,
    epsilon: float = 0.005,
) -> bool:
    """Detect if the lab is producing diminishing returns.

    Returns True if the last `window` experiments across ALL branches
    have composite_score_delta < epsilon. This catches the subtle
    "improving but not meaningfully" failure mode.
    """
    scored = [
        e for e in experiments
        if e.get("verdict") in ("PROMOTE", "MARGINAL", "REJECT")
        and e.get("composite_score") is not None
        and e.get("champion_score") is not None
    ]

    if len(scored) < window:
        return False

    recent = scored[-window:]
    deltas = []
    for e in recent:
        delta = abs(e.get("composite_score", 0) - e.get("champion_score", 0))
        deltas.append(delta)

    return all(d < epsilon for d in deltas)


def detect_stuck_branches(
    experiments: list[dict],
    beliefs: dict,
    threshold: int = 4,
) -> list[str]:
    """Identify branches with N+ consecutive non-improvements.

    Uses threshold=4 (raised from 3 per assessment recommendation).
    Also checks for semantic convergence within a branch.
    """
    stuck = []
    for name, b in beliefs.get("branches", {}).items():
        if b.get("status") in ("exhausted", "converged"):
            continue
        if b.get("n_experiments", 0) < threshold:
            continue

        branch_exps = [
            e for e in experiments
            if e.get("branch") == name and e.get("verdict")
        ]
        if len(branch_exps) < threshold:
            continue

        last_n = branch_exps[-threshold:]
        if all(e["verdict"] != "PROMOTE" for e in last_n):
            stuck.append(name)

    return stuck


def detect_flat_axes(
    experiments: list[dict],
    branch: str,
    epsilon: float = 0.005,
) -> list[str]:
    """Identify axes within a branch where variation produces no change.

    Looks at experiments that varied a specific delta_key and checks
    if all results are within epsilon of each other.
    """
    branch_exps = [e for e in experiments if e.get("branch") == branch]
    if len(branch_exps) < 3:
        return []

    # Group by delta key
    by_key: dict[str, list[float]] = {}
    for e in branch_exps:
        delta = e.get("delta", "")
        score = e.get("composite_score")
        if score is None:
            continue
        # Extract delta key from description (heuristic)
        if isinstance(delta, dict):
            key = delta.get("key", "unknown")
        elif isinstance(delta, str) and ":" in delta:
            key = delta.split(":")[0].strip()
        else:
            key = "unknown"
        by_key.setdefault(key, []).append(score)

    flat = []
    for key, scores in by_key.items():
        if len(scores) >= 2:
            spread = max(scores) - min(scores)
            if spread < epsilon:
                flat.append(key)

    return flat


def check_convergence(state: dict) -> tuple[bool, str]:
    """Check if the lab has converged.

    Returns (converged, reason).

    Convergence conditions (ALL must be true):
    1. All active branches are stuck or exhausted
    2. Production champion hasn't changed in 5+ cycles
    3. Diminishing returns detected across all branches
    """
    beliefs = state.get("branch_beliefs", {})
    experiments = state.get("experiments", [])
    budget = state.get("budget", {})
    cycle = state.get("cycle_counter", {}).get("cycle", 0)

    # Check 1: All branches stuck or exhausted
    active_branches = [
        name for name, b in beliefs.get("branches", {}).items()
        if b.get("status") not in ("exhausted", "converged")
        and budget.get(name, 0) > 0
    ]
    stuck = detect_stuck_branches(experiments, beliefs)
    unstuck_active = [b for b in active_branches if b not in stuck]

    if unstuck_active:
        return False, f"Active unstuck branches: {unstuck_active}"

    # Check 2: Champion stability
    promotes = [e for e in experiments if e.get("verdict") == "PROMOTE"]
    if promotes:
        last_promote_cycle = max(e.get("cycle", 0) for e in promotes)
        if cycle - last_promote_cycle < 5:
            return False, f"Champion changed {cycle - last_promote_cycle} cycles ago (need 5+)"

    # Check 3: Diminishing returns
    if not detect_diminishing_returns(experiments):
        return False, "Recent experiments still showing meaningful deltas"

    return True, "All branches stuck/exhausted, champion stable 5+ cycles, diminishing returns"


def detect_surprise(
    experiment: dict,
    experiments: list[dict],
    sigma_threshold: float = 3.0,
) -> bool:
    """Detect if an experiment result is surprisingly good or bad.

    Returns True if the composite_score is >sigma_threshold standard
    deviations from the mean of recent experiments.
    """
    score = experiment.get("composite_score")
    if score is None:
        return False

    recent_scores = [
        e.get("composite_score", 0)
        for e in experiments[-20:]
        if e.get("composite_score") is not None
    ]
    if len(recent_scores) < 5:
        return False

    import statistics
    mean = statistics.mean(recent_scores)
    stdev = statistics.stdev(recent_scores)
    if stdev < 0.001:
        return False

    z_score = abs(score - mean) / stdev
    return z_score > sigma_threshold


def generate_capstone_combinations(
    champions: dict,
    max_combinations: int = 16,
) -> list[dict]:
    """Generate 2^N factorial combinations of branch winners.

    For capstone branches, automatically combine the best configs
    from each branch. Limits to max_combinations using fractional
    factorial design when N is large.
    """
    branch_winners = {}
    for name, champ in champions.get("branches", {}).items():
        if name == "capstone":
            continue
        if champ.get("scores") and champ["scores"].get("composite_score", 0) > 0:
            branch_winners[name] = champ

    if len(branch_winners) <= 1:
        return []

    branches = list(branch_winners.keys())
    n = len(branches)

    # For small N, full factorial. For large N, pick top combinations.
    if 2**n <= max_combinations:
        # Full 2^N: include/exclude each branch winner
        combinations = []
        for mask in range(1, 2**n):
            combo = {}
            included = []
            for i, branch in enumerate(branches):
                if mask & (1 << i):
                    included.append(branch)
                    # Would need actual config merging logic here
                    combo[branch] = branch_winners[branch].get("experiment_id", "")
            if len(included) >= 2:  # At least 2 branches combined
                combinations.append({
                    "name": f"capstone_{'_'.join(sorted(included))}",
                    "branches_combined": included,
                    "source_experiments": combo,
                })
        return combinations[:max_combinations]
    else:
        # Fractional factorial: pick top N pairs + the full combination
        combinations = []
        # All pairs
        for i, b1 in enumerate(branches):
            for b2 in branches[i+1:]:
                combinations.append({
                    "name": f"capstone_{b1}_{b2}",
                    "branches_combined": [b1, b2],
                    "source_experiments": {
                        b1: branch_winners[b1].get("experiment_id", ""),
                        b2: branch_winners[b2].get("experiment_id", ""),
                    },
                })
        # Full combination
        combinations.append({
            "name": "capstone_all",
            "branches_combined": branches,
            "source_experiments": {
                b: branch_winners[b].get("experiment_id", "")
                for b in branches
            },
        })
        return combinations[:max_combinations]


if __name__ == "__main__":
    """CLI for testing allocation logic."""
    import argparse

    parser = argparse.ArgumentParser(description="Labrat branch allocator")
    parser.add_argument("--lab-dir", type=Path, required=True)
    parser.add_argument("--max-branches", type=int, default=None)
    parser.add_argument("--check-convergence", action="store_true")
    parser.add_argument("--check-stuck", action="store_true")
    parser.add_argument("--check-diminishing", action="store_true")
    args = parser.parse_args()

    state = load_state(args.lab_dir)

    if args.check_convergence:
        converged, reason = check_convergence(state)
        print(f"Converged: {converged}")
        print(f"Reason: {reason}")
    elif args.check_stuck:
        stuck = detect_stuck_branches(
            state["experiments"],
            state.get("branch_beliefs", {}),
        )
        print(f"Stuck branches: {stuck or 'none'}")
    elif args.check_diminishing:
        dim = detect_diminishing_returns(state["experiments"])
        print(f"Diminishing returns: {dim}")
    else:
        selected = select_branches(state, args.max_branches)
        print("Selected branches (priority):")
        for name, priority in selected:
            budget = state.get("budget", {}).get(name, 0)
            n_exp = state.get("branch_beliefs", {}).get("branches", {}).get(name, {}).get("n_experiments", 0)
            print(f"  {name}: priority={priority:.3f} budget={budget} experiments={n_exp}")
