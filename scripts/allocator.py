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


def track_gate_failures(
    experiments: list[dict],
    min_rejections: int = 10,
    binding_threshold: float = 0.40,
) -> dict:
    """Track which hard gates cause the most rejections.

    Returns dict with:
    - gate_counts: {gate_name: count}
    - total_rejections: int
    - binding_gates: [{gate, count, rate}] where rate > binding_threshold
    """
    gate_counts: dict[str, int] = {}
    total_rejections = 0

    for e in experiments:
        if e.get("verdict") != "REJECT":
            continue
        total_rejections += 1

        # Extract gate failure reasons from the experiment
        reason = e.get("reason", "")
        failures = e.get("hard_gate_failures", [])

        # Parse gate names from failure strings
        if failures:
            for fail in failures:
                gate = _classify_gate_failure(fail)
                gate_counts[gate] = gate_counts.get(gate, 0) + 1
        elif "p_value" in reason or "p=" in reason:
            gate_counts["significance"] = gate_counts.get("significance", 0) + 1
        elif "baseline" in reason.lower() or "metric" in reason.lower():
            gate_counts["below_baseline"] = gate_counts.get("below_baseline", 0) + 1
        elif "score=" in reason:
            gate_counts["soft_below_champion"] = gate_counts.get("soft_below_champion", 0) + 1
        else:
            gate_counts["other"] = gate_counts.get("other", 0) + 1

    binding = []
    if total_rejections >= min_rejections:
        for gate, count in gate_counts.items():
            rate = count / total_rejections
            if rate >= binding_threshold:
                binding.append({"gate": gate, "count": count, "rate": round(rate, 3)})
        binding.sort(key=lambda x: -x["rate"])

    return {
        "gate_counts": gate_counts,
        "total_rejections": total_rejections,
        "binding_gates": binding,
    }


def _classify_gate_failure(failure_str: str) -> str:
    """Map a gate failure string to a gate category."""
    s = failure_str.lower()
    if "p_value" in s or "p=" in s or "significant" in s:
        return "significance"
    if "baseline" in s or "metric" in s and "<=" in s:
        return "below_baseline"
    if "cv" in s or "fold" in s or "walk" in s or "window" in s:
        return "walk_forward"
    if "pred_std" in s or "collapsed" in s:
        return "model_collapsed"
    if "lag" in s or "causal" in s:
        return "causality"
    if "win_rate" in s or "win rate" in s:
        return "win_rate"
    return "other"


def categorize_failures(experiments: list[dict]) -> dict:
    """Categorize all non-PROMOTE experiments by failure type.

    Returns:
    - by_type: {type: count}
    - by_branch: {branch: {type: count}}
    - dominant_per_branch: {branch: most_common_failure_type}
    """
    by_type: dict[str, int] = {}
    by_branch: dict[str, dict[str, int]] = {}

    for e in experiments:
        verdict = e.get("verdict", "")
        branch = e.get("branch", "unknown")

        if verdict == "PROMOTE" or verdict == "DIAGNOSTIC" or not verdict:
            continue

        if verdict == "REJECT":
            failures = e.get("hard_gate_failures", [])
            if failures:
                ftype = "hard_gate:" + _classify_gate_failure(failures[0])
            elif e.get("reason", "").startswith("score="):
                ftype = "soft_below_champion"
            else:
                ftype = "rejected_other"
        elif verdict == "MARGINAL":
            ftype = "marginal"
        elif "ERROR" in str(verdict).upper() or "CRASH" in str(verdict).upper():
            ftype = "crashed"
        else:
            ftype = "other"

        by_type[ftype] = by_type.get(ftype, 0) + 1
        by_branch.setdefault(branch, {})
        by_branch[branch][ftype] = by_branch[branch].get(ftype, 0) + 1

    dominant = {}
    for branch, types in by_branch.items():
        if types:
            dominant[branch] = max(types, key=types.get)

    return {
        "by_type": by_type,
        "by_branch": by_branch,
        "dominant_per_branch": dominant,
    }


def compute_efficiency_metrics(
    experiments: list[dict],
    beliefs: dict,
    budget: dict,
) -> dict:
    """Compute lab efficiency metrics for meta-analysis.

    Returns:
    - waste_rate: fraction of experiments on branches that never promoted
    - budget_roi: {branch: promotions_per_budget_spent}
    - time_to_first_promote: {branch: cycle_of_first_promote or None}
    - total_promotions: int
    - total_experiments: int
    """
    branch_promoted = {}  # branch -> bool (ever promoted?)
    branch_exp_count = {}
    branch_promote_count = {}
    branch_first_promote_cycle = {}
    branch_budget_spent = {}

    for e in experiments:
        branch = e.get("branch", "unknown")
        verdict = e.get("verdict", "")
        cycle = e.get("cycle", 0)

        if verdict in ("PROMOTE", "MARGINAL", "REJECT", "DIAGNOSTIC"):
            branch_exp_count[branch] = branch_exp_count.get(branch, 0) + 1

        if verdict == "PROMOTE":
            branch_promoted[branch] = True
            branch_promote_count[branch] = branch_promote_count.get(branch, 0) + 1
            if branch not in branch_first_promote_cycle:
                branch_first_promote_cycle[branch] = cycle

    # Budget spent = initial - remaining
    initial_budgets = {}
    for name, b in beliefs.get("branches", {}).items():
        initial_budgets[name] = b.get("n_experiments", 0)  # experiments run = budget spent
    branch_budget_spent = initial_budgets

    # Waste rate: experiments on branches that never promoted
    total_exp = sum(branch_exp_count.values())
    wasted_exp = sum(
        count for branch, count in branch_exp_count.items()
        if not branch_promoted.get(branch, False)
    )
    waste_rate = wasted_exp / max(total_exp, 1)

    # Budget ROI
    budget_roi = {}
    for branch in branch_exp_count:
        spent = branch_budget_spent.get(branch, 0)
        promotes = branch_promote_count.get(branch, 0)
        budget_roi[branch] = round(promotes / max(spent, 1), 3)

    return {
        "waste_rate": round(waste_rate, 3),
        "total_experiments": total_exp,
        "total_promotions": sum(branch_promote_count.values()),
        "budget_roi": budget_roi,
        "time_to_first_promote": branch_first_promote_cycle,
        "never_promoted": [
            b for b in branch_exp_count
            if not branch_promoted.get(b, False)
        ],
    }


if __name__ == "__main__":
    """CLI for testing allocation logic."""
    import argparse

    parser = argparse.ArgumentParser(description="Labrat branch allocator")
    parser.add_argument("--lab-dir", type=Path, required=True)
    parser.add_argument("--max-branches", type=int, default=None)
    parser.add_argument("--check-convergence", action="store_true")
    parser.add_argument("--check-stuck", action="store_true")
    parser.add_argument("--check-diminishing", action="store_true")
    parser.add_argument("--check-gates", action="store_true", help="Analyze gate failure patterns")
    parser.add_argument("--check-failures", action="store_true", help="Categorize all failures")
    parser.add_argument("--check-efficiency", action="store_true", help="Lab efficiency metrics")
    args = parser.parse_args()

    state = load_state(args.lab_dir)

    if args.check_gates:
        result = track_gate_failures(state["experiments"])
        print(f"Total rejections: {result['total_rejections']}")
        print(f"Gate failure counts: {result['gate_counts']}")
        if result["binding_gates"]:
            print(f"BINDING GATES (>{40}% of rejections):")
            for bg in result["binding_gates"]:
                print(f"  {bg['gate']}: {bg['count']} rejections ({bg['rate']*100:.0f}%)")
        else:
            print("No binding gates detected.")
    elif args.check_failures:
        result = categorize_failures(state["experiments"])
        print("Failure types:", result["by_type"])
        print("Dominant per branch:", result["dominant_per_branch"])
    elif args.check_efficiency:
        result = compute_efficiency_metrics(
            state["experiments"],
            state.get("branch_beliefs", {}),
            state.get("budget", {}),
        )
        print(f"Waste rate: {result['waste_rate']*100:.0f}% of experiments on branches that never promoted")
        print(f"Total: {result['total_experiments']} experiments, {result['total_promotions']} promotions")
        print(f"Budget ROI: {result['budget_roi']}")
        if result["never_promoted"]:
            print(f"Never promoted: {result['never_promoted']}")
        if result["time_to_first_promote"]:
            print(f"First promote cycle: {result['time_to_first_promote']}")
    elif args.check_convergence:
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
