#!/usr/bin/env python3
"""Bootstrap the research lab: create directories, initialize state files.

v2: Adds transition_log, belief_chain, scout_history, lab_registry support.

Usage:
    python research_lab/scripts/bootstrap.py
    python research_lab/scripts/bootstrap.py --inherit-from /path/to/parent/lab
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

LAB_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = LAB_ROOT.parent


def main():
    parser = argparse.ArgumentParser(description="Bootstrap labrat research lab")
    parser.add_argument(
        "--inherit-from", type=Path, default=None,
        help="Path to a parent lab to inherit dead_ends and findings from",
    )
    args = parser.parse_args()

    print("Bootstrapping research lab...\n")

    # Validate required files exist
    required = ["branches.yaml", "scripts/run_experiment.py", "scripts/judge.py"]
    missing = [f for f in required if not (LAB_ROOT / f).exists()]
    if missing:
        print("ERROR: Missing required files:")
        for f in missing:
            print(f"  {f}")
        print("\nThese must exist before bootstrapping. See docs/getting-started.md.")
        sys.exit(1)

    # Create optional files from templates if missing
    for tmpl in ["constitution.md", "dead_ends.md"]:
        dest = LAB_ROOT / tmpl
        src = PROJECT_ROOT / "templates" / tmpl
        if not dest.exists() and src.exists():
            import shutil
            shutil.copy2(src, dest)
            print(f"  Created {tmpl} from template")

    # Load branch definitions
    with open(LAB_ROOT / "branches.yaml") as f:
        config = yaml.safe_load(f)

    branches = config.get("branches", {})

    # Create directories
    print("Creating directories:")
    dirs = [
        LAB_ROOT / "state",
        LAB_ROOT / "logs" / "cycles",
        LAB_ROOT / "logs" / "scouts",
        LAB_ROOT / "logs" / "expansions",
        LAB_ROOT / "logs" / "consolidations",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {d.relative_to(PROJECT_ROOT)}")

    for branch in list(branches.keys()) + ["red_team"]:
        d = LAB_ROOT / "experiments" / branch
        d.mkdir(parents=True, exist_ok=True)
        # Scout proposals dir per branch
        scout_dir = d / "scout_proposals"
        scout_dir.mkdir(exist_ok=True)
        print(f"  {d.relative_to(PROJECT_ROOT)}")

    # Initialize state
    print("\nInitializing state:")
    now = datetime.now(UTC).isoformat()

    # Cycle counter (with transition tracking)
    _write(LAB_ROOT / "state" / "cycle_counter.json", {
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
    _write(LAB_ROOT / "state" / "budget.json", budget)

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
    _write(LAB_ROOT / "state" / "branch_beliefs.json", beliefs)

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
    _write(LAB_ROOT / "state" / "champions.json", champions)

    # Experiment log (empty, append-only)
    (LAB_ROOT / "state" / "experiment_log.jsonl").write_text("")

    # Active agents (for dashboard live status)
    _write(LAB_ROOT / "state" / "active_agents.json", {
        "updated_at": now, "agents": {},
    })

    # Transition log (tracks cycle endings with named types)
    (LAB_ROOT / "state" / "transition_log.jsonl").write_text("")

    # Belief chain (tracks assumption dependencies)
    _write(LAB_ROOT / "state" / "belief_chain.json", {
        "updated_at": now,
        "assumptions": {},
        "invalidations": [],
    })

    # Scout history (tracks what external searches have been done)
    _write(LAB_ROOT / "state" / "scout_history.json", {
        "updated_at": now,
        "searches": [],
        "proposals_accepted": 0,
        "proposals_rejected": 0,
        "last_scout_cycle": None,
        "last_expansion_cycle": None,
    })

    # Decay tracking (val/test performance ratio)
    _write(LAB_ROOT / "state" / "decay_tracking.json", {
        "updated_at": now,
        "entries": [],
        "rolling_decay_ratio": None,
    })

    # Data profile (populated by Step 0 exploration agent)
    _write(LAB_ROOT / "state" / "data_profile.json", {
        "updated_at": None,
        "subgroups": {},
        "correlations": {},
        "distribution_shifts": [],
        "proposed_branches": [],
    })

    # Handoff
    active = [n for n, c in branches.items() if c.get("initial_budget", 0) > 0]
    meta = [n for n, c in branches.items() if c.get("experiment_type") in ("diagnostic", "meta")]
    (LAB_ROOT / "logs" / "handoff.md").write_text(
        f"# Research Lab Handoff\n\n## Cycle 0 -- Bootstrap\n\n"
        f"Lab initialized. Active branches: {', '.join(active)}.\n"
        f"Meta-branches: {', '.join(meta) or 'none'}.\n\n"
        f"External research: scouts trigger after "
        f"{config.get('external_research', {}).get('scout_trigger', {}).get('consecutive_non_improvements', 4)} "
        f"consecutive non-improvements. Expansion every "
        f"{config.get('external_research', {}).get('expansion_trigger', {}).get('every_n_cycles', 20)} cycles.\n"
    )

    # Inherit from parent lab if specified
    if args.inherit_from:
        _inherit_from_parent(args.inherit_from)

    # Copy dashboard if template exists
    template_dash = PROJECT_ROOT / "templates" / "dashboard.html"
    lab_dash = LAB_ROOT / "dashboard.html"
    if template_dash.exists() and not lab_dash.exists():
        import shutil
        shutil.copy2(template_dash, lab_dash)
        print(f"  Copied dashboard to {lab_dash.relative_to(PROJECT_ROOT)}")

    # Update lab registry
    _update_lab_registry(config)

    # Print research tree
    try:
        from scripts.tree_render import render_tree, load_lab
        _, state = load_lab(LAB_ROOT)
        print("\n" + render_tree(config, state, compact=True))
    except Exception:
        pass

    print(f"Bootstrap complete. {len(active)} active branches, {sum(budget.values())} total budget.")
    print(f"Meta-branches: {len(meta)}")
    print()
    print("To start:")
    print("  cd research_lab && python -m http.server 8787 &")
    print("  open http://localhost:8787/dashboard.html")
    print()
    print("Then in Claude Code:")
    print("  Read research_lab/orchestrator.md and execute one research cycle.")
    print()
    print("For tree design (optional, uses web research to design branches):")
    print("  Agent: Read labrat/templates/tree_designer.md. Design branches for: [your mission]")
    print()
    print("For continuous operation:")
    print("  /loop 10m Read research_lab/orchestrator.md and execute one research cycle.")


def _inherit_from_parent(parent_path: Path):
    """Inherit dead ends and findings from a parent lab."""
    print(f"\nInheriting from parent lab: {parent_path}")

    # Copy dead ends
    parent_dead = parent_path / "dead_ends.md"
    if parent_dead.exists():
        local_dead = LAB_ROOT / "dead_ends.md"
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
        dest = LAB_ROOT / "logs" / "parent_findings.md"
        import shutil
        shutil.copy2(parent_findings, dest)
        print(f"  Inherited FINDINGS.md -> logs/parent_findings.md")

    # Copy champion config for reference
    parent_champs = parent_path / "state" / "champions.json"
    if parent_champs.exists():
        dest = LAB_ROOT / "logs" / "parent_champions.json"
        import shutil
        shutil.copy2(parent_champs, dest)
        print(f"  Inherited champions.json -> logs/parent_champions.json")


def _update_lab_registry(config: dict):
    """Update the global lab registry with this lab's info."""
    registry_path = PROJECT_ROOT / "lab_registry.json"

    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
    else:
        registry = {"labs": {}, "updated_at": None}

    lab_name = LAB_ROOT.name
    registry["labs"][lab_name] = {
        "path": str(LAB_ROOT),
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
    print(f"  {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
