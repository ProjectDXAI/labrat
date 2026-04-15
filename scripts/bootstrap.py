#!/usr/bin/env python3
"""Bootstrap the research lab: create directories, initialize state files.

v2: Adds transition_log, belief_chain, scout_history, and optional lab registry support.

Usage:
    python scripts/bootstrap.py
    python scripts/bootstrap.py --inherit-from /path/to/parent/lab
    python scripts/bootstrap.py --lab-dir /path/to/lab
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from lab_core import find_readiness_issues

SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Bootstrap labrat research lab")
    parser.add_argument(
        "--inherit-from", type=Path, default=None,
        help="Path to a parent lab to inherit dead_ends and findings from",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Bypass the Phase 0 readiness gate for maintainers and partial scaffolds.",
    )
    parser.add_argument(
        "--lab-dir",
        type=Path,
        default=SCRIPT_ROOT,
        help="Path to the lab root. Defaults to the parent of this scripts directory.",
    )
    args = parser.parse_args()
    lab_root = args.lab_dir.resolve()
    project_root = _resolve_project_root(lab_root)

    print("Bootstrapping research lab...\n")

    issues = find_readiness_issues(lab_root)
    if issues and not args.allow_incomplete:
        print("ERROR: Phase 0 is not complete.\n")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Run:")
        print("  python scripts/operator_helper.py check-readiness")
        print("  python scripts/operator_helper.py next-prompt --runner claude --phase design")
        print("or")
        print("  python scripts/operator_helper.py next-prompt --runner codex --phase design")
        sys.exit(1)
    if issues and args.allow_incomplete:
        print("WARNING: bootstrapping an incomplete lab.")
        for issue in issues:
            print(f"  - {issue}")
        print()

    # Validate required files exist
    required = ["branches.yaml", "scripts/run_experiment.py", "scripts/judge.py"]
    missing = [f for f in required if not (lab_root / f).exists()]
    if missing:
        print("ERROR: Missing required files:")
        for f in missing:
            print(f"  {f}")
        print("\nThese must exist before bootstrapping. See docs/getting-started.md.")
        sys.exit(1)

    # Create optional files from templates if missing
    for tmpl in ["constitution.md", "dead_ends.md"]:
        dest = lab_root / tmpl
        src = project_root / "templates" / tmpl
        if not dest.exists() and src.exists():
            import shutil
            shutil.copy2(src, dest)
            print(f"  Created {tmpl} from template")

    # Load branch definitions
    with open(lab_root / "branches.yaml") as f:
        config = yaml.safe_load(f)

    branches = config.get("branches", {})

    # Create directories
    print("Creating directories:")
    dirs = [
        lab_root / "state",
        lab_root / "logs" / "cycles",
        lab_root / "logs" / "scouts",
        lab_root / "logs" / "expansions",
        lab_root / "logs" / "consolidations",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {_display_path(d, project_root)}")

    for branch in list(branches.keys()) + ["red_team"]:
        d = lab_root / "experiments" / branch
        d.mkdir(parents=True, exist_ok=True)
        # Scout proposals dir per branch
        scout_dir = d / "scout_proposals"
        scout_dir.mkdir(exist_ok=True)
        print(f"  {_display_path(d, project_root)}")

    # Initialize state
    print("\nInitializing state:")
    now = datetime.now(UTC).isoformat()

    # Cycle counter (with transition tracking)
    _write(lab_root / "state" / "cycle_counter.json", {
        "cycle": 0,
        "total_experiments": 0,
        "started_at": now,
        "last_run_at": None,
        "last_transition": None,
        "preferences": {
            "max_parallel_branches": None,
            "loop_interval": None,
            "priority_branches": [],
            "skip_branches": [],
        },
    })

    # Budget
    budget = {name: cfg.get("initial_budget", 0) for name, cfg in branches.items()}
    _write(lab_root / "state" / "budget.json", budget)

    # Branch beliefs
    beliefs = {"updated_at": now, "branches": {}}
    for name, cfg in branches.items():
        beliefs["branches"][name] = {
            "n_experiments": 0,
            "n_improvements": 0,
            "current_ev": 0.0,
            "uncertainty": 1.0,
            "last_explored_cycle": 0,
            "best_composite_score": None,
            "status": "exhausted" if cfg.get("initial_budget", 0) == 0 else "active",
            "flat_axes": [],
            "notes": [],
            "experiment_type": cfg.get("experiment_type", "standard"),
        }
    _write(lab_root / "state" / "branch_beliefs.json", beliefs)

    # Champions
    baseline = {
        "experiment_id": config.get("production_baseline", {}).get("experiment_id", "baseline"),
        "description": config.get("production_baseline", {}).get("description", "Baseline"),
        "scores": None,
        "result_path": None,
    }
    champions = {
        "updated_at": now,
        "production_champion": baseline,
        "branches": {name: baseline.copy() for name in branches},
    }
    _write(lab_root / "state" / "champions.json", champions)

    # Experiment log (empty, append-only)
    (lab_root / "state" / "experiment_log.jsonl").write_text("")

    # Active agents (for dashboard live status)
    _write(lab_root / "state" / "active_agents.json", {
        "updated_at": now, "agents": {},
    })

    # Transition log (tracks cycle endings with named types)
    (lab_root / "state" / "transition_log.jsonl").write_text("")

    # Belief chain (tracks assumption dependencies)
    _write(lab_root / "state" / "belief_chain.json", {
        "updated_at": now,
        "assumptions": {},
        "invalidations": [],
    })

    # Scout history (tracks what external searches have been done)
    _write(lab_root / "state" / "scout_history.json", {
        "updated_at": now,
        "searches": [],
        "proposals_accepted": 0,
        "proposals_rejected": 0,
        "last_scout_cycle": None,
        "last_expansion_cycle": None,
    })

    # Decay tracking (val/test performance ratio)
    _write(lab_root / "state" / "decay_tracking.json", {
        "updated_at": now,
        "entries": [],
        "rolling_decay_ratio": None,
    })

    # Data profile (populated by Step 0 exploration agent)
    _write(lab_root / "state" / "data_profile.json", {
        "updated_at": None,
        "subgroups": {},
        "correlations": {},
        "distribution_shifts": [],
        "proposed_branches": [],
    })

    # Handoff
    active = [n for n, c in branches.items() if c.get("initial_budget", 0) > 0]
    meta = [n for n, c in branches.items() if c.get("experiment_type") in ("diagnostic", "meta")]
    (lab_root / "logs" / "handoff.md").write_text(
        f"# Research Lab Handoff\n\n## Cycle 0 -- Bootstrap\n\n"
        f"Lab initialized. Active branches: {', '.join(active)}.\n"
        f"Meta-branches: {', '.join(meta) or 'none'}.\n\n"
        "Phase 0 artifacts detected: branches.yaml, research_brief.md, research_sources.md.\n\n"
        f"External research: scouts trigger after "
        f"{config.get('external_research', {}).get('scout_trigger', {}).get('consecutive_non_improvements', 4)} "
        f"consecutive non-improvements. Expansion every "
        f"{config.get('external_research', {}).get('expansion_trigger', {}).get('every_n_cycles', 20)} cycles.\n"
    )

    # Inherit from parent lab if specified
    if args.inherit_from:
        _inherit_from_parent(args.inherit_from, lab_root)

    # Copy dashboard if template exists
    template_dash = project_root / "templates" / "dashboard.html"
    lab_dash = lab_root / "dashboard.html"
    if template_dash.exists() and not lab_dash.exists():
        import shutil
        shutil.copy2(template_dash, lab_dash)
        print(f"  Copied dashboard to {_display_path(lab_dash, project_root)}")

    # Update lab registry when the repo already uses one.
    _update_lab_registry(config, lab_root, project_root)

    # Print research tree
    try:
        from scripts.tree_render import render_tree, load_lab
        _, state = load_lab(lab_root)
        print("\n" + render_tree(config, state, compact=True))
    except Exception:
        pass

    lab_rel = _display_path(lab_root, project_root)

    print(f"Bootstrap complete. {len(active)} active branches, {sum(budget.values())} total budget.")
    print(f"Meta-branches: {len(meta)}")
    print()
    print("To start:")
    print(f"  cd {lab_rel} && python -m http.server 8787 &")
    print("  open http://localhost:8787/dashboard.html")
    print()
    print("Then get the exact next prompt from the local helper:")
    print("  python scripts/operator_helper.py status")
    print("  python scripts/operator_helper.py next-prompt --runner claude --phase auto")
    print("  python scripts/operator_helper.py next-prompt --runner codex --phase auto")
    print()
    print("For continuous operation, keep the agent in the lab-local prompt flow.")


def _resolve_project_root(lab_root: Path) -> Path:
    if (SCRIPT_ROOT / "templates").exists() and (SCRIPT_ROOT / "scripts").exists():
        return SCRIPT_ROOT
    return lab_root.parent


def _inherit_from_parent(parent_path: Path, lab_root: Path):
    """Inherit dead ends and findings from a parent lab."""
    print(f"\nInheriting from parent lab: {parent_path}")

    # Copy dead ends
    parent_dead = parent_path / "dead_ends.md"
    if parent_dead.exists():
        local_dead = lab_root / "dead_ends.md"
        if local_dead.exists():
            # Append parent dead ends
            existing = local_dead.read_text()
            parent_content = parent_dead.read_text()
            local_dead.write_text(
                existing + f"\n\n## Inherited from {parent_path.name}\n\n" + parent_content
            )
        else:
            import shutil
            shutil.copy2(parent_dead, local_dead)
        print(f"  Inherited dead_ends.md")

    # Copy findings
    parent_findings = parent_path / "FINDINGS.md"
    if parent_findings.exists():
        dest = lab_root / "logs" / "parent_findings.md"
        import shutil
        shutil.copy2(parent_findings, dest)
        print(f"  Inherited FINDINGS.md -> logs/parent_findings.md")

    # Copy champion config for reference
    parent_champs = parent_path / "state" / "champions.json"
    if parent_champs.exists():
        dest = lab_root / "logs" / "parent_champions.json"
        import shutil
        shutil.copy2(parent_champs, dest)
        print(f"  Inherited champions.json -> logs/parent_champions.json")


def _update_lab_registry(config: dict, lab_root: Path, project_root: Path):
    """Update the global lab registry with this lab's info."""
    registry_path = project_root / "lab_registry.json"

    if not registry_path.exists():
        return

    with open(registry_path) as f:
        registry = json.load(f)

    lab_name = lab_root.name
    registry["labs"][lab_name] = {
        "path": str(lab_root),
        "mission": config.get("mission", ""),
        "branches": list(config.get("branches", {}).keys()),
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
    }
    registry["updated_at"] = datetime.now(UTC).isoformat()

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"  Updated lab registry: {registry_path}")


def _write(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    project_root = _resolve_project_root(path.parent.parent if path.name.endswith(".json") else path.parent)
    print(f"  {_display_path(path, project_root)}")


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
