#!/usr/bin/env python3
"""Helper for operating a labrat vNext lab."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from lab_core import determine_next_phase, diagnose_lab, summarize_lab


SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def resolve_lab_root(lab_dir: str | None) -> Path:
    return Path(lab_dir).resolve() if lab_dir else SCRIPT_ROOT


def check_readiness(lab_root: Path, as_json: bool = False) -> int:
    summary = summarize_lab(lab_root)
    if as_json:
        print(
            json.dumps(
                {
                    "lab_root": summary["lab_root"],
                    "ready": summary["ready"],
                    "readiness_issues": summary["readiness_issues"],
                },
                indent=2,
            )
        )
        return 0 if summary["ready"] else 1
    if summary["readiness_issues"]:
        print("PHASE0_INCOMPLETE")
        for issue in summary["readiness_issues"]:
            print(f"- {issue}")
        return 1
    print("PHASE0_READY")
    print(f"- Lab root: {lab_root}")
    print("- branches.yaml, dead_ends.md, research_brief.md, research_sources.md, evaluation.yaml, and runtime.yaml look complete.")
    return 0


def status(lab_root: Path, as_json: bool = False) -> int:
    summary = summarize_lab(lab_root)
    if as_json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"Lab root: {summary['lab_root']}")
    print(f"Phase 0 ready: {'yes' if summary['ready'] else 'no'}")
    if summary["readiness_issues"]:
        print("Readiness issues:")
        for issue in summary["readiness_issues"]:
            print(f"  - {issue}")
    print(f"Runtime initialized: {'yes' if summary.get('runtime_initialized') else 'no'}")
    print(f"Next phase: {summary['next_phase']}")
    if summary.get("runtime_initialized"):
        print(f"Step count: {summary.get('step_count', 0)}")
        print(f"Active phase: {summary.get('active_phase')}")
        print(f"Queued jobs: {summary.get('queued_jobs', 0)}")
        print(f"Leased jobs: {summary.get('leased_jobs', 0)}")
        print(f"Workers leased: {summary.get('worker_leases', 0)}/{summary.get('total_workers', 0)}")
        print(f"Total candidates: {summary.get('total_candidates', 0)}")
        print(f"Families: {', '.join(summary.get('families', [])) or 'none'}")
        print(f"Audit queue: {', '.join(summary.get('audit_queue', [])) or 'none'}")
        print(f"Invalid-fast candidates: {', '.join(summary.get('invalid_fast_candidates', [])) or 'none'}")
        print(f"Pending expansion: {summary.get('pending_expansion') or 'none'}")
        print(f"Remaining cheap probes: {summary.get('remaining_cheap_probes', 0)}")
    return 0


def doctor(lab_root: Path, as_json: bool = False) -> int:
    diagnosis = diagnose_lab(lab_root)
    if as_json:
        print(json.dumps(diagnosis, indent=2))
    else:
        print(f"Status: {diagnosis['status']}")
        print(f"Lab root: {diagnosis['lab_root']}")
        python_info = diagnosis["python"]
        python_status = "ok" if python_info["ok"] else f"requires >= {python_info['minimum']}"
        print(f"Python: {python_info['version']} ({python_status})")
        print(f"Phase 0 ready: {'yes' if diagnosis['phase0']['ready'] else 'no'}")
        if diagnosis["phase0"]["issues"]:
            print("Phase 0 issues:")
            for issue in diagnosis["phase0"]["issues"]:
                print(f"  - {issue}")
        print(f"Runtime bootstrap state: {diagnosis['runtime']['bootstrap_state']}")
        print(f"Runtime initialized: {'yes' if diagnosis['runtime']['initialized'] else 'no'}")
        print(f"Dashboard present: {'yes' if diagnosis['files']['dashboard_present'] else 'no'}")
        if diagnosis["files"]["missing_scripts"]:
            print("Missing scripts:")
            for name in diagnosis["files"]["missing_scripts"]:
                print(f"  - {name}")
        missing_requirements = diagnosis["dependencies"]["missing"]
        if diagnosis["dependencies"]["requirements_file"]:
            print(
                f"Requirements checked: {len(diagnosis['dependencies']['checked'])} "
                f"from {diagnosis['dependencies']['requirements_file']}"
            )
        if missing_requirements:
            print("Missing dependencies:")
            for record in missing_requirements:
                print(f"  - {record['requirement']} (import: {record['import_name']})")
        if diagnosis["runtime"]["initialized"]:
            print(f"Queued jobs: {diagnosis['runtime'].get('queued_jobs', 0)}")
            print(f"Leased jobs: {diagnosis['runtime'].get('leased_jobs', 0)}")
            print(
                f"Workers leased: "
                f"{diagnosis['runtime'].get('worker_leases', 0)}/{diagnosis['runtime'].get('total_workers', 0)}"
            )
            stale_leases = diagnosis["runtime"].get("stale_leases", [])
            print(f"Stale leases: {len(stale_leases)}")
            for lease in stale_leases:
                print(
                    "  - "
                    f"{lease['candidate_id']} on {lease['worker_id']} "
                    f"({lease['age_seconds']}s > {lease['timeout_seconds']}s timeout)"
                )
        if diagnosis["runtime_error"]:
            print(f"Runtime error: {diagnosis['runtime_error']}")
        print(f"Next action: {diagnosis['next_action']}")
    return 1 if diagnosis["status"] == "degraded" else 0


def runtime_summary(lab_root: Path) -> int:
    cmd = [sys.executable, str(SCRIPT_ROOT / "scripts" / "runtime.py"), "--lab-dir", str(lab_root), "summary"]
    return subprocess.run(cmd, check=False).returncode


def prompt_for_phase(lab_root: Path, runner: str, phase: str) -> str:
    summary = summarize_lab(lab_root)
    phase = determine_next_phase(lab_root) if phase == "auto" else phase
    runner_file = "claude_code.md" if runner == "claude" else "codex.md"
    phase_file = {
        "design": "design.md",
        "supervisor": "supervisor.md",
        "audit": "audit.md",
        "frame_break": "frame_break.md",
        "expansion": "expansion.md",
        "checkpoint": "checkpoint.md",
    }[phase]

    lines = [
        f"Read agent_prompts/{runner_file}.",
        f"Read agent_prompts/shared/{phase_file}.",
    ]
    if (lab_root / "coordination" / "workspace_map.md").exists():
        lines.append("Read coordination/workspace_map.md first and use it as your navigation surface.")
    if phase != "design":
        lines.append("Read orchestrator.md after the phase prompt.")

    if phase == "supervisor" and not summary.get("runtime_initialized"):
        lines.append("Run `python scripts/bootstrap.py` before supervising the runtime.")
    if phase == "audit":
        lines.append("Read implementation_audit.md and focus on the highest-signal suspicious candidate.")
    if phase == "frame_break":
        lines.append("Read frame_break.md and leave a concrete patch file under `logs/expansions/`.")
    if phase == "expansion":
        lines.append(
            "If no fresh scout requests exist, run `python scripts/operator_helper.py prepare-scout --expansion` first."
        )
        lines.append(
            "After approving a patch, merge it with `python scripts/research_scout.py --merge-expansion --lab-dir <lab>`."
        )

    lines.append("Use only this lab's local files as your operating context.")
    lines.append("Current lab status:")
    lines.append(f"- next phase: {summary['next_phase']}")
    lines.append(f"- runtime initialized: {'yes' if summary.get('runtime_initialized') else 'no'}")
    if summary.get("runtime_initialized"):
        lines.append(f"- active phase: {summary.get('active_phase')}")
        lines.append(f"- queued jobs: {summary.get('queued_jobs')}")
        lines.append(f"- leased jobs: {summary.get('leased_jobs')}")
        lines.append(f"- audit queue: {', '.join(summary.get('audit_queue', [])) or 'none'}")
        lines.append(f"- invalid-fast candidates: {', '.join(summary.get('invalid_fast_candidates', [])) or 'none'}")
        lines.append(f"- global champion: {summary.get('global_champion')}")
        lines.append(f"- family credits: {summary.get('family_credits')}")
    return "\n".join(lines)


def next_prompt(lab_root: Path, runner: str, phase: str) -> int:
    print(prompt_for_phase(lab_root, runner, phase))
    return 0


def prepare_scout(lab_root: Path, args: argparse.Namespace) -> int:
    scout_script = lab_root / "scripts" / "research_scout.py"
    if not scout_script.exists():
        print(f"ERROR: {scout_script} not found.")
        return 1

    cmd = [sys.executable, str(scout_script), "--lab-dir", str(lab_root)]
    if args.family:
        cmd.extend(["--family", args.family])
    elif args.expansion:
        cmd.append("--expansion")
    else:
        print("ERROR: choose --family or --expansion")
        return 1
    return subprocess.run(cmd, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Helper for operating a labrat vNext lab")
    parser.add_argument("--lab-dir", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    readiness = subparsers.add_parser("check-readiness")
    readiness.add_argument("--json", action="store_true")
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--json", action="store_true")
    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true")
    subparsers.add_parser("runtime-summary")

    next_p = subparsers.add_parser("next-prompt")
    next_p.add_argument("--runner", choices=["claude", "codex"], required=True)
    next_p.add_argument(
        "--phase",
        choices=["auto", "design", "supervisor", "audit", "frame_break", "expansion", "checkpoint"],
        default="auto",
    )

    scout = subparsers.add_parser("prepare-scout")
    scout.add_argument("--family", help="Prepare a scout request for one family")
    scout.add_argument("--expansion", action="store_true")

    args = parser.parse_args(argv)
    lab_root = resolve_lab_root(args.lab_dir)

    if args.command == "check-readiness":
        return check_readiness(lab_root, as_json=args.json)
    if args.command == "status":
        return status(lab_root, as_json=args.json)
    if args.command == "doctor":
        return doctor(lab_root, as_json=args.json)
    if args.command == "runtime-summary":
        return runtime_summary(lab_root)
    if args.command == "next-prompt":
        return next_prompt(lab_root, args.runner, args.phase)
    if args.command == "prepare-scout":
        return prepare_scout(lab_root, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
