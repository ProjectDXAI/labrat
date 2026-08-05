#!/usr/bin/env python3
"""Corpus round runner.

A candidate here is a *scouting policy*, not a model: which bucket to work, in
which mode, how deep, and through which discovery channel. Running the candidate
opens a bounded round against the bibliography network and writes a request the
scout can execute. Scoring happens when the findings come back.

The loop is therefore two-phase per candidate:

  1. first run   -> opens the round, writes `request.md`, returns
                    `failure_class: awaiting_findings` (valid=false, not scored)
  2. second run  -> merges `findings.yaml`, closes the round, and scores it

That is deliberate. The runtime should not invent bibliographic facts; the scout
supplies them and the runtime keeps the accounting honest.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import corpus
from lab_core import load_json, load_yaml, write_json


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def resolve_corpus_dir(lab_root: Path, config: dict[str, Any]) -> Path:
    configured = (config.get("corpus") or {}).get("dir")
    return (lab_root / configured).resolve() if configured else (lab_root / "corpus").resolve()


def bind_round(
    paths: dict[str, Path],
    binding_path: Path,
    candidate: dict[str, Any],
    policy: dict[str, Any],
) -> int:
    """Return the round this candidate owns, opening one if it has none yet."""
    binding = load_json(binding_path, {})
    if binding.get("round"):
        return int(binding["round"])

    entries = corpus.load_bibliography(paths)
    taxonomy = corpus.load_taxonomy(paths)
    state = corpus.load_state(paths)
    request = corpus.open_round(
        paths,
        entries,
        taxonomy,
        state,
        mode=policy.get("mode", "expand"),
        buckets=list(policy.get("buckets") or []),
        limit=int(policy.get("limit") or 20),
    )

    number = request["round"]
    request_path = corpus.round_dir(paths, number) / "request.json"
    stored = load_json(request_path, {})
    stored["candidate_id"] = candidate.get("candidate_id")
    stored["family"] = candidate.get("family")
    stored["channel"] = policy.get("channel")
    stored["channel_brief"] = policy.get("channel_brief")
    write_json(request_path, stored)

    # Restate the channel in the human-facing brief so the scout reads it with the targets.
    request_md = corpus.round_dir(paths, number) / "request.md"
    if request_md.exists() and policy.get("channel"):
        text = request_md.read_text()
        banner = (
            f"\n> **Discovery channel for this round: `{policy['channel']}`**\n>\n"
            f"> {policy.get('channel_brief') or 'Work this channel only, so the round measures the channel.'}\n"
        )
        request_md.write_text(text.replace("## What to do\n", "## What to do\n" + banner, 1))

    write_json(binding_path, {"round": number, "corpus_dir": str(paths["root"]), "opened_by": candidate.get("candidate_id")})
    return number


def findings_count(paths: dict[str, Path], number: int) -> int:
    findings = load_yaml(corpus.round_dir(paths, number) / "findings.yaml", {}) or {}
    return len(findings.get("entries") or [])


def score_round(report: dict[str, Any], policy: dict[str, Any], scoring: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    """Turn one closed round into the labrat metric contract.

    search      — raw productivity of the policy (new works and closed frontier targets)
    selection   — legally usable value added (pages that cleared the manifest gate)
    final       — how much of the touched buckets' page target is now cleared
    challenges  — the two things volume alone cannot buy: cross-domain bridges and
                  rights clearance
    """
    yield_target = float(scoring.get("yield_target") or max(4, int(policy.get("limit") or 20) * 0.4))
    pages_target = float(scoring.get("eligible_pages_target") or 2000)

    new_entries = int(report.get("new_entries") or 0)
    resolved = len(report.get("resolved_frontier") or [])
    updated = len(report.get("updated") or [])

    search = clamp((new_entries + 0.5 * resolved + 0.25 * updated) / yield_target)

    eligible_delta = int(report.get("eligible_pages_delta") or 0)
    confirmed_delta = int(report.get("rights_confirmed_delta") or 0)
    selection = clamp(0.65 * (eligible_delta / pages_target) + 0.35 * clamp(confirmed_delta / max(1.0, yield_target)))

    buckets = report.get("buckets") or list(status["buckets"].keys())
    progress = []
    for name in buckets:
        row = status["buckets"].get(name)
        if not row or not row["target_pages"]:
            continue
        progress.append(row["pages_manifest_eligible"] / row["target_pages"])
    final = clamp(sum(progress) / len(progress)) if progress else 0.0

    # Decisive challenge 1: did this round connect literatures, or only pile up pages?
    bridges_delta = int(report.get("bridges_delta") or 0)
    bridge_discovery = clamp(bridges_delta / max(1.0, new_entries or 1.0))

    # Decisive challenge 2: did the round leave its finds legally usable or just listed?
    touched = new_entries + updated
    rights_clearance = clamp(confirmed_delta / touched) if touched else 0.0

    return {
        "search": {"primary_metric": round(search, 4)},
        "selection": {"primary_metric": round(selection, 4)},
        "final": {"primary_metric": round(final, 4)},
        "challenges": {
            "bridge_discovery": {"primary_metric": round(bridge_discovery, 4)},
            "rights_clearance": {"primary_metric": round(rights_clearance, 4)},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one corpus scouting round as a labrat candidate.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lab-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    started = time.time()
    candidate = json.loads(args.candidate.read_text())
    config = candidate.get("resolved_config") or {}
    policy = dict(config.get("policy") or {})
    scoring = dict(config.get("scoring") or {})

    lab_root = (args.lab_dir or Path.cwd()).resolve()
    paths = corpus.corpus_paths(resolve_corpus_dir(lab_root, config))
    if not paths["bibliography"].exists():
        write_json(
            args.output,
            {
                "candidate_id": candidate["candidate_id"],
                "valid": False,
                "proxy_metrics": {},
                "metrics": {"search": {"primary_metric": 0.0}, "selection": {"primary_metric": 0.0}, "final": {"primary_metric": 0.0}},
                "failure_class": "no_corpus",
                "finding": f"no bibliography at {paths['bibliography']}; run `labrat corpus init` first",
                "resource_floor": None,
            },
        )
        return 0

    binding_path = args.output.parent / "corpus_round.json"
    number = bind_round(paths, binding_path, candidate, policy)
    directory = corpus.round_dir(paths, number)
    report = load_json(directory / "merge_report.json", {})

    if not report:
        if findings_count(paths, number) == 0:
            write_json(
                args.output,
                {
                    "candidate_id": candidate["candidate_id"],
                    "valid": False,
                    "proxy_metrics": {"round": number, "elapsed_seconds": round(time.time() - started, 3)},
                    "metrics": {"search": {"primary_metric": 0.0}, "selection": {"primary_metric": 0.0}, "final": {"primary_metric": 0.0}},
                    "failure_class": "awaiting_findings",
                    "finding": (
                        f"round {number:03d} is open and waiting on a scout. "
                        f"Brief: {directory / 'request.md'} — write findings to {directory / 'findings.yaml'}, then re-run this candidate."
                    ),
                    "resource_floor": None,
                },
            )
            return 0

        entries = corpus.load_bibliography(paths)
        taxonomy = corpus.load_taxonomy(paths)
        state = corpus.load_state(paths)
        report = corpus.close_round(paths, entries, taxonomy, state, number, None)

    entries = corpus.load_bibliography(paths)
    taxonomy = corpus.load_taxonomy(paths)
    state = corpus.load_state(paths)
    status = corpus.status_payload(entries, taxonomy, state)
    metrics = score_round(report, policy, scoring, status)

    touched = [name for name in (report.get("buckets") or []) if name in status["buckets"]]
    saturated = [name for name in touched if status["buckets"][name]["saturation"] == "saturated"]

    write_json(
        args.output,
        {
            "candidate_id": candidate["candidate_id"],
            "valid": True,
            "proxy_metrics": {
                "round": number,
                "mode": report.get("mode"),
                "channel": policy.get("channel"),
                "new_entries": report.get("new_entries"),
                "updated_entries": len(report.get("updated") or []),
                "frontier_resolved": len(report.get("resolved_frontier") or []),
                "frontier_open": report.get("unresolved_frontier"),
                "rediscovery_rate": report.get("rediscovery_rate"),
                "eligible_pages_delta": report.get("eligible_pages_delta"),
                "rights_confirmed_delta": report.get("rights_confirmed_delta"),
                "bridges_delta": report.get("bridges_delta"),
                "entries_total": report.get("entries_total"),
                "corpus_eligible_pages": status["pages_manifest_eligible"],
                "elapsed_seconds": round(time.time() - started, 3),
            },
            "metrics": metrics,
            "failure_class": "saturated" if saturated and not report.get("new_entries") else None,
            "finding": (
                f"round {number:03d} ({report.get('mode')}, channel={policy.get('channel') or 'unset'}): "
                f"+{report.get('new_entries')} entries, {len(report.get('resolved_frontier') or [])} frontier targets closed, "
                f"+{report.get('eligible_pages_delta')} manifest-eligible pages, "
                f"rediscovery {report.get('rediscovery_rate')}"
                + (f"; saturated: {', '.join(saturated)}" if saturated else "")
            ),
            "resource_floor": None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
