#!/usr/bin/env python3
"""Helper for deep-research-first lab operation."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from lab_core import determine_next_phase, summarize_lab


SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_lab_root(lab_dir: str | None) -> Path:
    if lab_dir:
        return Path(lab_dir).resolve()
    return SCRIPT_ROOT


def cmd_check_readiness(lab_root: Path) -> int:
    summary = summarize_lab(lab_root)
    if summary["readiness_issues"]:
        print("PHASE0_INCOMPLETE")
        for issue in summary["readiness_issues"]:
            print(f"- {issue}")
        return 1

    print("PHASE0_READY")
    print(f"- Lab root: {lab_root}")
    print("- branches.yaml, research_brief.md, and research_sources.md look complete.")
    return 0


def cmd_status(lab_root: Path) -> int:
    summary = summarize_lab(lab_root)
    print(f"Lab root: {summary['lab_root']}")
    print(f"Phase 0 ready: {'yes' if summary['ready'] else 'no'}")
    if summary["readiness_issues"]:
        print("Readiness issues:")
        for issue in summary["readiness_issues"]:
            print(f"  - {issue}")
    print(f"Bootstrapped: {'yes' if summary['bootstrapped'] else 'no'}")
    print(f"Cycle: {summary['cycle'] if summary['cycle'] is not None else 'not started'}")
    print(f"Next phase: {summary['next_phase']}")
    print("Active branches:", ", ".join(summary["active_branches"]) or "none")
    print("Stuck branches:", ", ".join(summary["stuck_branches"]) or "none")
    print("Audit branches:", ", ".join(summary["audit_branches"]) or "none")
    print("Invalid-fast branches:", ", ".join(summary["invalid_fast_branches"]) or "none")
    print("Exhausted branches:", ", ".join(summary["exhausted_branches"]) or "none")
    print("Active agents:", ", ".join(summary["active_agents"]) or "none")
    return 0


def _prompt_for_phase(lab_root: Path, runner: str, phase: str) -> str:
    summary = summarize_lab(lab_root)
    phase = determine_next_phase(lab_root) if phase == "auto" else phase
    runner_file = "claude_code.md" if runner == "claude" else "codex.md"
    phase_file = {
        "design": "design.md",
        "cycle": "cycle.md",
        "audit": "audit.md",
        "scout": "scout.md",
        "frame_break": "frame_break.md",
        "expansion": "expansion.md",
        "checkpoint": "checkpoint.md",
    }[phase]

    lines = [
        f"Read agent_prompts/{runner_file}.",
        f"Read agent_prompts/shared/{phase_file}.",
    ]

    if phase != "design":
        lines.append("Read orchestrator.md after the phase prompt.")

    if phase in {"scout", "expansion"}:
        lines.append(
            "If no scout request files exist yet, run `python scripts/operator_helper.py "
            f"prepare-scout {'--all-stuck' if phase == 'scout' else '--expansion'}` first."
        )
    if phase == "expansion":
        lines.append(
            "Expansion proposals should land in "
            "`experiments/expansion_meta/scout_proposals/expansion_cycle_N.yaml`."
        )
        lines.append(
            "After approving proposals, merge them with "
            "`python scripts/research_scout.py --merge-expansion --lab-dir <lab>`."
        )
    if phase == "frame_break":
        lines.append(
            "Frame-break should leave a patch file in `logs/expansions/frame_break_cycle_N_patch.yaml`."
        )
    if phase == "audit":
        lines.append(
            "Implementation audit should leave `logs/implementation_audit_cycle_N.md`"
            " plus a short patch or follow-up memo if the family should stay alive."
        )
        lines.append(
            "Treat suspicious invalid-fast or near-miss families as potentially broken implementations,"
            " not automatically dead science."
        )

    if phase == "cycle" and not summary["bootstrapped"]:
        lines.append("Run `python scripts/bootstrap.py` before executing the first cycle.")
    if summary["invalid_fast_branches"]:
        lines.append(
            "Recent invalid-fast branches need an implementation audit before you call the family exhausted."
        )
        lines.append(
            "For each suspicious branch: rerun the winning-looking config, run one nearby control or ablation,"
            " and decide whether the anomaly is a real frontier jump or a branch-implementation bug."
        )

    lines.append("Use only this lab's local files as your operating context.")
    lines.append("Current lab status:")
    lines.append(f"- cycle: {summary['cycle'] if summary['cycle'] is not None else 'not started'}")
    lines.append(f"- active branches: {', '.join(summary['active_branches']) or 'none'}")
    lines.append(f"- stuck branches: {', '.join(summary['stuck_branches']) or 'none'}")
    lines.append(f"- audit branches: {', '.join(summary['audit_branches']) or 'none'}")
    lines.append(f"- invalid-fast branches: {', '.join(summary['invalid_fast_branches']) or 'none'}")
    lines.append(f"- exhausted branches: {', '.join(summary['exhausted_branches']) or 'none'}")
    lines.append(f"- next phase: {summary['next_phase']}")
    return "\n".join(lines)


def cmd_next_prompt(lab_root: Path, runner: str, phase: str) -> int:
    print(_prompt_for_phase(lab_root, runner, phase))
    return 0


def cmd_prepare_scout(lab_root: Path, args: argparse.Namespace) -> int:
    scout_script = lab_root / "scripts" / "research_scout.py"
    if not scout_script.exists():
        print(f"ERROR: {scout_script} not found.")
        return 1

    cmd = [sys.executable, str(scout_script), "--lab-dir", str(lab_root)]
    if args.branch:
        cmd.extend(["--branch", args.branch])
    elif args.all_stuck:
        cmd.append("--all-stuck")
    elif args.expansion:
        cmd.append("--expansion")
    else:
        print("ERROR: choose --branch, --all-stuck, or --expansion")
        return 1

    result = subprocess.run(cmd, check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Helper for operating a labrat lab")
    parser.add_argument(
        "--lab-dir",
        default=None,
        help="Path to the lab root. Defaults to the parent of this scripts directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check-readiness", help="Verify that Phase 0 outputs are complete")
    subparsers.add_parser("status", help="Summarize current lab state and next phase")

    next_prompt = subparsers.add_parser("next-prompt", help="Print the exact next prompt to give the agent")
    next_prompt.add_argument("--runner", choices=["claude", "codex"], required=True)
    next_prompt.add_argument(
        "--phase",
        choices=["auto", "design", "cycle", "audit", "scout", "frame_break", "expansion", "checkpoint"],
        default="auto",
    )

    prepare_scout = subparsers.add_parser("prepare-scout", help="Generate scout requests")
    prepare_scout.add_argument("--branch", help="Generate a scout request for one branch")
    prepare_scout.add_argument("--all-stuck", action="store_true", help="Generate scout requests for all stuck branches")
    prepare_scout.add_argument("--expansion", action="store_true", help="Generate expansion scout requests")

    args = parser.parse_args()
    lab_root = _resolve_lab_root(args.lab_dir)

    if args.command == "check-readiness":
        return cmd_check_readiness(lab_root)
    if args.command == "status":
        return cmd_status(lab_root)
    if args.command == "next-prompt":
        return cmd_next_prompt(lab_root, args.runner, args.phase)
    if args.command == "prepare-scout":
        return cmd_prepare_scout(lab_root, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
