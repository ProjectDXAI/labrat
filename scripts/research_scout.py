#!/usr/bin/env python3
"""Prepare and merge research-scout artifacts for labrat vNext."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from lab_core import load_json, load_jsonl, load_yaml, now_iso, write_json, write_yaml


def load_state(lab_root: Path) -> dict[str, Any]:
    return {
        "branches": load_yaml(lab_root / "branches.yaml", {}),
        "runtime": load_json(lab_root / "state" / "runtime.json", {}),
        "frontier": load_json(lab_root / "state" / "frontier.json", {}),
        "jobs": load_json(lab_root / "state" / "jobs.json", {"queued": [], "leased": [], "finished": []}),
        "candidates": load_jsonl(lab_root / "state" / "candidates.jsonl"),
        "evaluations": load_jsonl(lab_root / "state" / "evaluations.jsonl"),
    }


def latest_candidates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("candidate_id"):
            latest[row["candidate_id"]] = row
    return latest


def stuck_families(state: dict[str, Any]) -> list[str]:
    frontier = state["frontier"]
    families = []
    for family_name, family_state in frontier.get("family_funding", {}).items():
        if family_state.get("plateau_counter", 0) >= 2:
            families.append(family_name)
    return families


def scout_request_for_family(lab_root: Path, family_name: str, state: dict[str, Any], mode: str) -> Path:
    families = state["branches"].get("families", {})
    family = families.get(family_name, {})
    latest = latest_candidates(state["candidates"])
    champion = state["frontier"].get("family_champions", {}).get(family_name)
    request = {
        "generated_at": now_iso(),
        "mode": mode,
        "family": family_name,
        "mission": state["branches"].get("mission"),
        "family_description": family.get("description"),
        "resource_class": family.get("resource_class", "cpu"),
        "global_champion": state["frontier"].get("global_champion"),
        "family_champion": champion,
        "audit_queue": state["frontier"].get("audit_queue", []),
        "pending_expansion": state["frontier"].get("pending_expansion"),
        "recent_candidates": [
            candidate
            for candidate in latest.values()
            if candidate.get("family") == family_name
        ][-5:],
    }
    out_dir = lab_root / "experiments" / family_name / "scout_requests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{mode}_{family_name}.json"
    write_json(out_path, request)
    return out_path


def merge_expansion(lab_root: Path) -> int:
    branches_path = lab_root / "branches.yaml"
    config = load_yaml(branches_path, {})
    families = config.setdefault("families", {})
    patches = sorted((lab_root / "logs" / "expansions").glob("*patch*.yaml"))
    merged = 0

    for patch in patches:
        data = load_yaml(patch, {})
        for proposal in data.get("proposals", []):
            if proposal.get("approved") is False:
                continue
            branch_name = proposal.get("branch_name")
            branch_yaml = proposal.get("branch_yaml")
            if not branch_name or not isinstance(branch_yaml, dict):
                continue
            if branch_name in families:
                continue
            families[branch_name] = branch_yaml
            merged += 1

    if merged:
        write_yaml(branches_path, config)

        frontier_path = lab_root / "state" / "frontier.json"
        frontier = load_json(frontier_path, {})
        funding = frontier.setdefault("family_funding", {})
        for family_name, family in families.items():
            if family_name in funding:
                continue
            funding[family_name] = {
                "credits": int(family.get("funding", {}).get("initial_credits", family.get("initial_credits", 6))),
                "spent": 0,
                "minted": 0,
                "remaining_cheap_probes": len(family.get("cheap_probes", [])),
                "tried_signatures": [],
                "queued_signatures": [],
                "tried_probe_signatures": [],
                "queued_probe_signatures": [],
                "plateau_counter": 0,
                "last_promoted_at": None,
                "status": "active",
                "exhausted": False,
            }
        frontier["pending_expansion"] = None
        frontier["updated_at"] = now_iso()
        write_json(frontier_path, frontier)

    print(json.dumps({"merged": merged}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare research scout requests or merge expansions")
    parser.add_argument("--lab-dir", type=Path, default=Path.cwd())
    parser.add_argument("--family", default=None)
    parser.add_argument("--expansion", action="store_true")
    parser.add_argument("--merge-expansion", action="store_true")
    args = parser.parse_args(argv)

    lab_root = args.lab_dir.resolve()
    if args.merge_expansion:
        return merge_expansion(lab_root)

    state = load_state(lab_root)
    if args.expansion:
        families = args.family and [args.family] or stuck_families(state) or list((state["branches"].get("families") or {}).keys())[:2]
        created = [str(scout_request_for_family(lab_root, family, state, "expansion")) for family in families]
        frontier = state["frontier"]
        frontier["pending_expansion"] = {"created_at": now_iso(), "families": families, "requests": created}
        write_json(lab_root / "state" / "frontier.json", frontier)
        print(json.dumps({"created": created}, indent=2))
        return 0

    if not args.family:
        parser.error("--family is required unless --expansion or --merge-expansion is used")
    path = scout_request_for_family(lab_root, args.family, state, "family")
    print(json.dumps({"created": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
