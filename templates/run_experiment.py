#!/usr/bin/env python3
"""Placeholder experiment runner for new labrat vNext labs.

Customize this file for your domain. It should read `candidate.json`,
execute the experiment, and write `result.json` with at least:

{
  "candidate_id": "...",
  "valid": true,
  "proxy_metrics": {},
  "metrics": {
    "search": {"primary_metric": 0.0},
    "selection": {"primary_metric": 0.0},
    "final": {"primary_metric": 0.0}
  },
  "finding": "one sentence",
  "resource_floor": null
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Placeholder runner for labrat vNext.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    with open(args.candidate) as f:
        candidate = json.load(f)

    payload = {
        "candidate_id": candidate["candidate_id"],
        "valid": False,
        "proxy_metrics": {},
        "metrics": {
            "search": {"primary_metric": 0.0},
            "selection": {"primary_metric": 0.0},
            "final": {"primary_metric": 0.0},
            "error": "Customize scripts/run_experiment.py for your domain.",
        },
        "finding": "placeholder runner was not replaced",
        "resource_floor": None,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
