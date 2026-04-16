#!/usr/bin/env python3
"""Bootstrap the labrat vNext runtime."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lab_core import find_readiness_issues
from runtime import bootstrap_runtime, save_runtime_files, top_up_queue


SCRIPT_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap a labrat vNext lab")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Bypass Phase 0 validation for maintainers.",
    )
    parser.add_argument(
        "--lab-dir",
        type=Path,
        default=SCRIPT_ROOT,
        help="Path to the lab root. Defaults to the parent of this scripts directory.",
    )
    args = parser.parse_args(argv)
    lab_root = args.lab_dir.resolve()

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
        return 1

    if issues and args.allow_incomplete:
        print("WARNING: bootstrapping an incomplete lab.")
        for issue in issues:
            print(f"  - {issue}")
        print()

    state = bootstrap_runtime(lab_root)
    created = top_up_queue(lab_root, state)
    save_runtime_files(lab_root, state)

    print(f"Runtime bootstrapped at {lab_root}")
    print(f"Queued initial jobs: {created}")
    print()
    print("To start:")
    print("  python -m http.server 8787")
    print("  open http://localhost:8787/dashboard.html")
    print()
    print("Then use the helper:")
    print("  python scripts/operator_helper.py status")
    print("  python scripts/operator_helper.py runtime-summary")
    print("  python scripts/operator_helper.py next-prompt --runner claude --phase auto")
    print("  python scripts/operator_helper.py next-prompt --runner codex --phase auto")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
