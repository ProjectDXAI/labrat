#!/usr/bin/env python3
"""Bootstrap SST-5 sentiment lab."""

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

LAB = Path(__file__).resolve().parent.parent
PROJ = LAB.parent

with open(LAB / "branches.yaml") as f:
    config = yaml.safe_load(f)

branches = config.get("branches", {})
now = datetime.now(UTC).isoformat()

# Dirs
for d in [LAB / "state", LAB / "logs" / "cycles"]:
    d.mkdir(parents=True, exist_ok=True)
for b in list(branches) + ["red_team"]:
    (LAB / "experiments" / b).mkdir(parents=True, exist_ok=True)

# State
def w(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  {path.relative_to(PROJ)}")

w(LAB / "state" / "cycle_counter.json", {"cycle": 0, "total_experiments": 0, "started_at": now})
w(LAB / "state" / "budget.json", {n: c.get("initial_budget", 0) for n, c in branches.items()})

beliefs = {"updated_at": now, "branches": {}}
for n, c in branches.items():
    beliefs["branches"][n] = {
        "n_experiments": 0, "n_improvements": 0, "current_ev": 0.0,
        "uncertainty": 1.0, "last_explored_cycle": 0, "best_composite_score": None,
        "status": "exhausted" if c.get("initial_budget", 0) == 0 else "active",
    }
w(LAB / "state" / "branch_beliefs.json", beliefs)

baseline = {"experiment_id": "baseline_tfidf_logreg", "scores": None, "result_path": None}
w(LAB / "state" / "champions.json", {
    "updated_at": now, "production_champion": baseline,
    "branches": {n: baseline.copy() for n in branches},
})

(LAB / "state" / "experiment_log.jsonl").write_text("")

# Active agents (for dashboard live status)
w(LAB / "state" / "active_agents.json", {"updated_at": now, "agents": {}})

(LAB / "logs" / "handoff.md").write_text(
    f"# Handoff\n\n## Cycle 0 -- Bootstrap\n\nLab initialized. "
    f"Active: {', '.join(n for n,c in branches.items() if c.get('initial_budget',0)>0)}.\n"
)

# Copy dashboard from templates
import shutil
template_dash = PROJ / "templates" / "dashboard.html" if (PROJ / "templates").exists() else None
if template_dash and template_dash.exists() and not (LAB / "dashboard.html").exists():
    shutil.copy2(template_dash, LAB / "dashboard.html")
    print(f"  Copied dashboard to {(LAB / 'dashboard.html').relative_to(PROJ)}")

print(f"\nReady. cd to {PROJ} and run:")
print("  1. cd research_lab && python -m http.server 8787 &")
print("     Open http://localhost:8787/dashboard.html")
print("  2. Read research_lab/orchestrator.md and execute one research cycle.")
