#!/usr/bin/env python3
"""Load controlled runtime fixtures for audit/frame-break testing."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


LAB_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load a named runtime fixture into state/.")
    parser.add_argument("fixture", choices=["audit", "frame_break"])
    args = parser.parse_args(argv)

    source = LAB_ROOT / "fixtures" / args.fixture / "state"
    target = LAB_ROOT / "state"
    target.mkdir(exist_ok=True)
    for item in source.iterdir():
        shutil.copy2(item, target / item.name)
    print(f"Loaded fixture: {args.fixture}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
