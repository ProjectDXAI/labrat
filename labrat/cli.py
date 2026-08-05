"""Installable CLI for operating labrat from a local editable checkout."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from . import __version__


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _ensure_editable_checkout() -> None:
    missing = [path.name for path in (SCRIPTS_DIR, REPO_ROOT / "templates", REPO_ROOT / "profiles") if not path.exists()]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(
            "labrat CLI needs the source checkout layout "
            f"({joined} missing). Reinstall from the repo root with `pip install -e .`."
        )


def _load_module(name: str):
    _ensure_editable_checkout()
    script_path = str(SCRIPTS_DIR)
    if script_path not in sys.path:
        sys.path.insert(0, script_path)
    return importlib.import_module(name)


def _call(module_name: str, argv: list[str]) -> int:
    module = _load_module(module_name)
    return int(module.main(argv))


def _lab_dir_args(path: Path) -> list[str]:
    return ["--lab-dir", str(path.resolve())]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labrat",
        description=(
            "Installable CLI for scaffolding and operating labrat labs. "
            "Use `pip install -e .` from the repo root to keep templates and scripts available."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_cmd = subparsers.add_parser("new", help="Create a new lab from the bundled templates.")
    new_cmd.add_argument("target_dir", help="Target directory for the new lab. Relative paths are resolved from the current directory.")
    new_cmd.add_argument(
        "--profile",
        action="append",
        default=None,
        help="Optional profile to overlay on top of the base templates. Repeat to stack profiles; later profiles win.",
    )

    bootstrap_cmd = subparsers.add_parser("bootstrap", help="Bootstrap a lab runtime.")
    bootstrap_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    bootstrap_cmd.add_argument("--allow-incomplete", action="store_true", help="Bypass Phase 0 validation.")

    readiness_cmd = subparsers.add_parser("check-readiness", help="Validate that Phase 0 files are complete.")
    readiness_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    readiness_cmd.add_argument("--json", action="store_true", help="Print the readiness payload as JSON.")

    status_cmd = subparsers.add_parser("status", help="Show the current lab status.")
    status_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    status_cmd.add_argument("--json", action="store_true", help="Print the status payload as JSON.")

    doctor_cmd = subparsers.add_parser("doctor", help="Run a local health check for a lab.")
    doctor_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    doctor_cmd.add_argument("--json", action="store_true", help="Print the health payload as JSON.")

    runtime_summary_cmd = subparsers.add_parser("runtime-summary", help="Show the current runtime summary.")
    runtime_summary_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")

    next_prompt_cmd = subparsers.add_parser("next-prompt", help="Print the next operator prompt for the selected runner.")
    next_prompt_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    next_prompt_cmd.add_argument("--runner", choices=["claude", "codex"], required=True)
    next_prompt_cmd.add_argument(
        "--phase",
        choices=["auto", "design", "supervisor", "audit", "frame_break", "expansion", "checkpoint"],
        default="auto",
    )

    scout_cmd = subparsers.add_parser("prepare-scout", help="Prepare a research scout request.")
    scout_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    scout_group = scout_cmd.add_mutually_exclusive_group(required=True)
    scout_group.add_argument("--family", help="Prepare a scout request for one family.")
    scout_group.add_argument("--expansion", action="store_true", help="Prepare a scout request for expansion work.")

    corpus_cmd = subparsers.add_parser(
        "corpus",
        help="Map a bibliography network, run scouting rounds, and tag rights.",
    )
    corpus_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. The corpus lives in <lab>/corpus.")
    corpus_cmd.add_argument("--corpus-dir", type=Path, default=None, help="Corpus directory override.")
    corpus_subparsers = corpus_cmd.add_subparsers(dest="corpus_command", required=True)

    corpus_subparsers.add_parser("init", help="Create the corpus workspace.")
    corpus_validate = corpus_subparsers.add_parser("validate", help="Validate the bibliography against the vocabularies.")
    corpus_validate.add_argument("--json", action="store_true")
    corpus_status = corpus_subparsers.add_parser("status", help="Coverage, rights posture, network shape, saturation.")
    corpus_status.add_argument("--json", action="store_true")
    corpus_frontier = corpus_subparsers.add_parser("frontier", help="Rank the next scouting targets.")
    corpus_frontier.add_argument("--bucket", default=None)
    corpus_frontier.add_argument("--limit", type=int, default=25)
    corpus_frontier.add_argument("--json", action="store_true")

    corpus_round = corpus_subparsers.add_parser("round", help="Open or close an iterative scouting round.")
    corpus_round_sub = corpus_round.add_subparsers(dest="round_command", required=True)
    corpus_round_open = corpus_round_sub.add_parser("open")
    corpus_round_open.add_argument("--mode", choices=["expand", "verify", "acquire"], default="expand")
    corpus_round_open.add_argument("--bucket", action="append", default=None)
    corpus_round_open.add_argument("--limit", type=int, default=None)
    corpus_round_close = corpus_round_sub.add_parser("close")
    corpus_round_close.add_argument("--round", type=int, default=None)
    corpus_round_close.add_argument("--findings", type=Path, default=None)
    corpus_round_sub.add_parser("list")

    corpus_rights = corpus_subparsers.add_parser("rights", help="Rights report and verification queue.")
    corpus_rights.add_argument("--verify-queue", action="store_true")
    corpus_rights.add_argument("--bucket", default=None)
    corpus_rights.add_argument("--limit", type=int, default=25)
    corpus_rights.add_argument("--json", action="store_true")

    corpus_manifest = corpus_subparsers.add_parser("manifest", help="Emit the rights-gated build manifest.")
    corpus_manifest.add_argument("--out", type=Path, default=None)
    corpus_graph = corpus_subparsers.add_parser("graph", help="Export the bibliography network.")
    corpus_graph.add_argument("--out", type=Path, default=None)
    corpus_report = corpus_subparsers.add_parser("report", help="Write the markdown corpus report.")
    corpus_report.add_argument("--out", type=Path, default=None)
    corpus_vocab = corpus_subparsers.add_parser("vocab", help="Print the form and rights vocabularies.")
    corpus_vocab.add_argument("--json", action="store_true")

    runtime_cmd = subparsers.add_parser("runtime", help="Access low-level runtime operations.")
    runtime_cmd.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. Defaults to the current directory.")
    runtime_subparsers = runtime_cmd.add_subparsers(dest="runtime_command", required=True)

    runtime_subparsers.add_parser("bootstrap-runtime")
    runtime_summary = runtime_subparsers.add_parser("summary")
    runtime_summary.add_argument("--json", action="store_true")
    runtime_dispatch = runtime_subparsers.add_parser("dispatch")
    runtime_dispatch.add_argument("--queue-depth", type=int, default=None)
    runtime_lease = runtime_subparsers.add_parser("lease")
    runtime_lease.add_argument("--worker-id", required=True)
    runtime_complete = runtime_subparsers.add_parser("complete")
    runtime_complete.add_argument("--candidate-id", required=True)
    runtime_complete.add_argument("--result", type=Path, required=True)
    runtime_complete.add_argument("--worker-id", default=None)
    runtime_subparsers.add_parser("reap")

    subparsers.add_parser("repo-root", help="Print the source checkout that backs this editable install.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "repo-root":
        _ensure_editable_checkout()
        print(REPO_ROOT)
        return 0

    if args.command == "new":
        delegated = [args.target_dir]
        for profile in args.profile or []:
            delegated.extend(["--profile", profile])
        return _call("new_lab", delegated)

    if args.command == "bootstrap":
        delegated = _lab_dir_args(args.lab_dir)
        if args.allow_incomplete:
            delegated.append("--allow-incomplete")
        return _call("bootstrap", delegated)

    if args.command == "check-readiness":
        delegated = _lab_dir_args(args.lab_dir) + ["check-readiness"]
        if args.json:
            delegated.append("--json")
        return _call("operator_helper", delegated)

    if args.command == "status":
        delegated = _lab_dir_args(args.lab_dir) + ["status"]
        if args.json:
            delegated.append("--json")
        return _call("operator_helper", delegated)

    if args.command == "doctor":
        delegated = _lab_dir_args(args.lab_dir) + ["doctor"]
        if args.json:
            delegated.append("--json")
        return _call("operator_helper", delegated)

    if args.command == "runtime-summary":
        return _call("operator_helper", _lab_dir_args(args.lab_dir) + ["runtime-summary"])

    if args.command == "next-prompt":
        delegated = _lab_dir_args(args.lab_dir) + ["next-prompt", "--runner", args.runner, "--phase", args.phase]
        return _call("operator_helper", delegated)

    if args.command == "prepare-scout":
        delegated = _lab_dir_args(args.lab_dir) + ["prepare-scout"]
        if args.family:
            delegated.extend(["--family", args.family])
        else:
            delegated.append("--expansion")
        return _call("operator_helper", delegated)

    if args.command == "corpus":
        delegated = _lab_dir_args(args.lab_dir)
        if args.corpus_dir:
            delegated.extend(["--corpus-dir", str(args.corpus_dir.resolve())])
        delegated.append(args.corpus_command)
        if args.corpus_command == "round":
            delegated.append(args.round_command)
            if args.round_command == "open":
                delegated.extend(["--mode", args.mode])
                for bucket in args.bucket or []:
                    delegated.extend(["--bucket", bucket])
                if args.limit is not None:
                    delegated.extend(["--limit", str(args.limit)])
            if args.round_command == "close":
                if args.round is not None:
                    delegated.extend(["--round", str(args.round)])
                if args.findings:
                    delegated.extend(["--findings", str(args.findings.resolve())])
            return _call("corpus", delegated)

        if args.corpus_command in {"frontier", "rights"}:
            if args.bucket:
                delegated.extend(["--bucket", args.bucket])
            delegated.extend(["--limit", str(args.limit)])
            if args.corpus_command == "rights" and args.verify_queue:
                delegated.append("--verify-queue")
        if args.corpus_command in {"manifest", "graph", "report"} and args.out:
            delegated.extend(["--out", str(args.out.resolve())])
        if getattr(args, "json", False):
            delegated.append("--json")
        return _call("corpus", delegated)

    if args.command == "runtime":
        delegated = _lab_dir_args(args.lab_dir) + [args.runtime_command]
        if args.runtime_command == "summary" and args.json:
            delegated.append("--json")
        if args.runtime_command == "dispatch" and args.queue_depth is not None:
            delegated.extend(["--queue-depth", str(args.queue_depth)])
        if args.runtime_command == "lease":
            delegated.extend(["--worker-id", args.worker_id])
        if args.runtime_command == "complete":
            delegated.extend(["--candidate-id", args.candidate_id, "--result", str(args.result.resolve())])
            if args.worker_id:
                delegated.extend(["--worker-id", args.worker_id])
        return _call("runtime", delegated)

    parser.error(f"Unsupported command: {args.command}")
    return 2
