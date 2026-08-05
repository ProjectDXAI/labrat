#!/usr/bin/env python3
"""Attribution ledger: from offered card to realized outcome.

Self-reported "I used the source" is not evidence. This ledger records the chain
explicitly so each rung can be counted separately:

    offered -> served -> inspected -> semantically used -> tool-changing
            -> behaviour-changing -> economically beneficial

Only the last rung requires matured outcomes, and only a randomized comparison
licenses the word "beneficial". The analysis here refuses to compute an effect
when outcomes have not matured or the batch is not frozen, because the failure
mode this module exists to prevent is a retrieval layer that updates on its own
unmatured results.

Inference is clustered at the unit of randomization (branch or branch-day), not
at the wake. Thousands of wakes inside one account path are not thousands of
independent observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable

from lab_core import append_jsonl, load_jsonl, now_iso, write_json


EVENT_TYPES = [
    "retrieval_event",   # what was offered, by which policy, in which arm
    "inspection",        # which cards the agent actually opened
    "tool_call",         # deterministic method runs that followed retrieval
    "claim",             # a reasoning claim the agent attributed to a card
    "decision",          # action before and after treatment, plus order ids
    "outcome",           # matured, net-of-cost result for a decision
]

LADDER = [
    "offered",
    "served",
    "inspected",
    "semantically_used",
    "tool_changing",
    "behaviour_changing",
    "economically_beneficial",
]


def ledger_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "events": root / "events.jsonl",
        "assignments": root / "assignments.json",
        "analysis": root / "analysis.json",
    }


# --------------------------------------------------------------------------------------
# Randomization
# --------------------------------------------------------------------------------------


def assign_arm(unit_id: str, arms: list[str], seed: str) -> str:
    """Deterministic hash-based assignment.

    Hashing rather than sampling means an assignment can be recomputed from the
    unit id alone, months later, without storing a random state — and it cannot
    drift when the analysis is re-run.
    """
    digest = hashlib.sha256(f"{seed}|{unit_id}".encode()).hexdigest()
    return arms[int(digest[:16], 16) % len(arms)]


def assign_units(unit_ids: Iterable[str], arms: list[str], seed: str) -> dict[str, str]:
    return {unit_id: assign_arm(unit_id, arms, seed) for unit_id in sorted(set(unit_ids))}


# --------------------------------------------------------------------------------------
# Ladder
# --------------------------------------------------------------------------------------


def index_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, list[dict[str, Any]]] = {name: [] for name in EVENT_TYPES}
    for event in events:
        by_type.setdefault(event.get("event_type"), []).append(event)
    return by_type


def ladder(events: list[dict[str, Any]], group_by: str = "concept_id") -> dict[str, Any]:
    """Count each rung per concept (or per family, when the events carry one)."""
    by_type = index_events(events)
    retrievals = {row["retrieval_event_id"]: row for row in by_type.get("retrieval_event", []) if row.get("retrieval_event_id")}

    def key_for(concept_id: str, event: dict[str, Any]) -> str:
        if group_by == "concept_id":
            return concept_id
        return str(event.get(group_by) or "unknown")

    counts: dict[str, dict[str, int]] = {}

    def bump(key: str, rung: str, amount: int = 1) -> None:
        counts.setdefault(key, {rung_name: 0 for rung_name in LADDER})[rung] += amount

    for event in by_type.get("retrieval_event", []):
        for concept_id in event.get("concept_ids_offered") or []:
            bump(key_for(concept_id, event), "offered")
        if not event.get("abstained"):
            for concept_id in event.get("concept_ids_served") or event.get("concept_ids_offered") or []:
                bump(key_for(concept_id, event), "served")

    for event in by_type.get("inspection", []):
        parent = retrievals.get(event.get("retrieval_event_id"), {})
        for concept_id in event.get("concept_ids_opened") or []:
            bump(key_for(concept_id, parent), "inspected")

    for event in by_type.get("claim", []):
        parent = retrievals.get(event.get("retrieval_event_id"), {})
        if event.get("concept_id"):
            bump(key_for(event["concept_id"], parent), "semantically_used")

    for event in by_type.get("tool_call", []):
        parent = retrievals.get(event.get("retrieval_event_id"), {})
        for concept_id in event.get("concept_ids") or (parent.get("concept_ids_served") or []):
            bump(key_for(concept_id, parent), "tool_changing")

    decisions_by_id: dict[str, dict[str, Any]] = {}
    for event in by_type.get("decision", []):
        decisions_by_id[event.get("decision_id")] = event
        parent = retrievals.get(event.get("retrieval_event_id"), {})
        changed = event.get("action_after_treatment") != event.get("action_before_treatment")
        if changed:
            for concept_id in event.get("concept_ids") or (parent.get("concept_ids_served") or []):
                bump(key_for(concept_id, parent), "behaviour_changing")

    for event in by_type.get("outcome", []):
        decision = decisions_by_id.get(event.get("decision_id"))
        if not decision or not event.get("matured"):
            continue
        if (event.get("realized_net") or 0.0) <= 0:
            continue
        parent = retrievals.get(decision.get("retrieval_event_id"), {})
        if decision.get("action_after_treatment") == decision.get("action_before_treatment"):
            continue  # no behaviour change means the outcome is not attributable to the card
        for concept_id in decision.get("concept_ids") or (parent.get("concept_ids_served") or []):
            bump(key_for(concept_id, parent), "economically_beneficial")

    rows = []
    for key, rungs in sorted(counts.items()):
        row = {group_by: key, **rungs}
        row["served_rate"] = round(rungs["served"] / rungs["offered"], 3) if rungs["offered"] else None
        row["use_rate"] = round(rungs["semantically_used"] / rungs["served"], 3) if rungs["served"] else None
        row["behaviour_rate"] = round(rungs["behaviour_changing"] / rungs["served"], 3) if rungs["served"] else None
        rows.append(row)
    rows.sort(key=lambda row: (-row["offered"], row[group_by]))
    return {"group_by": group_by, "rows": rows, "ladder": LADDER}


# --------------------------------------------------------------------------------------
# Clustered analysis
# --------------------------------------------------------------------------------------


def _bootstrap_difference(
    treatment: list[float],
    control: list[float],
    iterations: int = 2000,
    seed: int = 1337,
) -> dict[str, Any]:
    """Cluster bootstrap with a fixed LCG so the interval is reproducible."""
    if not treatment or not control:
        return {"difference": None, "ci_low": None, "ci_high": None, "note": "an arm has no clusters"}

    state = seed
    def next_index(modulus: int) -> int:
        nonlocal state
        state = (1103515245 * state + 12345) % (2 ** 31)
        return state % modulus

    observed = statistics.fmean(treatment) - statistics.fmean(control)
    differences: list[float] = []
    for _ in range(iterations):
        sample_t = [treatment[next_index(len(treatment))] for _ in treatment]
        sample_c = [control[next_index(len(control))] for _ in control]
        differences.append(statistics.fmean(sample_t) - statistics.fmean(sample_c))
    differences.sort()
    low = differences[int(0.025 * len(differences))]
    high = differences[int(0.975 * len(differences)) - 1]
    return {
        "difference": round(observed, 6),
        "ci_low": round(low, 6),
        "ci_high": round(high, 6),
        "crosses_zero": low <= 0.0 <= high,
        "clusters": {"treatment": len(treatment), "control": len(control)},
    }


def analyze(
    events: list[dict[str, Any]],
    cluster_field: str = "branch_id",
    control_arm: str = "baseline",
    as_of: str | None = None,
    require_frozen: bool = True,
) -> dict[str, Any]:
    """Compare arms on cluster-level net outcomes.

    Refuses rather than guesses when outcomes are unmatured or the batch is not
    frozen. An effect estimate computed mid-batch is exactly the artifact this
    ledger is meant to prevent.
    """
    by_type = index_events(events)
    outcomes = by_type.get("outcome", [])
    decisions = {row.get("decision_id"): row for row in by_type.get("decision", [])}

    unmatured = [row for row in outcomes if not row.get("matured")]
    if as_of:
        unmatured += [
            row for row in outcomes
            if row.get("outcome_maturity_time") and str(row["outcome_maturity_time"]) > str(as_of)
        ]
    if unmatured:
        return {
            "refused": "outcomes have not matured",
            "unmatured": len(unmatured),
            "hint": "wait for the maturity time, or pass --as-of after it",
        }
    frozen = all(row.get("frozen_batch") for row in outcomes) if outcomes else False
    if require_frozen and not frozen:
        return {
            "refused": "batch is not marked frozen",
            "hint": "policy and retrieval must not update inside a rollout batch; mark frozen_batch when the batch closes",
        }

    clusters: dict[tuple[str, str], list[float]] = {}
    for outcome in outcomes:
        decision = decisions.get(outcome.get("decision_id")) or {}
        arm = outcome.get("arm") or decision.get("arm")
        cluster = outcome.get(cluster_field) or decision.get(cluster_field)
        if not arm or not cluster:
            continue
        clusters.setdefault((arm, str(cluster)), []).append(float(outcome.get("realized_net") or 0.0))

    by_arm: dict[str, list[float]] = {}
    for (arm, _cluster), values in sorted(clusters.items()):
        by_arm.setdefault(arm, []).append(statistics.fmean(values))

    control = by_arm.get(control_arm, [])
    comparisons = {
        arm: _bootstrap_difference(values, control)
        for arm, values in sorted(by_arm.items())
        if arm != control_arm
    }

    return {
        "generated_at": now_iso(),
        "cluster_field": cluster_field,
        "control_arm": control_arm,
        "arms": {
            arm: {
                "clusters": len(values),
                "mean_net": round(statistics.fmean(values), 6),
                "median_net": round(statistics.median(values), 6),
            }
            for arm, values in sorted(by_arm.items())
        },
        "comparisons": comparisons,
        "note": (
            "Cluster-level means. A comparison whose interval crosses zero is not evidence of benefit, "
            "however many wakes are behind it."
        ),
    }


def utility_posteriors(events: list[dict[str, Any]], prior_strength: float = 6.0) -> dict[str, Any]:
    """P(useful | concept, decision type) from matured, behaviour-changing outcomes.

    Feeds knowledge.py's `historical_utility` re-ranking term. Shrunk hard toward
    the global base rate so a concept with three lucky trades does not jump the
    queue.
    """
    by_type = index_events(events)
    decisions = {row.get("decision_id"): row for row in by_type.get("decision", [])}
    retrievals = {row.get("retrieval_event_id"): row for row in by_type.get("retrieval_event", [])}

    observations: list[tuple[str, str, float]] = []
    for outcome in by_type.get("outcome", []):
        if not outcome.get("matured") or not outcome.get("frozen_batch"):
            continue
        decision = decisions.get(outcome.get("decision_id"))
        if not decision:
            continue
        if decision.get("action_after_treatment") == decision.get("action_before_treatment"):
            continue
        parent = retrievals.get(decision.get("retrieval_event_id"), {})
        concept_ids = decision.get("concept_ids") or parent.get("concept_ids_served") or []
        decision_type = decision.get("decision_type") or "all"
        success = 1.0 if float(outcome.get("realized_net") or 0.0) > 0 else 0.0
        for concept_id in concept_ids:
            observations.append((concept_id, decision_type, success))

    if not observations:
        return {"generated_at": now_iso(), "concepts": {}, "note": "no matured behaviour-changing outcomes yet"}

    base_rate = statistics.fmean([row[2] for row in observations])
    grouped: dict[tuple[str, str], list[float]] = {}
    for concept_id, decision_type, success in observations:
        grouped.setdefault((concept_id, decision_type), []).append(success)
        grouped.setdefault((concept_id, "all"), []).append(success)

    payload: dict[str, Any] = {}
    for (concept_id, decision_type), values in sorted(grouped.items()):
        posterior = (sum(values) + prior_strength * base_rate) / (len(values) + prior_strength)
        payload.setdefault(concept_id, {})[decision_type] = {
            "posterior_mean": round(posterior, 4),
            "n": len(values),
            "raw_rate": round(statistics.fmean(values), 4),
        }
    return {"generated_at": now_iso(), "base_rate": round(base_rate, 4), "concepts": payload}


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def _synthetic_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index in range(6):
        arm = "treatment" if index % 2 == 0 else "baseline"
        branch = f"branch-{index}"
        retrieval_id = f"r{index}"
        events.append(
            {
                "event_type": "retrieval_event",
                "retrieval_event_id": retrieval_id,
                "arm": arm,
                "branch_id": branch,
                "concept_ids_offered": ["KC-A", "KC-B"],
                "concept_ids_served": ["KC-A"],
                "abstained": False,
            }
        )
        events.append({"event_type": "inspection", "retrieval_event_id": retrieval_id, "concept_ids_opened": ["KC-A"]})
        events.append({"event_type": "claim", "retrieval_event_id": retrieval_id, "concept_id": "KC-A", "claim_text": "flow is informed"})
        events.append({"event_type": "tool_call", "retrieval_event_id": retrieval_id, "method_id": "order_flow_imbalance", "concept_ids": ["KC-A"]})
        events.append(
            {
                "event_type": "decision",
                "decision_id": f"d{index}",
                "retrieval_event_id": retrieval_id,
                "arm": arm,
                "branch_id": branch,
                "decision_type": "entry",
                "concept_ids": ["KC-A"],
                "action_before_treatment": "enter",
                "action_after_treatment": "abstain" if arm == "treatment" else "enter",
            }
        )
        events.append(
            {
                "event_type": "outcome",
                "decision_id": f"d{index}",
                "arm": arm,
                "branch_id": branch,
                "matured": True,
                "frozen_batch": True,
                "outcome_maturity_time": "2026-01-01T00:00:00Z",
                "realized_net": 12.0 if arm == "treatment" else -4.0,
            }
        )
    return events


def _synthetic_utility_events() -> list[dict[str, Any]]:
    """Two concepts with different hit rates, so shrinkage is observable."""
    events: list[dict[str, Any]] = []
    plan = [("KC-A", 12.0), ("KC-A", 12.0), ("KC-A", -5.0), ("KC-C", -3.0), ("KC-C", -3.0), ("KC-C", -3.0)]
    for index, (concept_id, net) in enumerate(plan):
        retrieval_id = f"u{index}"
        events.append(
            {
                "event_type": "retrieval_event",
                "retrieval_event_id": retrieval_id,
                "arm": "treatment",
                "branch_id": f"ubranch-{index}",
                "concept_ids_offered": [concept_id],
                "concept_ids_served": [concept_id],
                "abstained": False,
            }
        )
        events.append(
            {
                "event_type": "decision",
                "decision_id": f"ud{index}",
                "retrieval_event_id": retrieval_id,
                "arm": "treatment",
                "branch_id": f"ubranch-{index}",
                "decision_type": "entry",
                "concept_ids": [concept_id],
                "action_before_treatment": "enter",
                "action_after_treatment": "abstain",
            }
        )
        events.append(
            {
                "event_type": "outcome",
                "decision_id": f"ud{index}",
                "arm": "treatment",
                "branch_id": f"ubranch-{index}",
                "matured": True,
                "frozen_batch": True,
                "outcome_maturity_time": "2026-01-01T00:00:00Z",
                "realized_net": net,
            }
        )
    return events


def self_test() -> dict[str, Any]:
    checks: list[str] = []
    events = _synthetic_events()

    rungs = ladder(events)
    row = next(r for r in rungs["rows"] if r["concept_id"] == "KC-A")
    assert row["offered"] == 6 and row["served"] == 6, row
    assert row["inspected"] == 6 and row["semantically_used"] == 6, row
    assert row["behaviour_changing"] == 3, row
    assert row["economically_beneficial"] == 3, row
    offered_only = next(r for r in rungs["rows"] if r["concept_id"] == "KC-B")
    assert offered_only["offered"] == 6 and offered_only["served"] == 0, offered_only
    checks.append("ladder: offered/served/inspected/used/behaviour/beneficial counted separately")

    result = analyze(events, cluster_field="branch_id", control_arm="baseline")
    assert result.get("comparisons"), result
    treatment = result["comparisons"]["treatment"]
    assert treatment["difference"] == 16.0, treatment
    assert not treatment["crosses_zero"], treatment
    assert treatment["clusters"] == {"treatment": 3, "control": 3}, treatment
    checks.append("analyze: cluster-level difference with a reproducible bootstrap interval")

    unmatured = [dict(event, matured=False) if event["event_type"] == "outcome" else event for event in events]
    refusal = analyze(unmatured)
    assert refusal.get("refused") == "outcomes have not matured", refusal
    unfrozen = [dict(event, frozen_batch=False) if event["event_type"] == "outcome" else event for event in events]
    assert analyze(unfrozen).get("refused") == "batch is not marked frozen", analyze(unfrozen)
    checks.append("analyze: refuses unmatured outcomes and unfrozen batches")

    posteriors = utility_posteriors(_synthetic_utility_events())
    winner = posteriors["concepts"]["KC-A"]["entry"]
    loser = posteriors["concepts"]["KC-C"]["entry"]
    assert winner["n"] == 3 and winner["raw_rate"] > 0.6, winner
    assert posteriors["base_rate"] < winner["raw_rate"], posteriors["base_rate"]
    assert posteriors["base_rate"] < winner["posterior_mean"] < winner["raw_rate"], (posteriors["base_rate"], winner)
    assert loser["posterior_mean"] > loser["raw_rate"], loser
    assert winner["posterior_mean"] > loser["posterior_mean"], (winner, loser)
    checks.append("utility_posteriors: shrunk toward the base rate from both directions, never a raw win rate")

    arms = assign_units([f"branch-{i}" for i in range(200)], ["baseline", "treatment"], seed="dxap-2026")
    counts = {arm: sum(1 for value in arms.values() if value == arm) for arm in ["baseline", "treatment"]}
    assert 70 <= counts["treatment"] <= 130, counts
    assert assign_arm("branch-7", ["baseline", "treatment"], "dxap-2026") == arms["branch-7"], "assignment must be recomputable"
    checks.append("assignment: deterministic, recomputable, roughly balanced")

    return {"ok": True, "checks": checks}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def cmd_record(args: argparse.Namespace) -> int:
    paths = ledger_paths((args.lab_dir / "logs" / "ledger").resolve() if not args.ledger_dir else args.ledger_dir.resolve())
    payload = json.loads(args.event.read_text()) if args.event else json.loads(args.json_event or "{}")
    if payload.get("event_type") not in EVENT_TYPES:
        raise SystemExit(f"ERROR: event_type must be one of {', '.join(EVENT_TYPES)}")
    payload.setdefault("recorded_at", now_iso())
    append_jsonl(paths["events"], payload)
    print(json.dumps({"recorded": payload["event_type"], "events_file": str(paths["events"])}, indent=2))
    return 0


def _load(args: argparse.Namespace) -> tuple[dict[str, Path], list[dict[str, Any]]]:
    paths = ledger_paths((args.lab_dir / "logs" / "ledger").resolve() if not args.ledger_dir else args.ledger_dir.resolve())
    return paths, load_jsonl(paths["events"])


def cmd_ladder(args: argparse.Namespace) -> int:
    _, events = _load(args)
    result = ladder(events, group_by=args.group_by)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    header = f"{args.group_by:<28}" + "".join(f"{rung[:12]:>14}" for rung in LADDER)
    print(header)
    for row in result["rows"]:
        print(f"{str(row[args.group_by]):<28}" + "".join(f"{row[rung]:>14}" for rung in LADDER))
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    paths, events = _load(args)
    result = analyze(
        events,
        cluster_field=args.cluster_field,
        control_arm=args.control_arm,
        as_of=args.as_of,
        require_frozen=not args.allow_unfrozen,
    )
    write_json(paths["analysis"], result)
    print(json.dumps(result, indent=2))
    return 1 if result.get("refused") else 0


def cmd_utility(args: argparse.Namespace) -> int:
    paths, events = _load(args)
    payload = utility_posteriors(events)
    out = args.out or (args.lab_dir / "knowledge" / "utility.json")
    write_json(out, payload.get("concepts") or {})
    print(json.dumps({"utility_file": str(out), "concepts": len(payload.get("concepts") or {}), "base_rate": payload.get("base_rate")}, indent=2))
    return 0


def cmd_assign(args: argparse.Namespace) -> int:
    paths, _ = _load(args)
    units = json.loads(args.units.read_text()) if args.units else []
    assignments = assign_units(units, args.arm, args.seed)
    write_json(paths["assignments"], {"seed": args.seed, "arms": args.arm, "assignments": assignments})
    print(json.dumps({"assigned": len(assignments), "file": str(paths["assignments"])}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Attribution ledger for retrieval, decisions and outcomes")
    parser.add_argument("--lab-dir", type=Path, default=Path.cwd())
    parser.add_argument("--ledger-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    record_cmd = sub.add_parser("record", help="Append one event.")
    record_cmd.add_argument("--event", type=Path, default=None, help="JSON file holding the event.")
    record_cmd.add_argument("--json-event", default=None, help="Inline JSON event.")

    ladder_cmd = sub.add_parser("ladder", help="Count the offered-to-beneficial rungs.")
    ladder_cmd.add_argument("--group-by", default="concept_id")
    ladder_cmd.add_argument("--json", action="store_true")

    analyze_cmd = sub.add_parser("analyze", help="Cluster-level arm comparison on matured outcomes.")
    analyze_cmd.add_argument("--cluster-field", default="branch_id")
    analyze_cmd.add_argument("--control-arm", default="baseline")
    analyze_cmd.add_argument("--as-of", default=None)
    analyze_cmd.add_argument("--allow-unfrozen", action="store_true", help="Compute anyway. Exploratory only; never for a decision.")

    utility_cmd = sub.add_parser("utility", help="Write concept utility posteriors for retrieval re-ranking.")
    utility_cmd.add_argument("--out", type=Path, default=None)

    assign_cmd = sub.add_parser("assign", help="Deterministically assign units to arms.")
    assign_cmd.add_argument("--units", type=Path, required=True, help="JSON list of unit ids (branch or branch-day).")
    assign_cmd.add_argument("--arm", action="append", required=True)
    assign_cmd.add_argument("--seed", required=True)

    sub.add_parser("self-test", help="Check the ladder, the refusals, and the bootstrap on synthetic events.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    handlers = {
        "record": cmd_record,
        "ladder": cmd_ladder,
        "analyze": cmd_analyze,
        "utility": cmd_utility,
        "assign": cmd_assign,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
