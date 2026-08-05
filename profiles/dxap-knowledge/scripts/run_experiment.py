#!/usr/bin/env python3
"""Retrieval-policy runner.

A candidate here is a *retrieval policy*: which structural filters run, how the
decision-value re-rank is weighted, how many cards are served, whether
counterevidence is required, and how readily the policy abstains. Scoring runs
the policy over the labelled trial set in `knowledge/trials.yaml`.

This is the offline half of Gate 1. It measures whether a policy surfaces the
mechanism a competent analyst would reach for, and whether it stays quiet when
nothing applies. It does not measure whether the mechanism makes money — that is
Gate 2 (behaviour change on real traces) and Gate 3 (a prospective randomized
trial), neither of which can run inside this lab.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import knowledge
import methods as methods_module
from lab_core import write_json


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def problem_coverage(store: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Which diagnosed problems did this policy actually put a concept in front of?"""
    by_concept = {row["concept_id"]: row for row in store["concepts"]}
    all_problems = {problem.get("problem_id") for problem in store["problems"]}
    covered: set[str] = set()
    for row in rows:
        if not row["applicable"]:
            continue
        for concept_id in row["returned"]:
            covered.update(by_concept.get(concept_id, {}).get("problem_ids") or [])
    return {
        "covered": sorted(covered & all_problems),
        "uncovered": sorted(all_problems - covered),
        "fraction": len(covered & all_problems) / len(all_problems) if all_problems else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one retrieval policy against the labelled trial set.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lab-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    started = time.time()
    candidate = json.loads(args.candidate.read_text())
    config = candidate.get("resolved_config") or {}
    lab_root = (args.lab_dir or Path.cwd()).resolve()

    knowledge_dir = lab_root / ((config.get("knowledge") or {}).get("dir") or "knowledge")
    paths = knowledge.knowledge_paths(knowledge_dir)
    if not paths["concepts"].exists():
        write_json(
            args.output,
            {
                "candidate_id": candidate["candidate_id"],
                "valid": False,
                "proxy_metrics": {},
                "metrics": {"search": {"primary_metric": 0.0}, "selection": {"primary_metric": 0.0}, "final": {"primary_metric": 0.0}},
                "failure_class": "data",
                "finding": f"no knowledge store at {paths['concepts']}",
                "resource_floor": None,
            },
        )
        return 0

    store = knowledge.load_store(paths)
    sources = knowledge.load_corpus_sources(lab_root)

    # The gate that matters before any metric: cards that fail the SERVABLE check
    # are not retrievable at all, so a policy cannot be scored on a broken store.
    validation = knowledge.validate_store(store, sources)
    if not validation["ok"]:
        broken = [row for row in validation["concepts"] if not row["servable"]]
        write_json(
            args.output,
            {
                "candidate_id": candidate["candidate_id"],
                "valid": False,
                "proxy_metrics": {"unservable_concepts": len(broken)},
                "metrics": {"search": {"primary_metric": 0.0}, "selection": {"primary_metric": 0.0}, "final": {"primary_metric": 0.0}},
                "failure_class": "data",
                "finding": f"{len(broken)} concept cards fail the SERVABLE gate; fix the store before scoring policies",
                "resource_floor": None,
            },
        )
        return 0

    policy_config = dict(config.get("policy") or {})
    base = policy_config.pop("base", None)
    policy = knowledge.resolve_policy(store, base, policy_config)
    policy["name"] = candidate.get("candidate_id")

    result = knowledge.evaluate_policy(store, sources, policy)
    coverage = problem_coverage(store, result["rows"])

    # Clean-trial scores say whether a policy fits the labelled set. Stress says
    # whether it survives the set being wrong about the world: reworded contexts,
    # a missing observable, distractor cards, restatements, tools down.
    stress = knowledge.stress_policy(store, sources, policy)

    # Tool health is part of the contract: a method whose self-test fails would
    # feed wrong numbers into every packet that cites it.
    tools = methods_module.self_test()

    search = clamp(result["hit_rate"])
    selection = clamp(0.6 * result["precision"] + 0.4 * (1.0 - result["false_abstention_rate"]))
    final = clamp(coverage["fraction"])

    write_json(
        args.output,
        {
            "candidate_id": candidate["candidate_id"],
            "valid": True,
            "proxy_metrics": {
                "trials": result["trials"],
                "hit_rate": round(result["hit_rate"], 4),
                "precision": round(result["precision"], 4),
                "false_abstention_rate": round(result["false_abstention_rate"], 4),
                "mean_context_kilotokens": round(result["mean_context_kilotokens"], 4),
                "mean_latency_seconds": round(result["mean_latency_seconds"], 4),
                "problems_uncovered": coverage["uncovered"],
                "worst_case_retention": stress["worst_case_retention"],
                "integrity_violations": stress["integrity_violations"],
                "weakest_perturbation": min(stress["perturbations"], key=lambda k: stress["perturbations"][k]["retention"]),
                "synthetic_cards_served": sum(row["synthetic_cards_served"] for row in stress["perturbations"].values()),
                "methods_self_test_ok": bool(tools.get("ok")),
                "methods_registered": tools.get("methods"),
                "elapsed_seconds": round(time.time() - started, 3),
            },
            "metrics": {
                "search": {"primary_metric": round(search, 4)},
                "selection": {"primary_metric": round(selection, 4)},
                "final": {"primary_metric": round(final, 4)},
                "challenges": {
                    "non_applicability": {"primary_metric": round(clamp(result["non_applicability_accuracy"]), 4)},
                    "counterevidence_coverage": {"primary_metric": round(clamp(result["counterevidence_coverage"]), 4)},
                    "robustness": {"primary_metric": round(clamp(stress["robustness"]), 4)},
                },
            },
            "failure_class": None if tools.get("ok") else "arch",
            "finding": (
                f"hit {result['hit_rate']:.2f}, precision {result['precision']:.2f}, "
                f"abstains correctly on {result['non_applicability_accuracy']:.2f} of inapplicable contexts, "
                f"counterevidence on {result['counterevidence_coverage']:.2f} of served packets, "
                f"{result['mean_context_kilotokens']:.2f}k tokens per packet; "
                f"robustness {stress['robustness']:.2f} (worst: {min(stress['perturbations'], key=lambda k: stress['perturbations'][k]['retention'])}, "
                f"{stress['integrity_violations']} integrity violations)"
            ),
            "resource_floor": None,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
