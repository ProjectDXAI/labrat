#!/usr/bin/env python3
"""Research scout: prepares context for web-search-driven hypothesis generation.

Identifies stuck branches, generates search queries, writes scout_request.json
files that a Claude Code agent picks up and executes with WebSearch/WebFetch.

Usage:
    # Scout a specific stuck branch
    python scripts/research_scout.py --branch model --lab-dir /path/to/lab

    # Auto-detect and scout all stuck branches
    python scripts/research_scout.py --all-stuck --lab-dir /path/to/lab

    # Full expansion mode: scout even non-stuck branches for new ideas
    python scripts/research_scout.py --expansion --lab-dir /path/to/lab

    # Merge approved proposals back into branches.yaml
    python scripts/research_scout.py --merge --branch model --lab-dir /path/to/lab
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def load_state(lab_dir: Path) -> dict:
    """Load all relevant state files into a single dict."""
    state = {}
    state_dir = lab_dir / "state"

    for name in ["branch_beliefs", "champions", "cycle_counter", "budget"]:
        path = state_dir / f"{name}.json"
        if path.exists():
            with open(path) as f:
                state[name] = json.load(f)

    log_path = state_dir / "experiment_log.jsonl"
    state["experiments"] = []
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    state["experiments"].append(json.loads(line))

    dead_ends_path = lab_dir / "dead_ends.md"
    state["dead_ends_text"] = dead_ends_path.read_text() if dead_ends_path.exists() else ""

    branches_path = lab_dir / "branches.yaml"
    if branches_path.exists():
        with open(branches_path) as f:
            state["branches_config"] = yaml.safe_load(f)
    else:
        state["branches_config"] = {}

    return state


def get_branch_experiments(state: dict, branch: str) -> list[dict]:
    """Filter experiment log to a specific branch, sorted by cycle."""
    exps = [e for e in state["experiments"] if e.get("branch") == branch]
    exps.sort(key=lambda e: e.get("cycle", 0))
    return exps


def find_stuck_branches(state: dict, threshold: int = 3) -> list[str]:
    """Identify branches with N+ consecutive non-improvements."""
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    stuck = []

    for name, b in beliefs.items():
        if b.get("status") in ("blocked", "exhausted"):
            continue
        if b.get("n_experiments", 0) < threshold:
            continue

        branch_exps = [
            e for e in state["experiments"]
            if e.get("branch") == name and e.get("verdict")
        ]
        if len(branch_exps) < threshold:
            continue

        last_n = branch_exps[-threshold:]
        if all(e["verdict"] != "PROMOTE" for e in last_n):
            stuck.append(name)

    return stuck


def find_diminishing_branches(state: dict, delta_threshold: float = 0.005,
                               window: int = 5) -> list[str]:
    """Find branches where recent improvements are too small to matter."""
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    diminishing = []

    for name, b in beliefs.items():
        if b.get("status") in ("blocked", "exhausted"):
            continue

        branch_exps = [
            e for e in state["experiments"]
            if e.get("branch") == name and e.get("verdict") == "PROMOTE"
        ]
        if len(branch_exps) < window:
            continue

        recent_deltas = []
        for exp in branch_exps[-window:]:
            delta = abs(exp.get("composite_score", 0) - exp.get("champion_score", 0))
            recent_deltas.append(delta)

        if recent_deltas and max(recent_deltas) < delta_threshold:
            diminishing.append(name)

    return diminishing


def load_search_history(lab_dir: Path, branch: str) -> list[str]:
    """Load previously executed search queries for dedup."""
    scout_dir = lab_dir / "experiments" / branch / "scout_proposals"
    history = []
    if not scout_dir.exists():
        return history

    for f in scout_dir.glob("scout_*.yaml"):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict) and "search_queries" in data:
                history.extend(data["search_queries"])
        except (yaml.YAMLError, OSError):
            continue

    return history


def best_cycles_from_state(state: dict, lab_dir: Path) -> int | None:
    champions = state.get("champions", {})
    prod = champions.get("production_champion", {})
    result_path = prod.get("result_path")
    if not result_path:
        return None
    resolved = (lab_dir / result_path).resolve() if not Path(result_path).is_absolute() else Path(result_path)
    if not resolved.exists():
        return None
    try:
        with open(resolved) as f:
            data = json.load(f)
        return int(data.get("metrics", {}).get("test", {}).get("cycles"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def latest_frontier_gap(state: dict) -> dict:
    rows = list(reversed(state.get("experiments", [])))
    for row in rows:
        findings = row.get("findings")
        if not isinstance(findings, dict):
            continue
        if findings.get("kind") in {"frontier_gap_audit", "structure_gap_review"}:
            return findings
    return {}


def cheap_probe_families(state: dict) -> list[str]:
    return (
        state.get("branches_config", {})
        .get("exploration_policy", {})
        .get("cheap_probe_families", [])
    )


def build_search_queries(state: dict, branch: str) -> list[str]:
    """Generate targeted search queries based on branch context."""
    config = state.get("branches_config", {})
    mission = config.get("mission", "")
    branch_info = config.get("branches", {}).get(branch, {})
    branch_desc = branch_info.get("description", branch)

    search_terms = (
        config.get("external_research", {})
        .get("search_config", {})
        .get("domain_terms", [])
    )
    if search_terms:
        domain = search_terms[0]
    elif mission:
        domain = " ".join(mission.split()[:8])
    else:
        domain = branch_desc

    # Get the champion config to know what's currently winning
    champions = state.get("champions", {})
    branch_champ = champions.get("branches", {}).get(branch, {})
    champ_id = branch_champ.get("experiment_id", "baseline")

    # Get dead end techniques to search for alternatives
    dead_ends = state.get("dead_ends_text", "")
    dead_techniques = []
    for line in dead_ends.split("\n"):
        line = line.strip()
        if line.startswith("- **") and "**" in line[4:]:
            technique = line[4:line.index("**", 4)]
            dead_techniques.append(technique)

    queries = []

    # Pattern 1: State of the art
    queries.append(f"{domain} state of the art 2025 2026")

    # Pattern 2: Alternatives to dead ends
    for tech in dead_techniques[:2]:
        queries.append(f"{tech} alternatives {domain}")

    # Pattern 3: Metric improvement under constraints
    constraints = []
    budget_info = state.get("budget", {})
    if budget_info.get(branch, 0) < 10:
        constraints.append("low compute budget")
    queries.append(f"improve {branch_desc} {domain} recent papers")

    # Pattern 4: Beyond current approach
    queries.append(f"beyond {champ_id} {domain} novel approaches")

    # Pattern 5: Branch-specific technique search
    queries.append(f"{branch_desc} techniques {domain} 2024 2025")

    # Pattern 6: Cross-domain (only in expansion mode, but include one always)
    queries.append(f"novel {branch} optimization techniques machine learning 2025")

    frontier_gap = latest_frontier_gap(state)
    for family in frontier_gap.get("missing_families", [])[:2]:
        queries.append(f"{domain} {family} recent results")

    for probe in cheap_probe_families(state)[:2]:
        queries.append(f"{domain} {probe} optimization technique")

    return queries


def build_scout_request(state: dict, branch: str, lab_dir: Path,
                         mode: str = "stuck") -> dict:
    """Build the scout_request.json that the Claude Code agent picks up."""
    config = state.get("branches_config", {})
    champions = state.get("champions", {})
    branch_champ = champions.get("branches", {}).get(branch, {})

    branch_exps = get_branch_experiments(state, branch)
    recent = branch_exps[-10:] if len(branch_exps) > 10 else branch_exps

    search_history = load_search_history(lab_dir, branch)
    queries = build_search_queries(state, branch)
    # Remove queries already in history
    queries = [q for q in queries if q not in search_history]

    cycle = state.get("cycle_counter", {}).get("cycle", 0)
    frontier_gap = latest_frontier_gap(state)
    best_cycles = best_cycles_from_state(state, lab_dir)
    invalid_fast_branches = sorted(
        {
            e.get("branch")
            for e in state.get("experiments", [])[-8:]
            if e.get("valid") is False and e.get("verdict") == "REJECT" and e.get("branch")
        }
    )
    search_directives = {
        "audit_first": branch in invalid_fast_branches,
        "cheap_probe_families": cheap_probe_families(state),
        "stuck_branches": find_stuck_branches(state),
        "diminishing_branches": find_diminishing_branches(state),
        "frontier_questions": frontier_gap.get("missing_families", []),
    }

    request = {
        "branch": branch,
        "mode": mode,
        "domain": config.get("mission", "").split(".")[0],
        "mission": config.get("mission", ""),
        "champion_config": branch_champ,
        "dead_ends": state.get("dead_ends_text", ""),
        "recent_experiments": [
            {
                "id": e.get("experiment_id"),
                "delta": e.get("delta"),
                "verdict": e.get("verdict"),
                "score": e.get("composite_score"),
                "cycle": e.get("cycle"),
            }
            for e in recent
        ],
        "constraints": {
            "remaining_budget": state.get("budget", {}).get(branch, 0),
            "current_cycle": cycle,
        },
        "frontier_gap": frontier_gap,
        "best_cycles": best_cycles,
        "invalid_fast_branches": invalid_fast_branches,
        "search_directives": search_directives,
        "search_queries": queries,
        "search_history": search_history,
        "created_at": datetime.now(UTC).isoformat(),
    }

    if mode == "expansion":
        request["proposal_contract"] = {
            "kind": "new_branch",
            "output_file": "experiments/expansion_meta/scout_proposals/expansion_cycle_N.yaml",
            "required_fields": [
                "proposal_id",
                "approved",
                "orthogonality",
                "reason_broken_assumption",
                "source_refs",
                "implementation_todo",
                "branch_name",
                "branch_yaml",
            ],
        }

    return request


def write_scout_request(request: dict, lab_dir: Path) -> Path:
    """Write scout request to disk for the Claude Code agent."""
    branch = request["branch"]
    scout_dir = lab_dir / "experiments" / branch / "scout_proposals"
    scout_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = scout_dir / f"scout_request_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(request, f, indent=2)

    return path


def merge_proposals(lab_dir: Path, branch: str, dry_run: bool = False) -> int:
    """Merge approved scout proposals into branches.yaml search space.

    Reads all scout proposal files, filters to approved ones (those with
    an 'approved: true' field), and appends their configs to the branch's
    search space in branches.yaml.

    Returns the number of proposals merged.
    """
    scout_dir = lab_dir / "experiments" / branch / "scout_proposals"
    if not scout_dir.exists():
        print(f"No scout proposals found for branch '{branch}'")
        return 0

    branches_path = lab_dir / "branches.yaml"
    with open(branches_path) as f:
        branches_config = yaml.safe_load(f)

    if branch not in branches_config.get("branches", {}):
        print(f"Branch '{branch}' not found in branches.yaml")
        return 0

    merged = 0
    for proposal_file in sorted(scout_dir.glob("scout_*.yaml")):
        try:
            with open(proposal_file) as f:
                proposals = yaml.safe_load(f)
        except (yaml.YAMLError, OSError):
            continue

        if not isinstance(proposals, dict):
            continue

        # Handle both single proposal and list-of-proposals formats
        items = proposals.get("proposals", [proposals])
        if not isinstance(items, list):
            items = [items]

        for prop in items:
            if not isinstance(prop, dict):
                continue
            if not prop.get("approved", False):
                continue

            config_overrides = prop.get("experiment_config", {}).get("config_overrides", {})
            if not config_overrides:
                continue

            # Add as a new search space entry
            entry = {
                "delta_key": f"scout.{prop.get('proposal_id', 'unknown')}",
                "values": [config_overrides],
                "source": prop.get("source", "scout"),
                "scout_proposal": True,
            }

            search_space = branches_config["branches"][branch].get("search_space", [])
            # Check for duplicates
            existing_keys = {e.get("delta_key") for e in search_space}
            if entry["delta_key"] not in existing_keys:
                search_space.append(entry)
                merged += 1
                print(f"  Merged: {entry['delta_key']} from {proposal_file.name}")

        branches_config["branches"][branch]["search_space"] = search_space

    if merged > 0 and not dry_run:
        with open(branches_path, "w") as f:
            yaml.dump(branches_config, f, default_flow_style=False, sort_keys=False)
        print(f"\nWrote {merged} new entries to {branches_path}")
    elif merged > 0:
        print(f"\n[dry run] Would write {merged} new entries to {branches_path}")

    return merged


def merge_expansion_proposals(lab_dir: Path, dry_run: bool = False) -> int:
    scout_dir = lab_dir / "experiments" / "expansion_meta" / "scout_proposals"
    if not scout_dir.exists():
        print("No expansion scout proposals found.")
        return 0

    branches_path = lab_dir / "branches.yaml"
    with open(branches_path) as f:
        branches_config = yaml.safe_load(f)

    branches = branches_config.setdefault("branches", {})
    state_dir = lab_dir / "state"
    budget_path = state_dir / "budget.json"
    beliefs_path = state_dir / "branch_beliefs.json"
    champions_path = state_dir / "champions.json"
    budget = {}
    beliefs = {"branches": {}}
    champions = {"branches": {}}
    if budget_path.exists():
        with open(budget_path) as f:
            budget = json.load(f)
    if beliefs_path.exists():
        with open(beliefs_path) as f:
            beliefs = json.load(f)
    if champions_path.exists():
        with open(champions_path) as f:
            champions = json.load(f)
    baseline = branches_config.get("production_baseline", {})
    baseline_entry = {
        "experiment_id": baseline.get("experiment_id", "baseline"),
        "description": baseline.get("description", "Baseline"),
        "scores": None,
        "result_path": None,
    }
    now = datetime.now(UTC).isoformat()
    merged = 0
    for proposal_file in sorted(scout_dir.glob("*.yaml")):
        try:
            with open(proposal_file) as f:
                proposals = yaml.safe_load(f)
        except (yaml.YAMLError, OSError):
            continue

        if not isinstance(proposals, dict):
            continue

        items = proposals.get("proposals", [proposals])
        if not isinstance(items, list):
            items = [items]

        for prop in items:
            if not isinstance(prop, dict) or not prop.get("approved", False):
                continue
            branch_name = prop.get("branch_name")
            branch_yaml = prop.get("branch_yaml")
            if not branch_name or not isinstance(branch_yaml, dict):
                continue
            if branch_name in branches:
                print(f"  Skipped existing branch: {branch_name}")
                continue
            branches[branch_name] = branch_yaml
            budget[branch_name] = int(branch_yaml.get("initial_budget", 0))
            beliefs.setdefault("branches", {})[branch_name] = {
                "n_experiments": 0,
                "n_improvements": 0,
                "current_ev": 0.0,
                "uncertainty": 1.0,
                "last_explored_cycle": 0,
                "best_composite_score": None,
                "status": "exhausted" if int(branch_yaml.get("initial_budget", 0)) == 0 else "active",
                "flat_axes": [],
                "notes": [],
                "experiment_type": branch_yaml.get("experiment_type", "standard"),
            }
            champions.setdefault("branches", {})[branch_name] = baseline_entry.copy()
            merged += 1
            print(f"  Merged new branch: {branch_name} from {proposal_file.name}")

    if merged > 0 and not dry_run:
        with open(branches_path, "w") as f:
            yaml.dump(branches_config, f, default_flow_style=False, sort_keys=False)
        if budget_path.exists():
            with open(budget_path, "w") as f:
                json.dump(budget, f, indent=2)
        if beliefs_path.exists():
            beliefs["updated_at"] = now
            with open(beliefs_path, "w") as f:
                json.dump(beliefs, f, indent=2)
        if champions_path.exists():
            champions["updated_at"] = now
            with open(champions_path, "w") as f:
                json.dump(champions, f, indent=2)
        print(f"\nWrote {merged} new branch entries to {branches_path}")
    elif merged > 0:
        print(f"\n[dry run] Would write {merged} new branch entries to {branches_path}")

    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Research scout: find new experiment ideas for stuck branches"
    )
    parser.add_argument("--branch", type=str, help="Scout a specific branch")
    parser.add_argument("--all-stuck", action="store_true",
                        help="Auto-detect and scout all stuck branches")
    parser.add_argument("--expansion", action="store_true",
                        help="Scout all active branches for new ideas")
    parser.add_argument("--merge", action="store_true",
                        help="Merge approved proposals into branches.yaml")
    parser.add_argument("--merge-expansion", action="store_true",
                        help="Merge approved expansion proposals into new branches")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be merged without writing")
    parser.add_argument(
        "--lab-dir",
        type=str,
        default=str(SCRIPT_ROOT),
        help="Path to the lab root. Defaults to the parent of this scripts directory.",
    )
    parser.add_argument("--stuck-threshold", type=int, default=3,
                        help="Consecutive non-improvements to count as stuck")
    args = parser.parse_args()

    lab_dir = Path(args.lab_dir).resolve()
    if not (lab_dir / "state").exists():
        print(f"ERROR: {lab_dir}/state/ not found. Run bootstrap.py first.")
        sys.exit(1)

    # Merge mode: just merge proposals and exit
    if args.merge_expansion:
        merged = merge_expansion_proposals(lab_dir, dry_run=args.dry_run)
        print(f"Merged {merged} expansion proposals")
        return

    if args.merge:
        if not args.branch:
            print("ERROR: --merge requires --branch")
            sys.exit(1)
        merged = merge_proposals(lab_dir, args.branch, dry_run=args.dry_run)
        print(f"Merged {merged} proposals for branch '{args.branch}'")
        return

    state = load_state(lab_dir)

    # Determine which branches to scout
    branches_to_scout: list[tuple[str, str]] = []  # (branch, mode)

    if args.branch:
        branches_to_scout.append((args.branch, "targeted"))

    elif args.all_stuck:
        stuck = find_stuck_branches(state, threshold=args.stuck_threshold)
        diminishing = find_diminishing_branches(state)
        for b in stuck:
            branches_to_scout.append((b, "stuck"))
        for b in diminishing:
            if b not in stuck:
                branches_to_scout.append((b, "diminishing"))

    elif args.expansion:
        beliefs = state.get("branch_beliefs", {}).get("branches", {})
        if "expansion_meta" in beliefs and beliefs["expansion_meta"].get("status") not in ("blocked", "exhausted"):
            branches_to_scout.append(("expansion_meta", "expansion"))
        else:
            for name, b in beliefs.items():
                if b.get("status") not in ("blocked", "exhausted"):
                    branches_to_scout.append((name, "expansion"))

    else:
        parser.print_help()
        print("\nSpecify --branch, --all-stuck, or --expansion")
        sys.exit(1)

    if not branches_to_scout:
        print("No branches to scout. All branches are either progressing or exhausted.")
        return

    # Generate and write scout requests
    print(f"Scouting {len(branches_to_scout)} branch(es):\n")
    requests_written = []

    for branch, mode in branches_to_scout:
        print(f"  [{branch}] mode={mode}")
        branch_exps = get_branch_experiments(state, branch)
        n_exps = len(branch_exps)
        n_promote = sum(1 for e in branch_exps if e.get("verdict") == "PROMOTE")
        print(f"    {n_exps} experiments, {n_promote} promoted")

        request = build_scout_request(state, branch, lab_dir, mode=mode)
        path = write_scout_request(request, lab_dir)
        requests_written.append(path)

        print(f"    {len(request['search_queries'])} search queries generated")
        for q in request["search_queries"]:
            print(f"      - {q}")
        print(f"    Request written to: {path}")
        print()

    # Summary
    print(f"{'='*60}")
    print(f"Scout requests written: {len(requests_written)}")
    print()
    print("Next step: have the Claude Code agent run the research scout template.")
    print("The agent reads each scout_request.json, executes WebSearch queries,")
    print("and writes proposals to the scout_proposals/ directory.")
    print()
    print("To deploy the scout agent for each request:")
    for path in requests_written:
        branch = path.parent.parent.name
        print(f'  Agent(name="scout-{branch}", '
              f'prompt="Read {path} and research_scout.md. '
              f'Execute the scout protocol.")')
    print()
    print("After the scout writes proposals, approve good ones by adding")
    print("'approved: true' to the YAML, then run:")
    for branch, _ in branches_to_scout:
        print(f"  python scripts/research_scout.py --merge --branch {branch} "
              f"--lab-dir {lab_dir}")
    if any(mode == "expansion" for _, mode in branches_to_scout):
        print(f"  python scripts/research_scout.py --merge-expansion --lab-dir {lab_dir}")


if __name__ == "__main__":
    main()
