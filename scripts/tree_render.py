#!/usr/bin/env python3
"""Render the research tree as ASCII art.

Reads branches.yaml and state files to produce a live tree showing
branch status, budget, experiment counts, and champion scores.

Usage:
    python scripts/tree_render.py --lab-dir research_lab/
    python scripts/tree_render.py --lab-dir research_lab/ --compact
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def load_lab(lab_dir: Path) -> dict:
    """Load branches.yaml and state files."""
    with open(lab_dir / "branches.yaml") as f:
        config = yaml.safe_load(f)

    state = {}
    for name in ["branch_beliefs", "budget", "champions", "cycle_counter"]:
        path = lab_dir / "state" / f"{name}.json"
        if path.exists():
            with open(path) as f:
                state[name] = json.load(f)
    return config, state


def status_icon(status: str, n_improvements: int, n_experiments: int) -> str:
    if status == "converged":
        return "="
    if status == "exhausted":
        return "x"
    if n_experiments == 0:
        return "."
    if n_improvements > 0:
        return "+"
    return "-"


def render_tree(config: dict, state: dict, compact: bool = False) -> str:
    """Render the full research tree as ASCII art."""
    branches = config.get("branches", {})
    beliefs = state.get("branch_beliefs", {}).get("branches", {})
    budget = state.get("budget", {})
    champions = state.get("champions", {})
    cycle = state.get("cycle_counter", {}).get("cycle", 0)
    total_exp = state.get("cycle_counter", {}).get("total_experiments", 0)

    baseline = config.get("production_baseline", {})
    baseline_id = baseline.get("experiment_id", "baseline")
    mission = config.get("mission", "")

    prod_champ = champions.get("production_champion", {})
    prod_id = prod_champ.get("experiment_id", baseline_id)
    prod_score = ""
    if prod_champ.get("scores") and prod_champ["scores"].get("composite_score"):
        prod_score = f" (score={prod_champ['scores']['composite_score']:.3f})"

    lines = []

    # Header
    if mission and not compact:
        lines.append(f"  mission: {mission[:80]}")
        lines.append("")

    lines.append(f"  cycle {cycle} | {total_exp} experiments | champion: {prod_id}{prod_score}")
    lines.append("")

    # Baseline node
    lines.append(f"  {baseline_id}")
    lines.append("  │")

    # Sort branches: standard first, then meta, then capstone
    standard = []
    meta = []
    capstone = []
    for name, cfg in branches.items():
        exp_type = cfg.get("experiment_type", "standard")
        if name == "capstone":
            capstone.append((name, cfg))
        elif exp_type in ("diagnostic", "meta"):
            meta.append((name, cfg))
        else:
            standard.append((name, cfg))

    all_branches = standard + meta
    n_branches = len(all_branches)

    for i, (name, cfg) in enumerate(all_branches):
        is_last = (i == n_branches - 1) and not capstone
        b = beliefs.get(name, {})
        bgt = budget.get(name, 0)
        n_exp = b.get("n_experiments", 0)
        n_imp = b.get("n_improvements", 0)
        status = b.get("status", "active")
        exp_type = cfg.get("experiment_type", "standard")
        best = b.get("best_composite_score")
        icon = status_icon(status, n_imp, n_exp)

        # Branch champion
        bc = champions.get("branches", {}).get(name, {})
        bc_id = bc.get("experiment_id", "")
        bc_score = ""
        if bc.get("scores") and bc["scores"].get("composite_score"):
            bc_score = f"={bc['scores']['composite_score']:.3f}"

        connector = "└" if is_last else "├"
        pipe = " " if is_last else "│"

        # Type tag
        tag = ""
        if exp_type == "diagnostic":
            tag = " [diagnostic]"
        elif exp_type == "meta":
            tag = " [meta]"

        # Main branch line
        if compact:
            lines.append(f"  {connector}── [{icon}] {name}: {n_exp} exp, {n_imp} promoted, budget={bgt}{tag}")
        else:
            lines.append(f"  {connector}── [{icon}] {name}{tag}")
            lines.append(f"  {pipe}     {n_exp} experiments, {n_imp} promoted, budget={bgt}")
            if bc_id and bc_id != baseline_id:
                lines.append(f"  {pipe}     champion: {bc_id}{bc_score}")

            # Show search space summary
            search = cfg.get("search_space", [])
            if search and not compact:
                axes = []
                for item in search:
                    key = item.get("delta_key", "?")
                    vals = item.get("values", [])
                    if isinstance(vals, list) and len(vals) <= 5:
                        if all(isinstance(v, (int, float, str, bool)) for v in vals):
                            axes.append(f"{key}: {vals}")
                        else:
                            axes.append(f"{key}: {len(vals)} variants")
                    else:
                        axes.append(f"{key}: {len(vals)} values")
                for ax in axes[:3]:
                    lines.append(f"  {pipe}     {ax}")

            lines.append(f"  {pipe}")

    # Capstone at the bottom
    if capstone:
        name, cfg = capstone[0]
        b = beliefs.get(name, {})
        bgt = budget.get(name, 0)
        n_exp = b.get("n_experiments", 0)
        n_imp = b.get("n_improvements", 0)
        icon = status_icon(b.get("status", "active"), n_imp, n_exp)

        bc = champions.get("branches", {}).get(name, {})
        bc_id = bc.get("experiment_id", "")
        bc_score = ""
        if bc.get("scores") and bc["scores"].get("composite_score"):
            bc_score = f"={bc['scores']['composite_score']:.3f}"

        multi = " (multi-delta)" if cfg.get("multi_delta") else ""

        lines.append("  └── ┬ capstone ─── combine branch winners" + multi)
        lines.append(f"       [{icon}] {n_exp} experiments, {n_imp} promoted, budget={bgt}")
        if bc_id and bc_id != baseline_id:
            lines.append(f"       champion: {bc_id}{bc_score}")

    lines.append("")

    # Legend
    if not compact:
        lines.append("  [+] promoted  [-] explored, no improvement  [.] unexplored  [=] converged  [x] exhausted")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Render research tree as ASCII")
    parser.add_argument("--lab-dir", type=Path, default=Path("research_lab"))
    parser.add_argument("--compact", action="store_true", help="One line per branch")
    args = parser.parse_args()

    config, state = load_lab(args.lab_dir)
    print(render_tree(config, state, compact=args.compact))


if __name__ == "__main__":
    main()
