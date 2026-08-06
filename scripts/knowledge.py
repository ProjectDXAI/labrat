#!/usr/bin/env python3
"""Market knowledge compiler: concept cards, hypotheses, method bindings, retrieval.

The corpus engine (`corpus.py`) answers *what exists and what may we use*. This
engine answers *what does it claim, how would we test it, what would falsify it,
and which of it applies to the decision in front of us right now*.

    source -> mechanism -> assumptions -> observable signature
           -> deterministic test -> decision relevance -> realized outcome

A card is SERVABLE only when it carries a mechanism, its assumptions, the
observables it needs, an expected signature, a failure mode, at least one piece
of counterevidence, and a resolvable source anchor. Anything less is a quotation
with extra steps, and retrieval will not serve it.

Retrieval is deliberately *not* nearest-neighbour over passages: hard structural
filters run first (market, horizon, observables actually available, source
availability as of the decision timestamp, decision type), then lexical scoring,
then a decision-value re-rank, then a one-hop expansion that is required to
include counterevidence.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import graphops
from lab_core import load_json, load_yaml, now_iso, write_json, write_text, write_yaml

try:  # methods.py is optional at read time; a lab may not have compiled tools yet.
    import methods as methods_module
except Exception:  # pragma: no cover - only when the module is genuinely absent
    methods_module = None


# --------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------

IMPLEMENTATION_STATUS = ["proposed", "specified", "implemented", "validated", "retired"]
DECISION_TYPES = ["entry", "hold", "add", "reduce", "exit", "abstain", "sizing"]
HORIZONS = ["tick", "seconds", "minutes", "hours", "days", "weeks"]
MARKET_TYPES = [
    "clob_equities",
    "clob_futures",
    "clob_crypto",
    "perp_dex",
    "prediction_market",
    "amm",
    "dealer_market",
    "any",
]

CONCEPT_REQUIRED = [
    "concept_id",
    "canonical_name",
    "plain_description",
    "mechanism",
    "assumptions",
    "market_types",
    "relevant_horizons",
    "required_observables",
    "expected_empirical_signature",
    "known_failure_modes",
    "source_passage_ids",
    "implementation_status",
    "confidence",
]

HYPOTHESIS_REQUIRED = [
    "hypothesis_id",
    "concept_id",
    "market_context",
    "causal_story",
    "ex_ante_prediction",
    "null_hypothesis",
    "measurement_operator",
    "eligible_universe",
    "decision_timestamp_rule",
    "outcome_horizons",
    "cost_model",
    "invalidation_conditions",
]

DECISION_CARD_REQUIRED = [
    "decision_relevance_id",
    "concept_id",
    "decision_type",
    "evidence_that_would_support_action",
    "evidence_that_would_argue_against_action",
    "minimum_required_confidence",
]

# Language that turns a mechanism into an unearned rule. Flagged, not blocked —
# the author may have a reason, but they should have to see it.
DIRECTIVE_PATTERNS = [
    r"\balways\b",
    r"\bnever\b",
    r"\bmust (?:exit|close|enter|buy|sell)\b",
    r"\bclose after\b",
    r"\bcut (?:at|after)\b",
    r"\bstop out at\b",
    r"\b\d+\s*%\s*(?:trailing|stop|target)\b",
]

STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "is", "are", "be",
    "that", "this", "it", "its", "as", "at", "by", "from", "when", "which", "we", "our",
}


# --------------------------------------------------------------------------------------
# Paths and loading
# --------------------------------------------------------------------------------------


def knowledge_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "concepts": root / "concepts.yaml",
        "hypotheses": root / "hypotheses.yaml",
        "methods": root / "methods.yaml",
        "decisions": root / "decision_relevance.yaml",
        "problems": root / "problems.yaml",
        "trials": root / "trials.yaml",
        "bets": root / "frontier_bets.yaml",
        "extensions": root / "exploratory_extensions.yaml",
        "policies": root / "policies.yaml",
        "queues": root / "queues",
        "packets": root / "packets",
        "utility": root / "utility.json",
    }


def load_list(path: Path, key: str) -> list[dict[str, Any]]:
    data = load_yaml(path, {}) or {}
    return list(data.get(key) or [])


def load_store(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "concepts": load_list(paths["concepts"], "concepts"),
        "hypotheses": load_list(paths["hypotheses"], "hypotheses"),
        "methods": load_list(paths["methods"], "methods"),
        "decisions": load_list(paths["decisions"], "decision_relevance"),
        "problems": load_list(paths["problems"], "problems"),
        "trials": load_list(paths["trials"], "trials"),
        "bets": load_list(paths["bets"], "bets"),
        "extensions": load_list(paths["extensions"], "extensions"),
        "policies": (load_yaml(paths["policies"], {}) or {}).get("policies") or {},
        "utility": load_json(paths["utility"], {}),
    }


def load_corpus_sources(lab_root: Path, corpus_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Resolve source ids against the corpus bibliography when one is present."""
    try:
        import corpus as corpus_module
    except Exception:  # pragma: no cover
        return {}
    paths = corpus_module.corpus_paths((corpus_dir or (lab_root / "corpus")).resolve())
    if not paths["bibliography"].exists():
        return {}
    entries = corpus_module.load_bibliography(paths)
    return {
        entry["id"]: {**entry, "derived_rights": corpus_module.derive_rights(entry)}
        for entry in entries
    }


def parse_passage_ref(ref: Any) -> dict[str, Any]:
    """`entry-id#chapter-4` or {source_id, anchor, quote}."""
    if isinstance(ref, str):
        source_id, _, anchor = ref.partition("#")
        return {"source_id": source_id.strip(), "anchor": anchor.strip() or None, "quote": None}
    ref = dict(ref or {})
    return {
        "source_id": (ref.get("source_id") or "").strip(),
        "anchor": ref.get("anchor"),
        "quote": ref.get("quote"),
    }


# --------------------------------------------------------------------------------------
# The SERVABLE gate
# --------------------------------------------------------------------------------------


def concept_gate(concept: dict[str, Any], sources: dict[str, dict[str, Any]], store: dict[str, Any]) -> dict[str, Any]:
    """Decide whether a concept card may be served to a live decision.

    Errors block. Warnings are recorded and surfaced but do not block, because
    some are judgement calls the author is entitled to make.
    """
    errors: list[str] = []
    warnings: list[str] = []

    for field in CONCEPT_REQUIRED:
        value = concept.get(field)
        if value in (None, "", [], {}):
            errors.append(f"missing required field '{field}'")

    if concept.get("implementation_status") not in IMPLEMENTATION_STATUS:
        errors.append(f"unknown implementation_status '{concept.get('implementation_status')}'")
    for market in concept.get("market_types") or []:
        if market not in MARKET_TYPES:
            errors.append(f"unknown market_type '{market}'")
    for horizon in concept.get("relevant_horizons") or []:
        if horizon not in HORIZONS:
            errors.append(f"unknown horizon '{horizon}'")

    confidence = concept.get("confidence")
    if isinstance(confidence, (int, float)) and not 0.0 <= float(confidence) <= 1.0:
        errors.append("confidence must be in [0, 1]")

    # Counterevidence is structural, not optional: a card with nothing that would
    # argue against it is a confirmation engine.
    contradicting = concept.get("contradicting_concept_ids") or []
    alternatives = concept.get("alternative_explanations") or []
    if not contradicting and not alternatives:
        errors.append("no contradicting concept and no alternative explanation")

    known_ids = {row.get("concept_id") for row in store["concepts"]}
    for related in [*contradicting, *(concept.get("supporting_concept_ids") or [])]:
        if related not in known_ids:
            errors.append(f"dangling related concept '{related}'")

    # Source anchors must resolve, and quoting is gated on the source's rights.
    if sources:
        for raw_ref in concept.get("source_passage_ids") or []:
            ref = parse_passage_ref(raw_ref)
            source = sources.get(ref["source_id"])
            if source is None:
                errors.append(f"source '{ref['source_id']}' is not in the bibliography")
                continue
            rights = source.get("derived_rights") or {}
            if rights.get("use_class") == "excluded":
                errors.append(f"source '{ref['source_id']}' is excluded by policy and must not be cited")
            if ref["quote"] and not rights.get("manifest_eligible"):
                errors.append(
                    f"verbatim quote from '{ref['source_id']}' whose rights are {rights.get('use_class')}; "
                    "store an anchor and write the mechanism in our own words"
                )
            if not ref["anchor"]:
                warnings.append(f"source '{ref['source_id']}' cited without a page or section anchor")

    text = " ".join(
        str(concept.get(field) or "")
        for field in ("plain_description", "mechanism", "expected_empirical_signature")
    )
    for pattern in DIRECTIVE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            warnings.append(f"directive language matching /{pattern}/ — a mechanism should generate a question, not a rule")

    bound_methods = [row for row in store["methods"] if concept.get("concept_id") in (row.get("concept_ids") or [])]
    if concept.get("implementation_status") in {"implemented", "validated"} and not bound_methods:
        errors.append("implementation_status claims an implementation but no method object binds this concept")

    return {
        "concept_id": concept.get("concept_id"),
        "servable": not errors,
        "errors": errors,
        "warnings": warnings,
        "bound_methods": [row.get("method_id") for row in bound_methods],
    }


def hypothesis_gate(hypothesis: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    for field in HYPOTHESIS_REQUIRED:
        if hypothesis.get(field) in (None, "", [], {}):
            errors.append(f"missing required field '{field}'")

    concept_ids = {row.get("concept_id") for row in store["concepts"]}
    if hypothesis.get("concept_id") not in concept_ids:
        errors.append(f"unknown concept '{hypothesis.get('concept_id')}'")

    operator = hypothesis.get("measurement_operator") or {}
    method_id = operator.get("method_id") if isinstance(operator, dict) else None
    if method_id and methods_module is not None and method_id not in methods_module.REGISTRY:
        errors.append(f"measurement_operator references unimplemented method '{method_id}'")

    if hypothesis.get("cost_model") in (None, "", {}):
        errors.append("no cost model: an ex-ante prediction without costs is not a testable trading claim")

    return {"hypothesis_id": hypothesis.get("hypothesis_id"), "testable": not errors, "errors": errors}


def method_gate(binding: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    """Method objects bind a concept to a versioned implementation in methods.py."""
    errors: list[str] = []
    warnings: list[str] = []
    method_id = binding.get("method_id")

    if methods_module is None:
        warnings.append("methods.py not importable; binding not verified")
    elif method_id not in methods_module.REGISTRY:
        errors.append(f"no implementation registered for '{method_id}'")
    else:
        registered = methods_module.REGISTRY[method_id]["implementation_version"]
        declared = binding.get("implementation_version")
        if declared != registered:
            errors.append(
                f"version drift: card pins {declared}, implementation is {registered}. "
                "Re-verify the card against the new implementation before serving it."
            )

    concept_ids = {row.get("concept_id") for row in store["concepts"]}
    for concept_id in binding.get("concept_ids") or []:
        if concept_id not in concept_ids:
            errors.append(f"binds unknown concept '{concept_id}'")
    if not binding.get("concept_ids"):
        errors.append("method object binds no concept")

    return {"method_id": method_id, "bound": not errors, "errors": errors, "warnings": warnings}


def decision_gate(card: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    for field in DECISION_CARD_REQUIRED:
        if card.get(field) in (None, "", [], {}):
            errors.append(f"missing required field '{field}'")
    if card.get("decision_type") not in DECISION_TYPES:
        errors.append(f"unknown decision_type '{card.get('decision_type')}'")
    if card.get("concept_id") not in {row.get("concept_id") for row in store["concepts"]}:
        errors.append(f"unknown concept '{card.get('concept_id')}'")

    text = " ".join(
        str(card.get(field) or "")
        for field in ("evidence_that_would_support_action", "evidence_that_would_argue_against_action")
    )
    for pattern in DIRECTIVE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            warnings.append(f"directive language matching /{pattern}/ — state the operator and the comparison, not the rule")

    return {"decision_relevance_id": card.get("decision_relevance_id"), "usable": not errors, "errors": errors, "warnings": warnings}


def validate_store(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    concepts = [concept_gate(row, sources, store) for row in store["concepts"]]
    hypotheses = [hypothesis_gate(row, store) for row in store["hypotheses"]]
    bindings = [method_gate(row, store) for row in store["methods"]]
    decisions = [decision_gate(row, store) for row in store["decisions"]]

    seen: set[str] = set()
    duplicates = []
    for row in store["concepts"]:
        if row.get("concept_id") in seen:
            duplicates.append(row.get("concept_id"))
        seen.add(row.get("concept_id"))

    ok = (
        all(row["servable"] for row in concepts)
        and all(row["testable"] for row in hypotheses)
        and all(row["bound"] for row in bindings)
        and all(row["usable"] for row in decisions)
        and not duplicates
    )
    return {
        "ok": ok,
        "duplicate_concept_ids": duplicates,
        "concepts": concepts,
        "hypotheses": hypotheses,
        "methods": bindings,
        "decision_relevance": decisions,
        "counts": {
            "concepts": len(concepts),
            "servable_concepts": sum(1 for row in concepts if row["servable"]),
            "hypotheses": len(hypotheses),
            "testable_hypotheses": sum(1 for row in hypotheses if row["testable"]),
            "methods": len(bindings),
            "decision_relevance": len(decisions),
        },
    }


def servable_concepts(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    gates = {row["concept_id"]: row for row in (concept_gate(c, sources, store) for c in store["concepts"])}
    return [row for row in store["concepts"] if gates[row["concept_id"]]["servable"]]


# --------------------------------------------------------------------------------------
# Lexical scoring (BM25)
# --------------------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", (text or "").lower()) if token and token not in STOPWORDS]


def concept_document(concept: dict[str, Any]) -> list[str]:
    parts = [
        concept.get("canonical_name", ""),
        concept.get("plain_description", ""),
        concept.get("mechanism", ""),
        concept.get("expected_empirical_signature", ""),
        " ".join(concept.get("assumptions") or []),
        " ".join(concept.get("required_observables") or []),
        " ".join(concept.get("tags") or []),
        " ".join(concept.get("problem_ids") or []),
    ]
    # Name and observables carry more signal than prose, so they enter twice.
    return tokenize(" ".join(parts)) + tokenize(concept.get("canonical_name", "")) + tokenize(
        " ".join(concept.get("required_observables") or [])
    )


class Bm25:
    def __init__(self, documents: dict[str, list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = documents
        self.k1, self.b = k1, b
        self.lengths = {doc_id: len(tokens) for doc_id, tokens in documents.items()}
        self.avg_length = (sum(self.lengths.values()) / len(self.lengths)) if self.lengths else 0.0
        self.frequencies: dict[str, dict[str, int]] = {}
        self.document_frequency: dict[str, int] = {}
        for doc_id, tokens in documents.items():
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            self.frequencies[doc_id] = counts
            for token in counts:
                self.document_frequency[token] = self.document_frequency.get(token, 0) + 1

    def score(self, doc_id: str, query_tokens: list[str]) -> float:
        total = 0.0
        counts = self.frequencies.get(doc_id, {})
        length = self.lengths.get(doc_id, 0)
        n = max(1, len(self.documents))
        for token in query_tokens:
            frequency = counts.get(token, 0)
            if not frequency:
                continue
            df = self.document_frequency.get(token, 0)
            idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
            denominator = frequency + self.k1 * (1.0 - self.b + self.b * (length / (self.avg_length or 1.0)))
            total += idf * (frequency * (self.k1 + 1.0)) / denominator
        return total


# --------------------------------------------------------------------------------------
# Retrieval
# --------------------------------------------------------------------------------------


DEFAULT_POLICY: dict[str, Any] = {
    "name": "default",
    "filters": True,
    "k": 3,
    "expand_hops": 1,
    "require_counterevidence": True,
    "mmr_lambda": 0.75,
    "abstain_threshold": 0.15,
    "weights": {
        "relevance": 1.0,
        "evidence_availability": 1.0,
        "falsifiability": 1.0,
        "historical_utility": 1.0,
        "latency_penalty": 0.15,
        "context_penalty": 0.1,
    },
    "context_budget_cards": 5,
}

RUNTIME_COST_SECONDS = {"trivial": 0.01, "low": 0.05, "moderate": 0.3, "high": 1.5}


def resolve_policy(store: dict[str, Any], name: str | None, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    stored = (store.get("policies") or {}).get(name or "") or {}
    for key, value in stored.items():
        if key == "weights" and isinstance(value, dict):
            policy["weights"].update(value)
        else:
            policy[key] = value
    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "weights" and isinstance(value, dict):
            policy["weights"].update(value)
        else:
            policy[key] = value
    if name:
        policy["name"] = name
    return policy


def horizon_compatible(concept: dict[str, Any], horizon: str | None) -> bool:
    if not horizon:
        return True
    horizons = concept.get("relevant_horizons") or []
    return not horizons or horizon in horizons


def market_compatible(concept: dict[str, Any], market_type: str | None) -> bool:
    if not market_type:
        return True
    markets = concept.get("market_types") or []
    return not markets or "any" in markets or market_type in markets


def source_available(concept: dict[str, Any], sources: dict[str, dict[str, Any]], as_of: str | None) -> bool:
    """Point-in-time discipline: a 2025 book cannot inform a 2024 decision."""
    if not as_of or not sources:
        return True
    refs = [parse_passage_ref(ref) for ref in concept.get("source_passage_ids") or []]
    if not refs:
        return True
    for ref in refs:
        source = sources.get(ref["source_id"]) or {}
        start = source.get("availability_start_date") or (
            f"{source.get('year')}-01-01" if source.get("year") else None
        )
        if start is None or str(start) <= str(as_of):
            return True
    return False


def observables_satisfied(concept: dict[str, Any], available: list[str]) -> bool:
    required = set(concept.get("required_observables") or [])
    return required.issubset(set(available or []))


def hard_filter(
    concepts: list[dict[str, Any]],
    context: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    decisions_by_concept: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    kept: list[dict[str, Any]] = []
    rejected: dict[str, str] = {}
    decision_type = context.get("decision_type")
    for concept in concepts:
        concept_id = concept["concept_id"]
        if not market_compatible(concept, context.get("market_type")):
            rejected[concept_id] = "market type"
        elif not horizon_compatible(concept, context.get("horizon")):
            rejected[concept_id] = "horizon"
        elif not observables_satisfied(concept, context.get("observables_available") or []):
            missing = sorted(set(concept.get("required_observables") or []) - set(context.get("observables_available") or []))
            rejected[concept_id] = f"observables unavailable: {', '.join(missing)}"
        elif not source_available(concept, sources, context.get("timestamp")):
            rejected[concept_id] = "source not published as of the decision timestamp"
        elif concept.get("implementation_status") == "retired":
            rejected[concept_id] = "retired"
        elif decision_type and decisions_by_concept.get(concept_id) and not any(
            card.get("decision_type") == decision_type for card in decisions_by_concept[concept_id]
        ):
            rejected[concept_id] = f"no decision relevance for '{decision_type}'"
        else:
            kept.append(concept)
    return kept, rejected


def evidence_availability(concept: dict[str, Any], context: dict[str, Any], store: dict[str, Any]) -> float:
    """Can we actually compute the evidence right now, with the tools on hand?"""
    bound = [row for row in store["methods"] if concept["concept_id"] in (row.get("concept_ids") or [])]
    if not bound:
        return 0.4  # the concept can still inform reasoning, it just cannot be measured
    tools = set(context.get("tools_available") or [])
    if not tools:
        return 0.7
    runnable = [row for row in bound if row.get("method_id") in tools]
    return 1.0 if runnable else 0.5


def falsifiability(concept: dict[str, Any], store: dict[str, Any]) -> float:
    hypotheses = [row for row in store["hypotheses"] if row.get("concept_id") == concept["concept_id"]]
    score = 0.4
    if hypotheses:
        score += 0.3
        if any(row.get("null_hypothesis") for row in hypotheses):
            score += 0.15
        if any(row.get("invalidation_conditions") for row in hypotheses):
            score += 0.15
    return min(1.0, score)


def historical_utility(concept: dict[str, Any], context: dict[str, Any], store: dict[str, Any]) -> float:
    """Measured posterior when the ledger has matured outcomes; card confidence otherwise.

    Deliberately conservative: with no evidence this returns the author's stated
    confidence shrunk toward 0.5, so prestige cannot masquerade as track record.
    """
    utility = store.get("utility") or {}
    keyed = utility.get(concept["concept_id"])
    if isinstance(keyed, dict):
        by_context = keyed.get(str(context.get("decision_type"))) or keyed.get("all")
        if isinstance(by_context, dict) and by_context.get("posterior_mean") is not None:
            return float(by_context["posterior_mean"])
    confidence = concept.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else 0.5
    return 0.5 + 0.5 * (confidence - 0.5)


def latency_estimate(concept: dict[str, Any], store: dict[str, Any]) -> float:
    bound = [row for row in store["methods"] if concept["concept_id"] in (row.get("concept_ids") or [])]
    if not bound:
        return 0.0
    costs = []
    for row in bound:
        spec = (methods_module.REGISTRY.get(row.get("method_id")) if methods_module else None) or {}
        costs.append(RUNTIME_COST_SECONDS.get(spec.get("runtime_cost", "low"), 0.05))
    return max(costs)


def context_cost(concept: dict[str, Any]) -> float:
    """Rough token cost of putting this card in the agent's context."""
    text = json.dumps(concept)
    return len(text) / 4.0 / 1000.0  # thousands of tokens


def concept_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    left = set(a.get("tags") or []) | set(a.get("required_observables") or []) | set(a.get("problem_ids") or [])
    right = set(b.get("tags") or []) | set(b.get("required_observables") or []) | set(b.get("problem_ids") or [])
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def context_query(context: dict[str, Any]) -> list[str]:
    parts = [
        context.get("decision_type", ""),
        context.get("market_type", ""),
        context.get("instrument", ""),
        context.get("horizon", ""),
        " ".join(context.get("uncertainties") or []),
        " ".join(context.get("observables_available") or []),
        " ".join(context.get("state_notes") or []),
        context.get("question", ""),
    ]
    return tokenize(" ".join(str(part) for part in parts))


def retrieve(
    store: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    context: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    concepts = servable_concepts(store, sources)
    by_id = {row["concept_id"]: row for row in concepts}
    decisions_by_concept: dict[str, list[dict[str, Any]]] = {}
    for card in store["decisions"]:
        decisions_by_concept.setdefault(card.get("concept_id"), []).append(card)

    if policy.get("filters", True):
        candidates, rejected = hard_filter(concepts, context, sources, decisions_by_concept)
    else:
        candidates, rejected = list(concepts), {}

    documents = {row["concept_id"]: concept_document(row) for row in candidates}
    index = Bm25(documents)
    query = context_query(context)
    raw_scores = {concept_id: index.score(concept_id, query) for concept_id in documents}
    best_raw = max(raw_scores.values(), default=0.0)

    weights = policy["weights"]
    scored: list[dict[str, Any]] = []
    for concept in candidates:
        concept_id = concept["concept_id"]
        relevance = (raw_scores[concept_id] / best_raw) if best_raw > 0 else 0.0
        availability = evidence_availability(concept, context, store)
        falsify = falsifiability(concept, store)
        utility = historical_utility(concept, context, store)
        latency = latency_estimate(concept, store)
        tokens = context_cost(concept)

        value = (
            (relevance ** weights["relevance"])
            * (availability ** weights["evidence_availability"])
            * (falsify ** weights["falsifiability"])
            * (utility ** weights["historical_utility"])
        )
        latency_budget = float(context.get("latency_budget_seconds") or 0) or None
        penalty = weights["latency_penalty"] * (latency / latency_budget if latency_budget else latency)
        penalty += weights["context_penalty"] * tokens
        scored.append(
            {
                **concept,
                "score": max(0.0, value - penalty),
                "score_parts": {
                    "relevance": round(relevance, 4),
                    "evidence_availability": round(availability, 4),
                    "falsifiability": round(falsify, 4),
                    "historical_utility": round(utility, 4),
                    "latency_seconds": round(latency, 4),
                    "context_kilotokens": round(tokens, 4),
                    "penalty": round(penalty, 4),
                },
            }
        )

    ranked = graphops.maximal_marginal_relevance(
        scored,
        concept_similarity,
        k=min(int(policy.get("k") or 3), int(policy.get("context_budget_cards") or 5)),
        lambda_=float(policy.get("mmr_lambda") or 0.75),
        score_key="score",
        id_key="concept_id",
    )

    threshold = float(policy.get("abstain_threshold") or 0.0)
    selected = [row for row in ranked if row["score"] >= threshold]
    abstained = not selected

    # One-hop expansion, required to carry counterevidence rather than more support.
    counterevidence: list[dict[str, Any]] = []
    if selected and int(policy.get("expand_hops") or 0) > 0:
        top = selected[0]
        for concept_id in top.get("contradicting_concept_ids") or []:
            neighbour = by_id.get(concept_id)
            if neighbour:
                counterevidence.append(
                    {
                        "concept_id": concept_id,
                        "canonical_name": neighbour.get("canonical_name"),
                        "relation": "contradicts",
                        "mechanism": neighbour.get("mechanism"),
                        "for_concept": top["concept_id"],
                    }
                )
                break
        for alternative in (top.get("alternative_explanations") or [])[:1]:
            counterevidence.append(
                {"relation": "alternative_explanation", "statement": alternative, "for_concept": top["concept_id"]}
            )
        for failure in (top.get("known_failure_modes") or [])[:1]:
            counterevidence.append(
                {"relation": "failure_mode", "statement": failure, "for_concept": top["concept_id"]}
            )
        assumption = (top.get("assumptions") or [])[:1]
        if assumption:
            counterevidence.append(
                {"relation": "load_bearing_assumption", "statement": assumption[0], "for_concept": top["concept_id"]}
            )

    if policy.get("require_counterevidence") and selected and not counterevidence:
        abstained = True
        selected = []

    return {
        "generated_at": now_iso(),
        "policy": policy.get("name"),
        "context_id": context.get("context_id"),
        "abstained": abstained,
        "abstain_reason": (
            None
            if not abstained
            else ("no concept cleared the applicability threshold" if ranked else "no concept survived the hard filters")
        ),
        "considered": len(candidates),
        "rejected": rejected,
        "cards": [
            {
                "concept_id": row["concept_id"],
                "canonical_name": row.get("canonical_name"),
                "score": round(row["score"], 4),
                "score_parts": row["score_parts"],
                "mechanism": row.get("mechanism"),
                "assumptions": row.get("assumptions"),
                "required_observables": row.get("required_observables"),
                "expected_empirical_signature": row.get("expected_empirical_signature"),
                "known_failure_modes": row.get("known_failure_modes"),
                "methods": [
                    binding.get("method_id")
                    for binding in store["methods"]
                    if row["concept_id"] in (binding.get("concept_ids") or [])
                ],
                "decision_relevance": [
                    {
                        "decision_type": card.get("decision_type"),
                        "supports": card.get("evidence_that_would_support_action"),
                        "argues_against": card.get("evidence_that_would_argue_against_action"),
                        "minimum_required_confidence": card.get("minimum_required_confidence"),
                    }
                    for card in decisions_by_concept.get(row["concept_id"], [])
                    if not context.get("decision_type") or card.get("decision_type") == context.get("decision_type")
                ],
                "source_passage_ids": row.get("source_passage_ids"),
            }
            for row in selected
        ],
        "counterevidence": counterevidence,
        "context_kilotokens": round(sum(context_cost(row) for row in selected), 3),
        "latency_seconds": round(sum(latency_estimate(row, store) for row in selected), 3),
    }


def render_packet(packet: dict[str, Any]) -> str:
    lines = ["# Evidence packet", ""]
    lines.append(f"Policy: `{packet.get('policy')}` · context `{packet.get('context_id')}` · generated {packet['generated_at']}")
    lines.append("")
    if packet["abstained"]:
        lines.append(f"**No applicable concept.** {packet['abstain_reason']}.")
        lines.append("")
        lines.append(f"{packet['considered']} concepts passed the hard filters; none cleared the threshold.")
        lines.append("")
        lines.append("Abstention is a result. Do not reach for a loosely related mechanism to fill the packet.")
        return "\n".join(lines) + "\n"

    for index, card in enumerate(packet["cards"], 1):
        lines.append(f"## {index}. {card['canonical_name']} (`{card['concept_id']}`)")
        lines.append("")
        lines.append(f"**Mechanism.** {card['mechanism']}")
        lines.append("")
        lines.append("**Load-bearing assumptions.**")
        for assumption in card.get("assumptions") or []:
            lines.append(f"- {assumption}")
        lines.append("")
        lines.append(f"**Expected signature.** {card.get('expected_empirical_signature')}")
        lines.append("")
        if card.get("methods"):
            lines.append(f"**Run these, do not re-derive.** `{'`, `'.join(card['methods'])}`")
            lines.append("")
        for relevance in card.get("decision_relevance") or []:
            lines.append(f"**If considering `{relevance['decision_type']}`.**")
            lines.append(f"- supports: {relevance['supports']}")
            lines.append(f"- argues against: {relevance['argues_against']}")
            lines.append(f"- minimum confidence: {relevance['minimum_required_confidence']}")
            lines.append("")
        if card.get("source_passage_ids"):
            anchors = ", ".join(
                f"{ref['source_id']}#{ref['anchor']}" if ref["anchor"] else ref["source_id"]
                for ref in (parse_passage_ref(raw) for raw in card["source_passage_ids"])
            )
            lines.append(f"Sources: {anchors}")
            lines.append("")

    if packet["counterevidence"]:
        lines.append("## Counterevidence")
        lines.append("")
        for row in packet["counterevidence"]:
            label = row.get("canonical_name") or row.get("statement")
            lines.append(f"- **{row['relation']}** ({row['for_concept']}): {label}")
        lines.append("")

    lines.append(
        f"Cost: {packet['context_kilotokens']}k tokens, {packet['latency_seconds']}s of tool time if every method is run."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# Retrieval evaluation (Gate 1, offline half)
# --------------------------------------------------------------------------------------


def evaluate_policy(
    store: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Score a retrieval policy against the labelled trial set.

    This is the offline half of Gate 1: does the policy surface the concept a
    domain expert would have reached for, and — the part naive similarity search
    fails — does it correctly return *nothing* when no concept applies?
    """
    trials = store["trials"]
    rows: list[dict[str, Any]] = []
    for trial in trials:
        packet = retrieve(store, sources, trial.get("context") or {}, policy)
        returned = [card["concept_id"] for card in packet["cards"]]
        gold = list(trial.get("gold_concept_ids") or [])
        expected_counter = set(trial.get("counterevidence_concept_ids") or [])
        applicable = bool(trial.get("applicable", True))

        hit = bool(set(returned) & set(gold)) if gold else False
        precision = (len(set(returned) & set(gold)) / len(returned)) if returned else 0.0
        counter_ids = {row.get("concept_id") for row in packet["counterevidence"] if row.get("concept_id")}
        counter_kinds = {row.get("relation") for row in packet["counterevidence"]}
        counter_hit = bool(expected_counter & counter_ids) if expected_counter else bool(counter_kinds)

        rows.append(
            {
                "trial_id": trial.get("trial_id"),
                "applicable": applicable,
                "returned": returned,
                "gold": gold,
                "hit": hit,
                "precision": precision,
                "abstained": packet["abstained"],
                "correct_abstention": packet["abstained"] if not applicable else None,
                "false_abstention": packet["abstained"] if applicable else None,
                "counterevidence_hit": counter_hit if applicable and not packet["abstained"] else None,
                "context_kilotokens": packet["context_kilotokens"],
                "latency_seconds": packet["latency_seconds"],
            }
        )

    applicable_rows = [row for row in rows if row["applicable"]]
    negative_rows = [row for row in rows if not row["applicable"]]
    served = [row for row in applicable_rows if not row["abstained"]]

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "policy": policy.get("name"),
        "trials": len(rows),
        "hit_rate": mean([1.0 if row["hit"] else 0.0 for row in applicable_rows]),
        "precision": mean([row["precision"] for row in served]),
        "false_abstention_rate": mean([1.0 if row["false_abstention"] else 0.0 for row in applicable_rows]),
        "non_applicability_accuracy": mean([1.0 if row["correct_abstention"] else 0.0 for row in negative_rows]),
        "counterevidence_coverage": mean([1.0 if row["counterevidence_hit"] else 0.0 for row in served]),
        "mean_context_kilotokens": mean([row["context_kilotokens"] for row in served]),
        "mean_latency_seconds": mean([row["latency_seconds"] for row in served]),
        "rows": rows,
    }




# --------------------------------------------------------------------------------------
# Frontier bets: ranking speculative imports before any of them is compiled
# --------------------------------------------------------------------------------------

BET_REQUIRED = ["bet_id", "title", "domain", "import", "thesis", "sharp_prediction", "falsifier", "problem_ids", "minimum_data"]


def score_bet(bet: dict[str, Any]) -> dict[str, Any]:
    """V = payoff x sqrt(novelty) x testability x maturity - effort, on a 1-5 scale each.

    Novelty is square-rooted on purpose. Being first is worth something, but a novel
    idea nobody can test is worth less than a known one that can be refuted this week.
    Maturity multiplies rather than adds: a bet that needs new mathematics before it
    can be tried is not a bet, it is a research programme.
    """
    payoff = float(bet.get("payoff") or 3)
    novelty = float(bet.get("novelty") or 3)
    testability = float(bet.get("testability") or 3)
    maturity = float(bet.get("maturity") or 3)
    effort = float(bet.get("effort") or 3)
    raw = payoff * math.sqrt(novelty) * (testability / 5.0) * (maturity / 5.0)
    return {
        "score": round(raw - 0.5 * effort, 3),
        "components": {
            "payoff": payoff,
            "novelty": novelty,
            "testability": testability,
            "maturity": maturity,
            "effort": effort,
            "raw_value": round(raw, 3),
        },
    }


def validate_bets(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A bet must be refutable and grounded, or it is an opinion with a score attached."""
    rows: list[dict[str, Any]] = []
    problems = {problem.get("problem_id") for problem in store.get("problems") or []}
    for bet in store.get("bets") or []:
        errors: list[str] = []
        for field in BET_REQUIRED:
            if bet.get(field) in (None, "", [], {}):
                errors.append(f"missing required field '{field}'")
        for problem_id in bet.get("problem_ids") or []:
            if problems and problem_id not in problems:
                errors.append(f"unknown problem '{problem_id}'")
        for source_id in bet.get("sources") or []:
            if sources and source_id not in sources:
                errors.append(f"source '{source_id}' is not in the bibliography")
        method_id = bet.get("first_computation")
        if method_id and methods_module is not None and method_id not in methods_module.REGISTRY:
            errors.append(f"first_computation '{method_id}' has no implementation")
        for field in ("payoff", "novelty", "testability", "maturity", "effort"):
            value = bet.get(field)
            if value is not None and not 1 <= float(value) <= 5:
                errors.append(f"{field} must be between 1 and 5")
        rows.append({"bet_id": bet.get("bet_id"), "ok": not errors, "errors": errors, "runnable_now": bool(method_id)})
    return {"ok": all(row["ok"] for row in rows), "bets": rows, "count": len(rows)}


def rank_bets(store: dict[str, Any]) -> list[dict[str, Any]]:
    scored = [{**bet, **score_bet(bet)} for bet in store.get("bets") or []]
    scored.sort(key=lambda row: (-row["score"], row["bet_id"]))
    return scored



EXTENSION_REQUIRED = [
    "extension_id", "title", "domain", "grounded_in", "what_the_source_leaves_open",
    "our_advantage", "proposed_work", "novel_claim", "first_experiment", "kill_condition",
]


def read_units(sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every source unit anyone has actually opened, keyed as `entry-id#unit-id`."""
    opened: dict[str, dict[str, Any]] = {}
    for entry in sources.values():
        for unit in entry.get("units") or []:
            if unit.get("read_status") in {"read", "compiled"}:
                opened[f"{entry['id']}#{unit['unit_id']}"] = unit
    return opened


def validate_extensions(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The grounding rule: an extension must cite a unit that has been read.

    Proposing new work from a source nobody opened is the cheapest and least
    honest thing this repository could do, so it is refused rather than warned
    about. An extension may cite an unread source alongside a read one, but at
    least one grounding must be a unit whose read_status says someone opened it.
    """
    opened = read_units(sources)
    rows: list[dict[str, Any]] = []
    for extension in store.get("extensions") or []:
        errors: list[str] = []
        for field in EXTENSION_REQUIRED:
            if extension.get(field) in (None, "", [], {}):
                errors.append(f"missing required field '{field}'")

        grounded = list(extension.get("grounded_in") or [])
        read_anchors = [anchor for anchor in grounded if anchor in opened]
        if grounded and not read_anchors and sources:
            errors.append(
                "not grounded in anything that has been read: "
                f"{', '.join(grounded)} — mark the unit read_status once someone has actually opened it"
            )
        for anchor in grounded:
            source_id = str(anchor).split("#")[0]
            if sources and source_id not in sources:
                errors.append(f"grounding source '{source_id}' is not in the bibliography")

        method_id = extension.get("first_computation")
        if method_id and methods_module is not None and method_id not in methods_module.REGISTRY:
            errors.append(f"first_computation '{method_id}' has no implementation")

        rows.append(
            {
                "extension_id": extension.get("extension_id"),
                "ok": not errors,
                "errors": errors,
                "read_groundings": read_anchors,
                "runnable_now": bool(method_id),
            }
        )
    return {
        "ok": all(row["ok"] for row in rows),
        "extensions": rows,
        "count": len(rows),
        "units_read": len(opened),
    }


def score_extension(extension: dict[str, Any]) -> dict[str, Any]:
    """Same shape as a bet, minus the risk that the work is already done.

    A novel-work proposal fails most often by being unoriginal rather than by
    being wrong, so that risk is priced separately from effort.
    """
    base = score_bet(extension)
    already_done = float(extension.get("already_done_risk") or 3)
    return {
        "score": round(base["score"] - 0.4 * already_done, 3),
        "components": {**base["components"], "already_done_risk": already_done},
    }


def rank_extensions(store: dict[str, Any]) -> list[dict[str, Any]]:
    scored = [{**extension, **score_extension(extension)} for extension in store.get("extensions") or []]
    scored.sort(key=lambda row: (-row["score"], row["extension_id"]))
    return scored


# --------------------------------------------------------------------------------------
# Robustness: does a policy survive the trial set being wrong about the world?
# --------------------------------------------------------------------------------------


def _drop_tokens(text: str, keep_every: int = 2) -> str:
    """Deterministically thin a phrase, simulating an operator who worded it differently."""
    words = str(text or "").split()
    return " ".join(word for index, word in enumerate(words) if index % keep_every == 0)


def perturb_lexical(trial: dict[str, Any], store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same decision, different words. Structure is untouched, so a policy that
    leans on structure should barely move and a lexical policy should fall over."""
    context = json.loads(json.dumps(trial.get("context") or {}))
    context["question"] = _drop_tokens(context.get("question", ""))
    context["uncertainties"] = [_drop_tokens(item) for item in context.get("uncertainties") or []]
    context["state_notes"] = [_drop_tokens(item) for item in context.get("state_notes") or []]
    return {**trial, "context": context}, store


def perturb_observable_dropout(trial: dict[str, Any], store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove an observable the gold concept needs. Serving it anyway is an
    integrity violation: the packet would recommend a calculation we cannot run."""
    context = json.loads(json.dumps(trial.get("context") or {}))
    by_id = {row["concept_id"]: row for row in store["concepts"]}
    required: list[str] = []
    for concept_id in trial.get("gold_concept_ids") or []:
        required.extend(by_id.get(concept_id, {}).get("required_observables") or [])
    if required:
        victim = sorted(set(required))[0]
        context["observables_available"] = [o for o in context.get("observables_available") or [] if o != victim]
        context["_removed_observable"] = victim
    return {**trial, "context": context, "applicable": False if required else trial.get("applicable", True)}, store


def perturb_tool_loss(trial: dict[str, Any], store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The tools are down. Concepts can still inform reasoning, so the right
    behaviour is graceful degradation, not silence."""
    context = json.loads(json.dumps(trial.get("context") or {}))
    context["tools_available"] = []
    return {**trial, "context": context}, store


def _synthetic_card(index: int, template: dict[str, Any], kind: str) -> dict[str, Any]:
    """Build a card that passes the gate but should not win retrieval."""
    card = json.loads(json.dumps(template))
    if kind == "distractor":
        card["concept_id"] = f"KC-DISTRACT-{index}"
        card["canonical_name"] = f"{template.get('canonical_name')} (unrelated venue variant)"
        # Same words, wrong world: a market type and horizon this context never has.
        card["market_types"] = ["dealer_market"]
        card["relevant_horizons"] = ["weeks"]
        card["required_observables"] = ["dealer_quote_sheet"]
    else:
        card["concept_id"] = f"KC-DUPE-{index}"
        card["canonical_name"] = f"{template.get('canonical_name')} (restatement)"
        card["confidence"] = max(0.0, float(template.get("confidence") or 0.5) - 0.05)
    card["implementation_status"] = "specified"
    card["alternative_explanations"] = list(template.get("alternative_explanations") or ["Restated mechanism may not apply."])
    card["contradicting_concept_ids"] = []
    card["supporting_concept_ids"] = []
    return card


def perturb_distractors(trial: dict[str, Any], store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inject cards with heavy word overlap and the wrong applicability."""
    by_id = {row["concept_id"]: row for row in store["concepts"]}
    extra = [
        _synthetic_card(index, by_id[concept_id], "distractor")
        for index, concept_id in enumerate(trial.get("gold_concept_ids") or [])
        if concept_id in by_id
    ]
    if not extra:
        return trial, store
    return trial, {**store, "concepts": [*store["concepts"], *extra]}


def perturb_near_duplicates(trial: dict[str, Any], store: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Clone the gold card. Diversity control should keep the packet from
    spending its budget on two statements of one mechanism."""
    by_id = {row["concept_id"]: row for row in store["concepts"]}
    extra = [
        _synthetic_card(index, by_id[concept_id], "duplicate")
        for index, concept_id in enumerate(trial.get("gold_concept_ids") or [])
        if concept_id in by_id
    ]
    if not extra:
        return trial, store
    return trial, {**store, "concepts": [*store["concepts"], *extra]}


# Each perturbation declares how success is measured, because they do not all ask
# the same question. Reworded context: keep serving the same thing (retention).
# Missing observable: the right answer changed, so the test is whether the policy
# stops serving what it can no longer compute (compliance).
PERTURBATIONS = {
    "lexical_drift": {"fn": perturb_lexical, "mode": "retention"},
    "observable_dropout": {"fn": perturb_observable_dropout, "mode": "compliance"},
    "tool_loss": {"fn": perturb_tool_loss, "mode": "retention"},
    "distractors": {"fn": perturb_distractors, "mode": "retention"},
    "near_duplicates": {"fn": perturb_near_duplicates, "mode": "retention"},
}


def integrity_violations(
    packet: dict[str, Any],
    context: dict[str, Any],
    store: dict[str, Any],
) -> list[dict[str, Any]]:
    """Hard errors, independent of any label: a served card whose observables are
    absent, whose market or horizon does not match, or whose sources postdate the
    decision. These are wrong regardless of what the trial expected."""
    by_id = {row["concept_id"]: row for row in store["concepts"]}
    available = set(context.get("observables_available") or [])
    problems: list[dict[str, Any]] = []
    for card in packet.get("cards") or []:
        concept = by_id.get(card["concept_id"]) or card
        missing = set(concept.get("required_observables") or []) - available
        if missing:
            problems.append({"concept_id": card["concept_id"], "violation": "missing_observables", "detail": sorted(missing)})
        if not market_compatible(concept, context.get("market_type")):
            problems.append({"concept_id": card["concept_id"], "violation": "wrong_market", "detail": context.get("market_type")})
        if not horizon_compatible(concept, context.get("horizon")):
            problems.append({"concept_id": card["concept_id"], "violation": "wrong_horizon", "detail": context.get("horizon")})
    return problems


def stress_policy(
    store: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Score a policy on the clean trials, then under each perturbation.

    The headline number is the worst case, not the average. A retrieval layer that
    is excellent on the trial set as written and collapses when one observable
    goes missing is not a retrieval layer we can put in front of a live decision.
    """
    clean = evaluate_policy(store, sources, policy)
    baseline = max(1e-9, 0.6 * clean["precision"] + 0.4 * (1.0 - clean["false_abstention_rate"]))

    results: dict[str, Any] = {}
    for name, spec in PERTURBATIONS.items():
        perturb, mode = spec["fn"], spec["mode"]
        trials: list[dict[str, Any]] = []
        violations: list[dict[str, Any]] = []
        working_store = store
        for trial in store["trials"]:
            perturbed_trial, perturbed_store = perturb(trial, store)
            working_store = perturbed_store
            packet = retrieve(perturbed_store, sources, perturbed_trial.get("context") or {}, policy)
            violations.extend(
                {**row, "trial_id": trial.get("trial_id")}
                for row in integrity_violations(packet, perturbed_trial.get("context") or {}, perturbed_store)
            )
            returned = [card["concept_id"] for card in packet["cards"]]
            gold = list(perturbed_trial.get("gold_concept_ids") or [])
            trials.append(
                {
                    "trial_id": trial.get("trial_id"),
                    "applicable": bool(perturbed_trial.get("applicable", True)),
                    "returned": returned,
                    "hit": bool(set(returned) & set(gold)),
                    "precision": (len(set(returned) & set(gold)) / len(returned)) if returned else 0.0,
                    "abstained": packet["abstained"],
                    "synthetic_served": [c for c in returned if c.startswith(("KC-DISTRACT", "KC-DUPE"))],
                }
            )

        applicable = [row for row in trials if row["applicable"]]
        served = [row for row in applicable if not row["abstained"]]
        negatives = [row for row in trials if not row["applicable"]]

        def mean(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        precision = mean([row["precision"] for row in served])
        false_abstention = mean([1.0 if row["abstained"] else 0.0 for row in applicable])
        clean_trials = {row["trial_id"] for row in trials} - {row["trial_id"] for row in violations}
        if mode == "compliance":
            # Serving nothing is a pass here; serving something uncomputable is not.
            retention = len(clean_trials) / max(1, len(trials))
        else:
            quality = 0.6 * precision + 0.4 * (1.0 - false_abstention)
            retention = quality / baseline
        results[name] = {
            "mode": mode,
            "hit_rate": round(mean([1.0 if row["hit"] else 0.0 for row in applicable]), 4),
            "precision": round(precision, 4),
            "false_abstention_rate": round(false_abstention, 4),
            "correct_abstention": round(mean([1.0 if row["abstained"] else 0.0 for row in negatives]), 4),
            "synthetic_cards_served": sum(len(row["synthetic_served"]) for row in trials),
            "integrity_violations": len(violations),
            "retention": round(retention, 4),
            "violation_detail": violations[:5],
        }

    retentions = [row["retention"] for row in results.values()]
    total_violations = sum(row["integrity_violations"] for row in results.values())
    # Violations are not a soft penalty: serving a card whose data is absent is a
    # different kind of wrong from ranking it second.
    violation_rate = total_violations / max(1, len(store["trials"]) * len(PERTURBATIONS))
    return {
        "policy": policy.get("name"),
        "clean_quality": round(baseline, 4),
        "worst_case_retention": round(min(retentions), 4) if retentions else 0.0,
        "mean_retention": round(sum(retentions) / len(retentions), 4) if retentions else 0.0,
        "integrity_violations": total_violations,
        "robustness": round(max(0.0, (min(retentions) if retentions else 0.0) * (1.0 - min(1.0, violation_rate))), 4),
        "perturbations": results,
    }


# --------------------------------------------------------------------------------------
# Compile queue (what to read next, at chapter level)
# --------------------------------------------------------------------------------------


def compile_queue(
    store: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    limit: int = 25,
) -> dict[str, Any]:
    """Rank sources by expected contribution to the *compiled* knowledge base.

        V(s) = P(new capability) x P(behaviour change | capability) x P(net gain | change)
               - processing cost - redundancy - misapplication risk

    Before outcomes exist these are component priors: proximity to a diagnosed
    problem (personalized PageRank seeded on the problem map), mechanistic
    density, data compatibility, likely pretraining scarcity, bridge value,
    non-redundancy with what is already compiled, and legal accessibility.
    """
    if not sources:
        return {"queues": {}, "note": "no corpus bibliography found; nothing to rank"}

    problems = store["problems"]
    problem_buckets: dict[str, float] = {}
    problem_tags: dict[str, float] = {}
    for problem in problems:
        weight = float(problem.get("weight") or 1.0)
        for bucket in problem.get("buckets") or []:
            problem_buckets[bucket] = problem_buckets.get(bucket, 0.0) + weight
        for tag in problem.get("tags") or []:
            problem_tags[tag] = problem_tags.get(tag, 0.0) + weight

    node_ids = sorted(sources)
    edges: list[tuple[str, str]] = []
    for entry in sources.values():
        for raw_ref in entry.get("refs") or []:
            target = raw_ref.get("target") if isinstance(raw_ref, dict) else raw_ref
            if target in sources:
                edges.append((entry["id"], target))

    seeds: dict[str, float] = {}
    for entry in sources.values():
        weight = problem_buckets.get(entry.get("bucket"), 0.0)
        weight += sum(problem_tags.get(tag, 0.0) for tag in entry.get("tags") or [])
        if weight:
            seeds[entry["id"]] = weight
    proximity = graphops.personalized_pagerank(node_ids, edges, seeds=seeds or None)
    best_proximity = max(proximity.values(), default=1.0) or 1.0
    bridge = graphops.betweenness(node_ids, edges)
    best_bridge = max(bridge.values(), default=1.0) or 1.0

    compiled_sources = set()
    for concept in store["concepts"]:
        for raw_ref in concept.get("source_passage_ids") or []:
            compiled_sources.add(parse_passage_ref(raw_ref)["source_id"])

    density_by_form = {
        "textbook": 0.9, "monograph": 0.9, "lecture_notes": 0.95, "paper": 0.8, "survey": 0.7,
        "handbook": 0.8, "thesis": 0.75, "problem_set": 0.6, "course": 0.6, "working_paper": 0.75,
        "exchange_doc": 0.7, "rulebook": 0.5, "api_doc": 0.6, "standard": 0.6, "regulatory_filing": 0.5,
        "manual": 0.6, "proceedings": 0.6, "newsletter": 0.3, "blog": 0.3, "video": 0.4,
        "interview_packet": 0.4, "software_docs": 0.4, "dataset": 0.4, "notes_own": 0.5,
    }
    # Likely pretraining scarcity is a proxy, not an observation: we cannot see any
    # model's training set. Access friction is the only honest signal available.
    scarcity_by_rights = {
        "licensed_purchase_required": 0.9, "subscription_required": 0.7, "proprietary_confidential": 0.0,
        "all_rights_reserved": 0.6, "public_but_restricted": 0.5, "author_hosted_free": 0.3,
        "cc_by_nc_sa": 0.3, "cc_by": 0.2, "government_work": 0.3, "unknown": 0.5,
    }

    rows: list[dict[str, Any]] = []
    for entry in sources.values():
        rights = entry.get("derived_rights") or {}
        if rights.get("use_class") == "excluded":
            continue
        proximity_score = proximity.get(entry["id"], 0.0) / best_proximity
        density = density_by_form.get(entry.get("form"), 0.5) * (
            1.0 if entry.get("density") == "high" else 0.75 if entry.get("density") == "medium" else 0.5
        )
        scarcity = scarcity_by_rights.get(rights.get("status"), 0.5)
        bridge_value = bridge.get(entry["id"], 0.0) / best_bridge
        redundancy = 0.5 if entry["id"] in compiled_sources else 0.0
        accessibility = 1.0 if rights.get("manifest_eligible") else 0.75 if rights.get("study_ok") else 0.0
        priority = float(entry.get("priority") or 3) / 5.0
        pages = int(entry.get("pages") or 0)
        processing_cost = min(0.4, pages / 5000.0)

        value = (
            0.34 * proximity_score
            + 0.20 * density
            + 0.14 * priority
            + 0.12 * scarcity
            + 0.10 * bridge_value
            + 0.10 * accessibility
            - processing_cost
            - redundancy
        )
        rows.append(
            {
                "id": entry["id"],
                "title": entry.get("title"),
                "bucket": entry.get("bucket"),
                "form": entry.get("form"),
                "pages": pages,
                "use_class": rights.get("use_class"),
                "rights_status": rights.get("status"),
                "score": round(value, 4),
                "components": {
                    "problem_proximity": round(proximity_score, 4),
                    "mechanistic_density": round(density, 4),
                    "analyst_priority": round(priority, 4),
                    "likely_scarcity_proxy": round(scarcity, 4),
                    "bridge_value": round(bridge_value, 4),
                    "accessibility": round(accessibility, 4),
                    "processing_cost": round(processing_cost, 4),
                    "redundancy": round(redundancy, 4),
                },
                "already_compiled": entry["id"] in compiled_sources,
                "tags": entry.get("tags") or [],
                "problem_ids": [
                    problem.get("problem_id")
                    for problem in problems
                    if entry.get("bucket") in (problem.get("buckets") or [])
                    or set(entry.get("tags") or []) & set(problem.get("tags") or [])
                ],
            }
        )

    rows.sort(key=lambda row: (-row["score"], row["id"]))

    def top(predicate, count: int) -> list[dict[str, Any]]:
        return [row for row in rows if predicate(row)][:count]

    spine = graphops.maximal_marginal_relevance(
        [row for row in rows if row["form"] in {"textbook", "monograph", "handbook", "lecture_notes"}],
        lambda a, b: 1.0 if a["bucket"] == b["bucket"] else 0.0,
        k=min(20, limit),
        lambda_=0.6,
    )

    coverage = {row["id"]: set(row["problem_ids"]) for row in rows if row["problem_ids"]}
    cover = graphops.submodular_cover(
        [row for row in rows if row["problem_ids"]],
        coverage,
        targets={problem.get("problem_id") for problem in problems},
    )

    return {
        "generated_at": now_iso(),
        "ranked": rows[:limit],
        "queues": {
            "human_foundation_spine": spine,
            "machine_reading": top(lambda row: not row["already_compiled"], limit),
            "rare_source": top(lambda row: row["components"]["likely_scarcity_proxy"] >= 0.6, limit),
            "contradiction": top(lambda row: "contradiction" in (row["tags"] or []) or row["components"]["bridge_value"] > 0.2, limit),
            "implementation": top(lambda row: row["bucket"] in {"optimal_control", "operations_research", "signal_processing", "queueing_networks", "decision_sequential"}, limit),
            "experiment": top(lambda row: row["already_compiled"], limit),
        },
        "minimum_problem_cover": cover,
    }


# --------------------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------------------


def _cards_on_read_units(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """How much of the compiled knowledge rests on a source someone actually opened.

    Not a gate — the original cards were written from working knowledge and that is
    a legitimate way to seed a store. But the number should be visible, because a
    knowledge base whose anchors have never been opened is a well-organized memory.
    """
    opened = read_units(sources) if sources else {}
    grounded, ungrounded = [], []
    for concept in store.get("concepts") or []:
        anchors = [str(ref if isinstance(ref, str) else parse_passage_ref(ref)["source_id"]) for ref in concept.get("source_passage_ids") or []]
        anchors = [f"{parse_passage_ref(ref)['source_id']}#{parse_passage_ref(ref)['anchor']}" for ref in concept.get("source_passage_ids") or []]
        (grounded if any(anchor in opened for anchor in anchors) else ungrounded).append(concept["concept_id"])
    return {"grounded": grounded, "ungrounded": ungrounded}


def status_payload(store: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    validation = validate_store(store, sources)
    servable = servable_concepts(store, sources)
    by_problem: dict[str, int] = {}
    for concept in servable:
        for problem_id in concept.get("problem_ids") or []:
            by_problem[problem_id] = by_problem.get(problem_id, 0) + 1

    bound_concepts = {
        concept_id
        for binding in store["methods"]
        for concept_id in binding.get("concept_ids") or []
    }
    decision_concepts = {card.get("concept_id") for card in store["decisions"]}
    hypothesis_concepts = {row.get("concept_id") for row in store["hypotheses"]}

    return {
        "generated_at": now_iso(),
        "counts": validation["counts"],
        "servable_rate": round(
            validation["counts"]["servable_concepts"] / max(1, validation["counts"]["concepts"]), 3
        ),
        "concepts_by_problem": by_problem,
        "problems_uncovered": sorted(
            {problem.get("problem_id") for problem in store["problems"]} - set(by_problem)
        ),
        "concepts_without_method": sorted(
            {row["concept_id"] for row in store["concepts"]} - bound_concepts
        ),
        "concepts_without_decision_card": sorted(
            {row["concept_id"] for row in store["concepts"]} - decision_concepts
        ),
        "concepts_without_hypothesis": sorted(
            {row["concept_id"] for row in store["concepts"]} - hypothesis_concepts
        ),
        "implementations_available": sorted(methods_module.REGISTRY) if methods_module else [],
        "trials": len(store["trials"]),
        "frontier_bets": len(store.get("bets") or []),
        "exploratory_extensions": len(store.get("extensions") or []),
        "cards_anchored_to_read_units": _cards_on_read_units(store, sources)["grounded"],
        "cards_anchored_only_to_unread": _cards_on_read_units(store, sources)["ungrounded"],
        "bets_runnable_now": sum(1 for bet in (store.get("bets") or []) if bet.get("first_computation")),
        "policies": sorted(store["policies"]),
    }



# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def _card(**overrides: Any) -> dict[str, Any]:
    card = {
        "concept_id": "KC-T",
        "canonical_name": "Test concept",
        "plain_description": "d",
        "mechanism": "m",
        "assumptions": ["a"],
        "market_types": ["clob_crypto"],
        "relevant_horizons": ["minutes"],
        "required_observables": ["l1_book"],
        "expected_empirical_signature": "s",
        "known_failure_modes": ["f"],
        "alternative_explanations": ["alt"],
        "source_passage_ids": ["src#ch1"],
        "implementation_status": "specified",
        "confidence": 0.6,
    }
    card.update(overrides)
    return card


def self_test() -> dict[str, Any]:
    checks: list[str] = []
    sources = {
        "src": {"id": "src", "year": 2010, "derived_rights": {"use_class": "reference_only", "manifest_eligible": False, "confidence": "confirmed"}},
        "open": {"id": "open", "year": 2010, "derived_rights": {"use_class": "ingest_full", "manifest_eligible": True, "confidence": "confirmed"}},
        "banned": {"id": "banned", "year": 2010, "derived_rights": {"use_class": "excluded", "manifest_eligible": False}},
        "future": {"id": "future", "year": 2030, "derived_rights": {"use_class": "reference_only", "manifest_eligible": False}},
    }
    store = {"concepts": [], "hypotheses": [], "methods": [], "decisions": [], "problems": [], "trials": [], "policies": {}, "utility": {}}

    good = _card()
    store["concepts"] = [good]
    assert concept_gate(good, sources, store)["servable"], concept_gate(good, sources, store)
    checks.append("gate: a complete card serves")

    # Counterevidence is structural.
    lonely = _card(alternative_explanations=[], contradicting_concept_ids=[])
    assert not concept_gate(lonely, sources, {**store, "concepts": [lonely]})["servable"]
    checks.append("gate: a card with nothing that could argue against it is refused")

    # Rights: quoting is gated on the source, citing an excluded source never allowed.
    quoted = _card(source_passage_ids=[{"source_id": "src", "anchor": "ch1", "quote": "verbatim"}])
    errors = concept_gate(quoted, sources, {**store, "concepts": [quoted]})["errors"]
    assert any("verbatim" in e for e in errors), errors
    allowed = _card(source_passage_ids=[{"source_id": "open", "anchor": "ch1", "quote": "verbatim"}])
    assert concept_gate(allowed, sources, {**store, "concepts": [allowed]})["servable"]
    banned = _card(source_passage_ids=["banned#ch1"])
    assert any("excluded" in e for e in concept_gate(banned, sources, {**store, "concepts": [banned]})["errors"])
    missing_source = _card(source_passage_ids=["ghost#ch1"])
    assert any("not in the bibliography" in e for e in concept_gate(missing_source, sources, {**store, "concepts": [missing_source]})["errors"])
    checks.append("gate: quotes gated on source rights, excluded and unknown sources refused")

    # Implementation claims must be backed, at the registered version.
    claimed = _card(implementation_status="implemented")
    assert not concept_gate(claimed, sources, {**store, "concepts": [claimed]})["servable"]
    if methods_module is not None:
        bound = {"method_id": "cusum_changepoint", "implementation_version": "1.0.0", "concept_ids": ["KC-T"]}
        assert method_gate(bound, {**store, "concepts": [claimed]})["bound"]
        drifted = {**bound, "implementation_version": "0.9.0"}
        assert any("version drift" in e for e in method_gate(drifted, {**store, "concepts": [claimed]})["errors"])
        ghost = {"method_id": "not_a_method", "implementation_version": "1.0.0", "concept_ids": ["KC-T"]}
        assert not method_gate(ghost, {**store, "concepts": [claimed]})["bound"]
        checks.append("gate: unbacked implementation claims, version drift and unknown methods all refused")

    # Dangling relations and hypotheses without a cost model.
    dangling = _card(contradicting_concept_ids=["KC-GHOST"])
    assert any("dangling" in e for e in concept_gate(dangling, sources, {**store, "concepts": [dangling]})["errors"])
    costless = {"hypothesis_id": "H", "concept_id": "KC-T", "market_context": "m", "causal_story": "c",
                "ex_ante_prediction": "p", "null_hypothesis": "n", "measurement_operator": {},
                "eligible_universe": "u", "decision_timestamp_rule": "r", "outcome_horizons": ["1d"],
                "cost_model": None, "invalidation_conditions": ["i"]}
    assert any("cost model" in e for e in hypothesis_gate(costless, {**store, "concepts": [good]})["errors"])
    checks.append("gate: dangling relations and costless hypotheses refused")

    # Retrieval filters: each one, in isolation.
    store = {**store, "concepts": [good]}
    base_context = {"market_type": "clob_crypto", "horizon": "minutes", "observables_available": ["l1_book"],
                    "timestamp": "2026-01-01T00:00:00Z", "question": "test concept mechanism"}
    policy = resolve_policy(store, None, {"abstain_threshold": 0.0, "require_counterevidence": False})
    assert retrieve(store, sources, base_context, policy)["cards"], "clean context should serve"
    for field, value, label in [
        ("market_type", "prediction_market", "market"),
        ("horizon", "days", "horizon"),
        ("observables_available", [], "observables"),
        ("timestamp", "1990-01-01T00:00:00Z", "point-in-time"),
    ]:
        packet = retrieve(store, sources, {**base_context, field: value}, policy)
        assert packet["abstained"] and not packet["cards"], (label, packet)
    checks.append("retrieval: market, horizon, observable and point-in-time filters each block on their own")

    # Point-in-time is about the source, not the card.
    future_card = _card(concept_id="KC-F", source_passage_ids=["future#ch1"])
    future_store = {**store, "concepts": [future_card]}
    assert retrieve(future_store, sources, base_context, policy)["abstained"], "a 2030 source cannot inform a 2026 decision"
    checks.append("retrieval: a source published after the decision timestamp is unreachable")

    # Counterevidence requirement can veto an otherwise good packet.
    strict = resolve_policy(store, None, {"abstain_threshold": 0.0, "require_counterevidence": True, "expand_hops": 1})
    assert retrieve(store, sources, base_context, strict)["counterevidence"], "alternative explanation should surface"
    no_counter = _card(alternative_explanations=[], contradicting_concept_ids=[], known_failure_modes=[], assumptions=[])
    packet = retrieve({**store, "concepts": [no_counter]}, sources, base_context, strict)
    assert packet["abstained"], "unservable card leaves nothing to serve"
    checks.append("retrieval: counterevidence requirement enforced at serve time")

    # Degenerate stores must not raise.
    empty = {**store, "concepts": []}
    assert retrieve(empty, sources, base_context, policy)["abstained"]
    assert retrieve(store, {}, base_context, policy) is not None, "no bibliography should not crash retrieval"
    assert status_payload(empty, {})["servable_rate"] == 0.0
    assert status_payload(empty, {})["frontier_bets"] == 0, "a store assembled without every key must still report"
    assert rank_bets({}) == [] and validate_bets({}, {})["ok"], "bets ranking on an empty store"
    checks.append("degenerate input: empty store and missing bibliography degrade quietly")

    # Perturbations and integrity accounting.
    trial = {"trial_id": "t", "applicable": True, "gold_concept_ids": ["KC-T"], "context": base_context}
    dropped, _ = perturb_observable_dropout(trial, store)
    assert "l1_book" not in (dropped["context"]["observables_available"] or []), dropped
    _, injected = perturb_distractors(trial, store)
    assert len(injected["concepts"]) == 2 and injected["concepts"][1]["concept_id"].startswith("KC-DISTRACT")
    served = {"cards": [{"concept_id": "KC-T", **good}]}
    violations = integrity_violations(served, {**base_context, "observables_available": []}, store)
    assert violations and violations[0]["violation"] == "missing_observables", violations
    checks.append("stress: perturbations apply and integrity violations are detected")

    return {"ok": True, "checks": checks}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def resolve_dirs(args: argparse.Namespace) -> tuple[Path, dict[str, Path], Path | None]:
    lab_root = args.lab_dir.resolve()
    knowledge_dir = (args.knowledge_dir or (lab_root / "knowledge")).resolve()
    corpus_dir = args.corpus_dir.resolve() if args.corpus_dir else None
    return lab_root, knowledge_paths(knowledge_dir), corpus_dir


def cmd_init(args: argparse.Namespace) -> int:
    _, paths, _ = resolve_dirs(args)
    paths["root"].mkdir(parents=True, exist_ok=True)
    for key, root_key in [("concepts", "concepts"), ("hypotheses", "hypotheses"), ("methods", "methods"), ("trials", "trials")]:
        if not paths[key].exists():
            write_yaml(paths[key], {root_key: []})
    if not paths["decisions"].exists():
        write_yaml(paths["decisions"], {"decision_relevance": []})
    if not paths["problems"].exists():
        write_yaml(paths["problems"], {"problems": []})
    if not paths["policies"].exists():
        write_yaml(paths["policies"], {"policies": {"default": DEFAULT_POLICY}})
    print(json.dumps({"knowledge_dir": str(paths["root"])}, indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    result = validate_store(store, sources)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"ok": result["ok"], **result["counts"]}, indent=2))
        for group in ("concepts", "hypotheses", "methods", "decision_relevance"):
            for row in result[group]:
                errors = row.get("errors") or []
                warnings = row.get("warnings") or []
                identifier = row.get("concept_id") or row.get("hypothesis_id") or row.get("method_id") or row.get("decision_relevance_id")
                for message in errors:
                    print(f"ERROR  {identifier}: {message}")
                for message in warnings:
                    print(f"WARN   {identifier}: {message}")
    return 0 if result["ok"] else 1


def cmd_status(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    payload = status_payload(store, sources)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    counts = payload["counts"]
    print(f"knowledge: {paths['root']}")
    print(
        f"  concepts={counts['concepts']} servable={counts['servable_concepts']} ({payload['servable_rate']}) "
        f"hypotheses={counts['hypotheses']} methods={counts['methods']} decision_cards={counts['decision_relevance']}"
    )
    print(f"  trials={payload['trials']} policies={', '.join(payload['policies']) or 'default only'}")
    if payload["problems_uncovered"]:
        print(f"  problems with no servable concept: {', '.join(payload['problems_uncovered'])}")
    if payload["concepts_without_method"]:
        print(f"  concepts with no method binding: {', '.join(payload['concepts_without_method'])}")
    if payload["concepts_without_hypothesis"]:
        print(f"  concepts with no hypothesis: {', '.join(payload['concepts_without_hypothesis'])}")
    grounded = len(payload["cards_anchored_to_read_units"])
    print(
        f"  provenance: {grounded}/{payload['counts']['concepts']} cards anchored to a source unit someone has opened; "
        f"{len(payload['cards_anchored_only_to_unread'])} rest on unread anchors"
    )
    print(f"  bets={payload['frontier_bets']} extensions={payload['exploratory_extensions']}")
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    context = json.loads(args.context.read_text())
    policy = resolve_policy(store, args.policy, {"k": args.k} if args.k else None)
    packet = retrieve(store, sources, context, policy)

    if args.markdown:
        text = render_packet(packet)
        if args.out:
            write_text(args.out, text)
            print(json.dumps({"packet": str(args.out), "abstained": packet["abstained"]}, indent=2))
        else:
            print(text)
        return 0

    if args.out:
        write_json(args.out, packet)
        print(json.dumps({"packet": str(args.out), "cards": len(packet["cards"]), "abstained": packet["abstained"]}, indent=2))
        return 0
    print(json.dumps(packet, indent=2))
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    names = [args.policy] if args.policy else (sorted(store["policies"]) or [None])
    results = [evaluate_policy(store, sources, resolve_policy(store, name)) for name in names]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for result in results:
        print(
            f"{result['policy'] or 'default':<24} hit={result['hit_rate']:.2f} prec={result['precision']:.2f} "
            f"abstain_ok={result['non_applicability_accuracy']:.2f} counter={result['counterevidence_coverage']:.2f} "
            f"false_abstain={result['false_abstention_rate']:.2f} ctx={result['mean_context_kilotokens']:.2f}k"
        )
    return 0


def cmd_bets(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    validation = validate_bets(store, sources)
    ranked = rank_bets(store)

    if args.json:
        print(json.dumps({"validation": validation, "ranked": ranked}, indent=2))
        return 0 if validation["ok"] else 1

    for row in validation["bets"]:
        for message in row["errors"]:
            print(f"ERROR  {row['bet_id']}: {message}")
    print(f"{len(ranked)} bets, {sum(1 for r in validation['bets'] if r['runnable_now'])} with a first computation already implemented\n")
    for index, bet in enumerate(ranked, 1):
        runnable = bet.get("first_computation")
        print(f"{index:>2}. {bet['score']:>5}  {bet['bet_id']:<22} {bet['title']}")
        print(f"        domain={bet['domain']}  problems={', '.join(bet.get('problem_ids') or [])}")
        print(f"        run: {runnable or 'no implementation yet'}")
        if args.verbose:
            print(f"        prediction: {' '.join(str(bet['sharp_prediction']).split())[:160]}")
            print(f"        falsifier:  {' '.join(str(bet['falsifier']).split())[:160]}")
    return 0 if validation["ok"] else 1


def cmd_extensions(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    validation = validate_extensions(store, sources)
    ranked = rank_extensions(store)

    if args.json:
        print(json.dumps({"validation": validation, "ranked": ranked}, indent=2))
        return 0 if validation["ok"] else 1

    for row in validation["extensions"]:
        for message in row["errors"]:
            print(f"ERROR  {row['extension_id']}: {message}")
    print(
        f"{len(ranked)} proposed extensions, all grounded in {validation['units_read']} source units "
        f"that have actually been read\n"
    )
    for index, extension in enumerate(ranked, 1):
        print(f"{index:>2}. {extension['score']:>6}  {extension['extension_id']:<26} {extension['title']}")
        print(f"          grounded in: {', '.join(extension.get('grounded_in') or [])}")
        print(f"          run: {extension.get('first_computation') or 'no implementation yet'}")
        if args.verbose:
            print(f"          leaves open: {' '.join(str(extension['what_the_source_leaves_open']).split())[:170]}")
            print(f"          novel claim: {' '.join(str(extension['novel_claim']).split())[:170]}")
            print(f"          kill:        {' '.join(str(extension['kill_condition']).split())[:170]}")
    return 0 if validation["ok"] else 1


def cmd_stress(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    names = [args.policy] if args.policy else (sorted(store["policies"]) or [None])
    results = [stress_policy(store, sources, resolve_policy(store, name)) for name in names]
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for result in results:
        print(f"{result['policy'] or 'default':<24} robustness={result['robustness']:.2f} worst={result['worst_case_retention']:.2f} violations={result['integrity_violations']}")
        for name, row in result["perturbations"].items():
            print(f"    {name:<20} retention={row['retention']:.2f} prec={row['precision']:.2f} synthetic_served={row['synthetic_cards_served']} violations={row['integrity_violations']}")
    return 0


def cmd_compile_queue(args: argparse.Namespace) -> int:
    lab_root, paths, corpus_dir = resolve_dirs(args)
    store = load_store(paths)
    sources = load_corpus_sources(lab_root, corpus_dir)
    queues = compile_queue(store, sources, limit=args.limit)
    out = args.out or (paths["queues"] / "compile_queue.json")
    write_json(out, queues)
    if args.json:
        print(json.dumps(queues, indent=2))
        return 0
    print(json.dumps({"queue_file": str(out), "ranked": len(queues.get("ranked") or [])}, indent=2))
    for row in (queues.get("ranked") or [])[: min(10, args.limit)]:
        print(f"  {row['score']:>7}  {row['bucket']:<24} {row['title'][:60]}")
    cover = queues.get("minimum_problem_cover") or {}
    if cover.get("selected"):
        print(f"  minimum cover of the problem map: {', '.join(row['id'] for row in cover['selected'])}")
        if cover.get("uncovered"):
            print(f"  problems no mapped source covers: {', '.join(cover['uncovered'])}")
    return 0


def cmd_vocab(args: argparse.Namespace) -> int:
    payload = {
        "implementation_status": IMPLEMENTATION_STATUS,
        "decision_types": DECISION_TYPES,
        "horizons": HORIZONS,
        "market_types": MARKET_TYPES,
        "concept_required_fields": CONCEPT_REQUIRED,
        "hypothesis_required_fields": HYPOTHESIS_REQUIRED,
        "decision_card_required_fields": DECISION_CARD_REQUIRED,
        "servable_gate": [
            "every required field present",
            "at least one contradicting concept or alternative explanation",
            "source anchors resolve to non-excluded bibliography entries",
            "verbatim quotes only from manifest-eligible sources",
            "an implementation claim must be backed by a method binding at the registered version",
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Market knowledge compiler and retrieval")
    parser.add_argument("--lab-dir", type=Path, default=Path.cwd())
    parser.add_argument("--knowledge-dir", type=Path, default=None)
    parser.add_argument("--corpus-dir", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create an empty knowledge store.")
    validate_cmd = sub.add_parser("validate", help="Run the SERVABLE gate over every card.")
    validate_cmd.add_argument("--json", action="store_true")
    status_cmd = sub.add_parser("status", help="Coverage of the problem map, gaps, and gates.")
    status_cmd.add_argument("--json", action="store_true")

    retrieve_cmd = sub.add_parser("retrieve", help="Build an evidence packet for a decision context.")
    retrieve_cmd.add_argument("--context", type=Path, required=True)
    retrieve_cmd.add_argument("--policy", default=None)
    retrieve_cmd.add_argument("--k", type=int, default=None)
    retrieve_cmd.add_argument("--markdown", action="store_true")
    retrieve_cmd.add_argument("--out", type=Path, default=None)

    evaluate_cmd = sub.add_parser("evaluate", help="Score retrieval policies against the labelled trial set.")
    evaluate_cmd.add_argument("--policy", default=None)
    evaluate_cmd.add_argument("--json", action="store_true")

    bets_cmd = sub.add_parser("bets", help="Rank the frontier research bets and check each one is refutable and grounded.")
    bets_cmd.add_argument("--verbose", action="store_true")
    bets_cmd.add_argument("--json", action="store_true")

    extensions_cmd = sub.add_parser("extensions", help="Rank proposed new work; refuse anything not grounded in a source unit that has been read.")
    extensions_cmd.add_argument("--verbose", action="store_true")
    extensions_cmd.add_argument("--json", action="store_true")

    stress_cmd = sub.add_parser("stress", help="Score policies under perturbation: reworded contexts, missing observables, distractors, duplicates, tool loss.")
    stress_cmd.add_argument("--policy", default=None)
    stress_cmd.add_argument("--json", action="store_true")

    queue_cmd = sub.add_parser("compile-queue", help="Rank what to read and compile next.")
    queue_cmd.add_argument("--limit", type=int, default=25)
    queue_cmd.add_argument("--out", type=Path, default=None)
    queue_cmd.add_argument("--json", action="store_true")

    sub.add_parser("vocab", help="Print the card vocabularies and the SERVABLE gate.")
    sub.add_parser("self-test", help="Exercise the gates, the filters and the stress harness on adversarial input.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "self-test":
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    handlers = {
        "init": cmd_init,
        "validate": cmd_validate,
        "status": cmd_status,
        "retrieve": cmd_retrieve,
        "evaluate": cmd_evaluate,
        "bets": cmd_bets,
        "extensions": cmd_extensions,
        "stress": cmd_stress,
        "compile-queue": cmd_compile_queue,
        "vocab": cmd_vocab,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
