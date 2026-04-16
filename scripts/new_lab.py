#!/usr/bin/env python3
"""Create a labrat vNext starter lab inside this checked-out repo."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest, dirs_exist_ok=True)


def target_is_safe(target: Path) -> bool:
    if not target.exists():
        return True
    return target.is_dir() and not any(target.iterdir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a starter lab from the labrat vNext templates.")
    parser.add_argument("target_dir", help="Directory to create inside this checked-out labrat repo.")
    args = parser.parse_args(argv)

    target = (REPO_ROOT / args.target_dir).resolve()
    if REPO_ROOT not in target.parents and target != REPO_ROOT:
        print("ERROR: target_dir must stay inside this checked-out labrat repo.")
        return 1
    if not target_is_safe(target):
        print(f"ERROR: target directory is not empty: {target}")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    (target / "scripts").mkdir(exist_ok=True)

    root_files = [
        "branches.yaml",
        "dead_ends.md",
        "research_brief.md",
        "research_sources.md",
        "evaluation.yaml",
        "runtime.yaml",
        "orchestrator.md",
        "research_scout.md",
        "expansion_scout.md",
        "frame_break.md",
        "implementation_audit.md",
        "consolidation_agent.md",
        "tree_designer.md",
        "mutation_worker.md",
        "crossover_worker.md",
        "probe_worker.md",
        "dashboard.html",
    ]
    for name in root_files:
        copy_file(TEMPLATES_DIR / name, target / name)

    script_files = [
        "bootstrap.py",
        "runtime.py",
        "evaluator.py",
        "operator_helper.py",
        "lab_core.py",
        "research_scout.py",
    ]
    for name in script_files:
        copy_file(SCRIPTS_DIR / name, target / "scripts" / name)
    copy_file(TEMPLATES_DIR / "run_experiment.py", target / "scripts" / "run_experiment.py")
    copy_tree(TEMPLATES_DIR / "agent_prompts", target / "agent_prompts")

    print(f"Created starter lab at {target.relative_to(REPO_ROOT)}")
    print()
    print("Next steps:")
    print(f"  1. cd {target.relative_to(REPO_ROOT)}")
    print("  2. Complete Phase 0 with the lab-local prompts:")
    print("     python scripts/operator_helper.py next-prompt --runner claude --phase design")
    print("     or")
    print("     python scripts/operator_helper.py next-prompt --runner codex --phase design")
    print("  3. Confirm readiness:")
    print("     python scripts/operator_helper.py check-readiness")
    print("  4. Bootstrap the runtime:")
    print("     python scripts/bootstrap.py")
    print("  5. Start the dashboard:")
    print("     python -m http.server 8787")
    print()
    print("Then use the helper to get the exact next prompt:")
    print("  python scripts/operator_helper.py next-prompt --runner claude --phase auto")
    print("  python scripts/operator_helper.py next-prompt --runner codex --phase auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
