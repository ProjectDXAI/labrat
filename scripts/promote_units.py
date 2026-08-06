#!/usr/bin/env python3
"""Declare reading units on held sources that have none.

63 held sources carrying about 15,000 pages have no reading unit at all, so nothing can
be read against them, nothing can be compiled from them, and they cannot pass the
admission gate however good they are. This declares the units for the ones the acquisition
review named, scoped by file rather than page range: a course is dozens of PDFs with page
numbers restarting in each, so `pp. 12-30` across one addresses nothing.

Units are declared unread. Declaring is not reading, and the point of the gate is that
those are different things.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# source_id -> [(unit_id, topic, locator, pages, priority), ...]
UNITS: dict[str, list[tuple[str, str, str, int, int]]] = {
    "mit-ocw-6262-discrete-stochastic-processes": [
        ("renewal-processes-slln", "renewal processes, the strong law, and why a complex process breaks into independent intervals", "file:lec10", 16, 5),
        ("markov-rewards-dynamic-programming", "Markov rewards and dynamic programming: expected reward to an absorbing decision", "file:lec09", 18, 5),
        ("poisson-combining-splitting", "the Poisson process, combining and splitting arrival streams", "file:lec04, file:lec05", 46, 5),
        ("finite-state-markov-chains", "finite-state chains, the transition matrix, eigenvalues and steady state", "file:lec07, file:lec08", 58, 4),
        ("poisson-to-markov", "from Poisson to Markov: continuous-time chains and holding times", "file:lec06", 30, 4),
    ],
    "stanford-ee364a-convex-optimization-notes": [
        ("convex-sets-functions", "convex sets and functions: the vocabulary a market-maker potential has to satisfy", "file:bv_cvxslides.pdf", 54, 4),
        ("duality", "Lagrange duality, KKT, and what a dual variable prices", "file:bv_cvxslides.pdf", 40, 5),
        ("stochastic-programming", "stochastic programming and chance constraints under uncertain outcomes", "file:stoch_prog, file:chance_constr", 42, 5),
        ("filter-design", "filter design as a convex problem", "file:filters", 20, 3),
    ],
    "mit-ocw-18657-high-dimensional-statistics": [
        ("concentration-inequalities", "sub-Gaussian concentration and the tail bounds every estimator error rests on", "file:LecNote", 40, 5),
        ("multiple-testing", "multiple testing and selective inference over many candidate signals", "file:LecNote", 30, 5),
        ("covariance-estimation", "covariance estimation when dimension is comparable to sample size", "file:LecNote", 30, 5),
    ],
    "mit-ocw-6262-linear-algebra-learning-from-data": [
        ("matrix-factorizations", "the factorizations: SVD, eigendecomposition, low-rank structure", "file:ZoomNotes", 40, 4),
    ],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Declare reading units on held sources that have none")
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    path = args.lab / "corpus" / "bibliography.yaml"
    data = yaml.safe_load(path.read_text())
    by_id = {e["id"]: e for e in data["entries"]}

    added, skipped, missing = 0, [], []
    for source_id, units in UNITS.items():
        entry = by_id.get(source_id)
        if entry is None:
            missing.append(source_id)
            continue
        existing = {u.get("unit_id") for u in (entry.get("units") or [])}
        fresh = []
        for unit_id, topic, locator, pages, priority in units:
            if unit_id in existing:
                skipped.append(f"{source_id}#{unit_id}")
                continue
            fresh.append({
                "unit_id": unit_id,
                "title": None,
                "topic": topic,
                "locator": locator,
                "kind": "section",
                "pages": pages,
                "priority": priority,
                "read_status": "unread",
                "concepts_expected": [],
                "notes": None,
            })
        if fresh:
            entry.setdefault("units", [])
            entry["units"].extend(fresh)
            added += len(fresh)

    if not args.dry_run and added:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    print(json.dumps({
        "units_added": added,
        "already_present": skipped,
        "source_not_found": missing,
    }, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
