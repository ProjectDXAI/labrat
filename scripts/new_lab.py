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
PROFILES_DIR = REPO_ROOT / "profiles"


def copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest, dirs_exist_ok=True)


def target_is_safe(target: Path) -> bool:
    if not target.exists():
        return True
    return target.is_dir() and not any(target.iterdir())


def available_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.name for p in PROFILES_DIR.iterdir() if p.is_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a starter lab from the labrat vNext templates.",
        epilog=(
            "Profiles pre-fill Phase 0 (branches.yaml, evaluation.yaml, runtime.yaml, "
            "research_brief.md, research_sources.md, dead_ends.md), a working run_experiment.py, "
            "CLAUDE.md, and .claude/commands for Claude Code users. "
            f"Available profiles: {', '.join(available_profiles()) or 'none'}."
        ),
    )
    parser.add_argument("target_dir", help="Directory to create inside this checked-out labrat repo.")
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "Optional profile to overlay on top of the base templates. "
            "Overlays Phase 0 files, a working run_experiment.py, "
            "CLAUDE.md and .claude/commands/. Base templates remain the default if omitted."
        ),
    )
    args = parser.parse_args(argv)

    if args.profile and args.profile not in available_profiles():
        print(f"ERROR: unknown profile '{args.profile}'. Available: {', '.join(available_profiles()) or 'none'}.")
        return 1

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
        "CLAUDE.md",
    ]
    for name in root_files:
        src = TEMPLATES_DIR / name
        if not src.exists():
            continue
        copy_file(src, target / name)

    script_files = [
        "bootstrap.py",
        "runtime.py",
        "evaluator.py",
        "operator_helper.py",
        "lab_core.py",
        "pareto.py",
        "research_scout.py",
    ]
    for name in script_files:
        src = SCRIPTS_DIR / name
        if not src.exists():
            continue
        copy_file(src, target / "scripts" / name)
    copy_file(TEMPLATES_DIR / "run_experiment.py", target / "scripts" / "run_experiment.py")
    copy_tree(TEMPLATES_DIR / "agent_prompts", target / "agent_prompts")
    if (TEMPLATES_DIR / ".claude").exists():
        copy_tree(TEMPLATES_DIR / ".claude", target / ".claude")
    if (TEMPLATES_DIR / "coordination").exists():
        copy_tree(TEMPLATES_DIR / "coordination", target / "coordination")

    profile_applied: list[str] = []
    if args.profile:
        profile_src = PROFILES_DIR / args.profile
        copy_tree(profile_src, target)
        profile_applied = sorted(
            str(p.relative_to(profile_src)) for p in profile_src.rglob("*") if p.is_file()
        )

    rel_target = target.relative_to(REPO_ROOT)
    print(f"Created starter lab at {rel_target}")
    if args.profile:
        print(f"Applied profile '{args.profile}' ({len(profile_applied)} files overlaid).")
    print()
    print("Next steps:")
    print(f"  1. cd {rel_target}")
    if args.profile:
        print("  2. Review the pre-filled Phase 0 files (branches.yaml, evaluation.yaml, runtime.yaml).")
        profile_req = PROFILES_DIR / args.profile / "requirements.txt"
        if profile_req.exists():
            print(f"     The profile ships its own requirements.txt at {rel_target}/requirements.txt.")
        print("  3. Confirm readiness:")
        print("     python scripts/operator_helper.py check-readiness")
        print("  4. Bootstrap the runtime:")
        print("     python scripts/bootstrap.py")
        print("  5. Start the dashboard (optional):")
        print("     python -m http.server 8787")
        print()
        print("Then use Claude Code's slash commands from this directory:")
        print("  /next           — get the next operator prompt")
        print("  /why-stuck      — diagnose a stuck frontier")
        print("  /synthesize     — synthesize recent evaluations before dispatching")
        print("  /audit-candidate /frame-break /consolidate")
        print()
        print("Or hand-run the operator helper:")
        print("  python scripts/operator_helper.py next-prompt --runner claude --phase auto")
    else:
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
        print("Then use Claude Code's slash commands from this directory:")
        print("  /next           — get the next operator prompt")
        print("  /why-stuck /synthesize /audit-candidate /frame-break /consolidate")
        print()
        print("Or hand-run the operator helper:")
        print("  python scripts/operator_helper.py next-prompt --runner claude --phase auto")
        print("  python scripts/operator_helper.py next-prompt --runner codex --phase auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
