#!/usr/bin/env python3
"""Bootstrap the research lab: create directories, initialize state files.

Usage:
    python research_lab/scripts/bootstrap.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

LAB_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = LAB_ROOT.parent


def main():
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
    for d in [LAB_ROOT / "state", LAB_ROOT / "logs" / "cycles"]:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {d.relative_to(PROJECT_ROOT)}")
    for branch in list(branches.keys()) + ["red_team"]:
        d = LAB_ROOT / "experiments" / branch
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {d.relative_to(PROJECT_ROOT)}")

    # Initialize state
    print("\nInitializing state:")
    now = datetime.now(UTC).isoformat()

    # Cycle counter
    _write(LAB_ROOT / "state" / "cycle_counter.json", {
        "cycle": 0, "total_experiments": 0,
        "started_at": now, "last_run_at": None,
    })

    # Budget
    budget = {name: cfg.get("initial_budget", 0) for name, cfg in branches.items()}
    _write(LAB_ROOT / "state" / "budget.json", budget)

    # Branch beliefs
    beliefs = {"updated_at": now, "branches": {}}
    for name, cfg in branches.items():
        beliefs["branches"][name] = {
            "n_experiments": 0, "n_improvements": 0,
            "current_ev": 0.0, "uncertainty": 1.0,
            "last_explored_cycle": 0, "best_composite_score": None,
            "status": "exhausted" if cfg.get("initial_budget", 0) == 0 else "active",
            "flat_axes": [],
        }
    _write(LAB_ROOT / "state" / "branch_beliefs.json", beliefs)

    # Champions
    baseline = {
        "experiment_id": config.get("production_baseline", {}).get("experiment_id", "baseline"),
        "description": config.get("production_baseline", {}).get("description", "Baseline"),
        "scores": None, "result_path": None,
    }
    champions = {
        "updated_at": now,
        "production_champion": baseline,
        "branches": {name: baseline.copy() for name in branches},
    }
    _write(LAB_ROOT / "state" / "champions.json", champions)

    # Experiment log (empty)
    (LAB_ROOT / "state" / "experiment_log.jsonl").write_text("")

    # Active agents (for dashboard live status)
    _write(LAB_ROOT / "state" / "active_agents.json", {
        "updated_at": now, "agents": {},
    })

    # Handoff
    active = [n for n, c in branches.items() if c.get("initial_budget", 0) > 0]
    (LAB_ROOT / "logs" / "handoff.md").write_text(
        f"# Research Lab Handoff\n\n## Cycle 0 -- Bootstrap\n\n"
        f"Lab initialized. Active branches: {', '.join(active)}.\n"
    )

    # Copy dashboard if template exists
    template_dash = PROJECT_ROOT / "templates" / "dashboard.html"
    lab_dash = LAB_ROOT / "dashboard.html"
    if template_dash.exists() and not lab_dash.exists():
        import shutil
        shutil.copy2(template_dash, lab_dash)
        print(f"  Copied dashboard to {lab_dash.relative_to(PROJECT_ROOT)}")

    print(f"\nBootstrap complete. {len(active)} active branches, {sum(budget.values())} total budget.")
    print("\nTo start:")
    print("  cd research_lab && python -m http.server 8787 &")
    print("  open http://localhost:8787/dashboard.html")
    print()
    print("Then in Claude Code:")
    print("  Read research_lab/orchestrator.md and execute one research cycle.")
    print("  Follow the 8 steps exactly. Do not ask for permission.")
    print()
    print("For continuous operation:")
    print("  /loop 10m Read research_lab/orchestrator.md and execute one research cycle.")


def _write(path: Path, data: dict):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
