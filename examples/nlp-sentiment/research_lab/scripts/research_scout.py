#!/usr/bin/env python3
"""Delegate to the repo scout helper for the flagship example."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]


def main() -> int:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "research_scout.py"),
        "--lab-dir",
        str(LAB_ROOT),
        *sys.argv[1:],
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
