#!/usr/bin/env python3
"""Bibliography network mapping, iterative expansion rounds, and rights tagging.

The corpus engine keeps a durable bibliography (`corpus/bibliography.yaml`), maps
it as a citation / co-syllabus network, and drives bounded scouting rounds until
each bucket stops producing new material. Every entry carries a form tag and a
rights tag; nothing reaches the build manifest unless its rights are *confirmed*
with evidence.

The engine is offline and deterministic. Scouts (Claude Code / Codex / a human)
do the searching; this script decides what to look for next and what may be used.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

from lab_core import append_jsonl, load_json, load_jsonl, load_yaml, now_iso, write_json, write_text, write_yaml


# --------------------------------------------------------------------------------------
# Controlled vocabularies
# --------------------------------------------------------------------------------------

# What the material physically is. Drives extraction cost and density expectations.
FORMS: dict[str, str] = {
    "textbook": "Graduate or professional textbook.",
    "monograph": "Single-topic research monograph.",
    "handbook": "Edited handbook or collected survey volume.",
    "lecture_notes": "Course notes, slides, or a lecture-note book.",
    "problem_set": "Problem sets, solutions, exercise banks.",
    "course": "Structured course (video, MOOC, paid program) with materials.",
    "paper": "Peer-reviewed or archival paper.",
    "working_paper": "Preprint or working paper (arXiv, SSRN, NBER, Fed series).",
    "survey": "Review / survey article.",
    "thesis": "PhD or masters thesis.",
    "proceedings": "Conference or workshop proceedings.",
    "rulebook": "Exchange rulebook or regulatory rule text.",
    "exchange_doc": "Exchange technical documentation (matching engine, market data specs).",
    "api_doc": "Venue or vendor API / protocol documentation.",
    "regulatory_filing": "Regulatory filing, concept release, or market structure report.",
    "manual": "Trading desk manual, training manual, internal handbook.",
    "interview_packet": "Prop-shop / market-maker interview or onboarding material.",
    "newsletter": "Trading newsletter or practitioner letter series.",
    "software_docs": "Library documentation used as a knowledge source.",
    "dataset": "Dataset with documentation worth ingesting.",
    "standard": "Technical standard (FIX, ITCH, SBE, ISO).",
    "blog": "Practitioner blog or essay series.",
    "video": "Recorded lecture or talk (transcribable).",
    "notes_own": "Our own notes, summaries, or derived explanations.",
}

# Rights status -> what we may do with it. `use_class` values:
#   ingest_*        the text itself may enter a corpus build (subject to the confirm gate)
#   reference_only  read it, learn from it, write our own explanations; never copy it in
#   needs_review    unresolved; blocked from the manifest until someone checks
#   excluded        must not be used at all
RIGHTS_STATUS: dict[str, dict[str, Any]] = {
    "public_domain": {
        "use_class": "ingest_full",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": False,
        "note": "Copyright expired or dedicated to the public domain.",
    },
    "cc0": {
        "use_class": "ingest_full",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": False,
        "note": "CC0 dedication.",
    },
    "government_work": {
        "use_class": "ingest_full",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": False,
        "note": "Work of a government that places it outside copyright. Jurisdiction-specific: verify, do not assume.",
    },
    "cc_by": {
        "use_class": "ingest_attribution",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": True,
        "note": "CC BY. Attribution must survive into the build manifest.",
    },
    "cc_by_sa": {
        "use_class": "ingest_share_alike",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": True,
        "note": "CC BY-SA. Share-alike obligations may propagate to derived artifacts.",
    },
    "cc_by_nc": {
        "use_class": "ingest_noncommercial",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": True,
        "note": "CC BY-NC. Non-commercial only; incompatible with a commercially deployed model.",
    },
    "cc_by_nc_sa": {
        "use_class": "ingest_noncommercial",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": True,
        "note": "CC BY-NC-SA (the MIT OpenCourseWare default). Non-commercial plus share-alike.",
    },
    "cc_by_nd": {
        "use_class": "reference_only",
        "redistribute": True,
        "derivatives": False,
        "attribution_required": True,
        "note": "No-derivatives clause. Corpus construction is a derivative use.",
    },
    "cc_by_nc_nd": {
        "use_class": "reference_only",
        "redistribute": True,
        "derivatives": False,
        "attribution_required": True,
        "note": "Non-commercial and no-derivatives. Read it, cite it, do not build on it.",
    },
    "open_license_other": {
        "use_class": "ingest_check_terms",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": True,
        "note": "Open but non-CC licence (MIT/Apache docs, OGL, publisher OA terms). Record the exact terms.",
    },
    "author_hosted_free": {
        "use_class": "reference_only",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Free to read on an author or course page, with no licence granted. Free != licensed.",
    },
    "public_but_restricted": {
        "use_class": "reference_only",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Publicly posted under restrictive terms of use (most exchange docs and rulebooks).",
    },
    "subscription_required": {
        "use_class": "reference_only",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Behind a subscription; the subscription rarely grants corpus rights.",
    },
    "licensed_purchase_required": {
        "use_class": "reference_only",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Buying a copy grants reading, not corpus construction.",
    },
    "all_rights_reserved": {
        "use_class": "reference_only",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Standard commercial copyright.",
    },
    "proprietary_confidential": {
        "use_class": "excluded",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Leaked, confidential, or NDA-bound. Do not acquire, do not cite as a source.",
    },
    "owned_by_us": {
        "use_class": "ingest_full",
        "redistribute": True,
        "derivatives": True,
        "attribution_required": False,
        "note": "We wrote it or hold the copyright.",
    },
    "unknown": {
        "use_class": "needs_review",
        "redistribute": False,
        "derivatives": False,
        "attribution_required": True,
        "note": "Not yet determined.",
    },
}

RIGHTS_CONFIDENCE = ["confirmed", "inferred", "unknown"]
ACQUISITION_STATES = ["not_acquired", "open_url", "library", "purchasable", "owned", "unavailable"]
ENTRY_STATUS = ["candidate", "reviewed", "accepted", "rejected", "acquired", "ingested"]
# A unit is a targeted part of a source: "the chapter about dealer inventory".
# It starts as a topic with no locator and becomes precise once someone opens the
# book. Reading, and therefore compiling, happens at this granularity — not at
# the granularity of a 656-page textbook.
UNIT_KINDS = ["chapter", "section", "appendix", "lecture", "module", "paper_section", "whole"]
READ_STATUS = ["unread", "located", "skimmed", "read", "compiled", "abandoned"]
ROUND_MODES = ["expand", "verify", "acquire"]

INGEST_CLASSES = {
    "ingest_full",
    "ingest_attribution",
    "ingest_share_alike",
    "ingest_noncommercial",
    "ingest_check_terms",
    "ingest_licensed",
}

STOPWORDS = {"a", "an", "the", "of", "and", "in", "on", "for", "to", "with", "its"}


# --------------------------------------------------------------------------------------
# Paths and normalization
# --------------------------------------------------------------------------------------


def corpus_paths(corpus_dir: Path) -> dict[str, Path]:
    return {
        "root": corpus_dir,
        "taxonomy": corpus_dir / "taxonomy.yaml",
        "bibliography": corpus_dir / "bibliography.yaml",
        "state": corpus_dir / "state.json",
        "rounds": corpus_dir / "rounds",
        "log": corpus_dir / "rounds" / "log.jsonl",
        "manifest": corpus_dir / "manifest.json",
        "report": corpus_dir / "REPORT.md",
        "graph": corpus_dir / "graph.json",
    }


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text


def title_key(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii").lower()
    text = text.split(":")[0]
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in STOPWORDS]
    return "-".join(words[:6])


def surname(author: str) -> str:
    cleaned = (author or "").replace(",", " ").strip()
    if not cleaned:
        return ""
    parts = [p for p in cleaned.split() if p]
    if "," in (author or ""):
        return slugify(parts[0])
    return slugify(parts[-1])


def full_title_key(title: str) -> str:
    """Like `title_key`, but keeps the subtitle.

    The prefix key is what makes fuzzy matching work — a scout writing "Trading
    and Exchanges" should resolve to the full-subtitle entry. But two volumes of
    one series share a prefix and differ only after the colon, so the prefix key
    alone would merge them. This distinguishes those.
    """
    text = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in STOPWORDS]
    return "-".join(words[:8])


def compatible_titles(left: str, right: str) -> bool:
    """True when two titles could be the same work written at different lengths."""
    a, b = full_title_key(left), full_title_key(right)
    return a == b or a.startswith(b) or b.startswith(a)


def dedupe_key(entry: dict[str, Any]) -> str:
    authors = entry.get("authors") or []
    first = surname(authors[0]) if authors else ""
    return f"{first}|{title_key(entry.get('title', ''))}"


def normalize_identifier(kind: str, value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if kind == "isbn":
        return re.sub(r"[^0-9x]", "", text) or None
    if kind == "doi":
        return re.sub(r"^https?://(dx\.)?doi\.org/", "", text) or None
    return text or None


def suggest_id(entry: dict[str, Any]) -> str:
    authors = entry.get("authors") or []
    first = surname(authors[0]) if authors else "anon"
    year = entry.get("year") or "nd"
    return f"{first}-{year}-{title_key(entry.get('title', '')) or 'untitled'}"


# --------------------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------------------


def default_entry() -> dict[str, Any]:
    return {
        "id": None,
        "title": None,
        "authors": [],
        "year": None,
        "bucket": None,
        "form": "textbook",
        "venue": None,
        "identifiers": {"isbn": None, "doi": None, "url": None},
        "pages": None,
        "density": "medium",
        "priority": 3,
        "rights": {
            "status": "unknown",
            "confidence": "unknown",
            "evidence": None,
            "checked_at": None,
            "grant": None,
            "notes": None,
        },
        "acquisition": {"state": "not_acquired", "copy_path": None},
        "units": [],
        "refs": [],
        "discovered": {"round": 0, "method": "seed", "source": None},
        "status": "candidate",
        "tags": [],
        "notes": None,
    }


def merge_defaults(entry: dict[str, Any]) -> dict[str, Any]:
    base = default_entry()
    for key, value in (entry or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged = dict(base[key])
            merged.update({k: v for k, v in value.items()})
            base[key] = merged
        else:
            base[key] = value
    if not base.get("id"):
        base["id"] = suggest_id(base)
    base["authors"] = list(base.get("authors") or [])
    base["refs"] = list(base.get("refs") or [])
    base["units"] = [normalize_unit(unit) for unit in (base.get("units") or [])]
    base["tags"] = list(base.get("tags") or [])
    return base


def normalize_unit(unit: dict[str, Any]) -> dict[str, Any]:
    base = {
        "unit_id": None,
        "topic": None,
        "title": None,      # filled in once the unit is located in the physical source
        "locator": None,    # "ch 13", "pp. 288-320", "lecture 4"
        "kind": "chapter",
        "pages": None,
        "priority": 3,
        "read_status": "unread",
        "concepts_expected": [],
        "notes": None,
    }
    base.update({k: v for k, v in (unit or {}).items()})
    if not base["unit_id"]:
        base["unit_id"] = slugify(base.get("topic") or base.get("title") or "unit")
    base["concepts_expected"] = list(base.get("concepts_expected") or [])
    return base


def entry_units(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Units of a source, falling back to one implicit whole-source unit."""
    units = entry.get("units") or []
    if units:
        return units
    return [
        normalize_unit(
            {
                "unit_id": "whole",
                "topic": entry.get("title"),
                "kind": "whole",
                "pages": entry.get("pages"),
                "priority": entry.get("priority", 3),
                "read_status": "unread",
            }
        )
    ]


def unit_pages(unit: dict[str, Any], entry: dict[str, Any]) -> int:
    if unit.get("pages"):
        return int(unit["pages"])
    return 0


def reading_queue(
    entries: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    state: dict[str, Any],
    bucket: str | None = None,
    limit: int = 25,
    include_unmapped: bool = False,
) -> list[dict[str, Any]]:
    """What to read next, at chapter granularity rather than by the book.

    A 656-page textbook is not a task. The unit that covers dealer inventory is.
    Sources with no declared units surface as a single `map_first` row: the next
    action there is to decompose the source, not to read it end to end.
    """
    cover = coverage(entries, taxonomy, state)["buckets"]
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if bucket and entry.get("bucket") != bucket:
            continue
        rights = derive_rights(entry)
        if rights["use_class"] == "excluded" or entry.get("status") == "rejected":
            continue
        declared = bool(entry.get("units"))
        if not declared and not include_unmapped:
            continue
        bucket_row = cover.get(entry.get("bucket") or "", {})
        target = bucket_row.get("target_pages") or 0
        gap = (bucket_row.get("pages_remaining") or 0) / target if target else 0.5
        for unit in entry_units(entry):
            # A unit someone has opened is not a reading task, whether or not a card
            # was compiled from it. Leaving `read` in here put already-read units at
            # the top of "what to read next", because reading raises no score.
            # Read-but-uncompiled work belongs to the compile queue, and `status`
            # counts it as `awaiting_compile` so it cannot go quiet.
            if unit.get("read_status") in {"read", "compiled", "abandoned"}:
                continue
            score = (
                0.4 * (int(unit.get("priority") or 3) / 5.0)
                + 0.3 * (int(entry.get("priority") or 3) / 5.0)
                + 0.2 * gap
                + 0.1 * (1.0 if unit.get("locator") else 0.0)
            )
            rows.append(
                {
                    "entry_id": entry["id"],
                    "unit_id": unit["unit_id"],
                    "topic": unit.get("topic"),
                    "locator": unit.get("locator"),
                    "bucket": entry.get("bucket"),
                    "pages": unit_pages(unit, entry),
                    "read_status": unit.get("read_status"),
                    "action": "read" if unit.get("locator") else ("map_first" if declared else "decompose_source"),
                    "use_class": rights["use_class"],
                    "concepts_expected": unit.get("concepts_expected"),
                    "score": round(score, 4),
                }
            )
    rows.sort(key=lambda row: (-row["score"], row["entry_id"], row["unit_id"]))
    return rows[:limit]


def load_taxonomy(paths: dict[str, Path]) -> dict[str, Any]:
    taxonomy = load_yaml(paths["taxonomy"], {}) or {}
    taxonomy.setdefault("buckets", {})
    taxonomy.setdefault("defaults", {})
    return taxonomy


def load_bibliography(paths: dict[str, Path]) -> list[dict[str, Any]]:
    raw = load_yaml(paths["bibliography"], {}) or {}
    entries = raw.get("entries") or []
    return [merge_defaults(entry) for entry in entries]


def save_bibliography(paths: dict[str, Path], entries: list[dict[str, Any]]) -> None:
    ordered = sorted(entries, key=lambda e: (str(e.get("bucket")), -int(e.get("priority") or 0), str(e.get("id"))))
    write_yaml(paths["bibliography"], {"updated_at": now_iso(), "entries": ordered})


def load_state(paths: dict[str, Path]) -> dict[str, Any]:
    return load_json(paths["state"], {"round_counter": 0, "open_rounds": [], "buckets": {}, "created_at": None})


def save_state(paths: dict[str, Path], state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    write_json(paths["state"], state)


# --------------------------------------------------------------------------------------
# Rights derivation
# --------------------------------------------------------------------------------------


def derive_rights(entry: dict[str, Any]) -> dict[str, Any]:
    """Compute the effective use class for one entry.

    Two gates apply. A licence grant we hold can upgrade a restricted work; a
    missing evidence trail downgrades anything otherwise ingestable to review.
    """
    rights = entry.get("rights") or {}
    status = rights.get("status") or "unknown"
    spec = RIGHTS_STATUS.get(status, RIGHTS_STATUS["unknown"])
    confidence = rights.get("confidence") or "unknown"
    grant = rights.get("grant")
    evidence = rights.get("evidence")
    checked_at = rights.get("checked_at")

    use_class = spec["use_class"]
    reasons: list[str] = []

    if grant:
        grant_evidence = grant.get("evidence") if isinstance(grant, dict) else None
        if grant_evidence:
            use_class = "ingest_licensed"
            reasons.append("explicit licence grant on file")
        else:
            reasons.append("licence grant claimed without evidence; ignored")

    if use_class in INGEST_CLASSES:
        if confidence != "confirmed":
            use_class = "needs_review"
            reasons.append(f"rights confidence is '{confidence}', not confirmed")
        elif not evidence:
            use_class = "needs_review"
            reasons.append("no evidence URL recorded")
        elif not checked_at:
            use_class = "needs_review"
            reasons.append("no rights check date recorded")

    return {
        "status": status,
        "confidence": confidence,
        "use_class": use_class,
        "manifest_eligible": use_class in INGEST_CLASSES,
        "study_ok": use_class != "excluded",
        "attribution_required": bool(spec["attribution_required"]) or use_class == "ingest_licensed",
        "reasons": reasons,
        "status_note": spec["note"],
    }


# --------------------------------------------------------------------------------------
# Network mapping
# --------------------------------------------------------------------------------------


def index_entries(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build lookup tables for id, dedupe key, ISBN and DOI."""
    index: dict[str, dict[str, Any]] = {"by_id": {}, "by_key": {}, "by_isbn": {}, "by_doi": {}}
    for entry in entries:
        index["by_id"][entry["id"]] = entry
        index["by_key"].setdefault(dedupe_key(entry), entry)
        identifiers = entry.get("identifiers") or {}
        isbn = normalize_identifier("isbn", identifiers.get("isbn"))
        doi = normalize_identifier("doi", identifiers.get("doi"))
        if isbn:
            index["by_isbn"][isbn] = entry
        if doi:
            index["by_doi"][doi] = entry
    return index


def parse_ref(ref: Any) -> dict[str, Any]:
    """Refs are either a bare id/label string or a mapping with target + relation."""
    if isinstance(ref, str):
        return {"target": ref, "relation": "cites", "note": None}
    ref = dict(ref or {})
    ref.setdefault("relation", "cites")
    ref.setdefault("note", None)
    ref.setdefault("target", ref.get("title"))
    return ref


def resolve_ref(ref: dict[str, Any], index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    target = ref.get("target")
    if not target:
        return None
    if target in index["by_id"]:
        return index["by_id"][target]
    probe = {"title": target, "authors": ref.get("authors") or []}
    if not probe["authors"] and ref.get("author"):
        probe["authors"] = [ref["author"]]
    key = dedupe_key(probe)
    candidate = index["by_key"].get(key)
    if candidate is not None and compatible_titles(target, candidate.get("title", "")):
        return candidate
    # A bare title with no author still resolves if exactly one stored title matches.
    title_only = title_key(target)
    matches = [
        entry
        for stored_key, entry in index["by_key"].items()
        if stored_key.split("|", 1)[1] == title_only and compatible_titles(target, entry.get("title", ""))
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def matches_frontier_label(label: str, entry: dict[str, Any]) -> bool:
    """Decide whether a newly catalogued entry is the work a frontier label pointed at.

    Frontier labels are how a scout wrote a reference down ("Ho & Stoll — Optimal
    dealer pricing..."), so an exact key match is the exception. Require a real
    title overlap, plus an author signal unless the title overlap is already long.
    """
    label_words = set(title_key(label).split("-")) - {""}
    title_words = set(title_key(entry.get("title", "")).split("-")) - {""}
    shared = label_words & title_words
    if len(shared) < 3:
        return False
    label_slug = slugify(label)
    author_hit = any(surname(a) and surname(a) in label_slug for a in entry.get("authors") or [])
    return author_hit or len(shared) >= 5


def rewrite_refs(entries: list[dict[str, Any]], label: str, new_id: str) -> int:
    """Point every ref that used a free-text label at the entry that now covers it."""
    target_key = dedupe_key({"title": label, "authors": []})
    rewritten = 0
    for entry in entries:
        refs = entry.get("refs") or []
        for position, raw_ref in enumerate(refs):
            ref = parse_ref(raw_ref)
            if ref.get("target") == new_id:
                continue
            if dedupe_key({"title": str(ref.get("target")), "authors": ref.get("authors") or []}) != target_key:
                continue
            ref["target"] = new_id
            refs[position] = ref
            rewritten += 1
    return rewritten


def resolve_frontier(entries: list[dict[str, Any]], added_ids: list[str], declared: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Close frontier targets that a round actually found.

    `declared` is what the scout claimed (findings entries may carry `resolves:`);
    anything not declared is matched heuristically against the round's new entries.
    """
    resolved: list[dict[str, Any]] = []
    graph = build_graph(entries)
    open_labels = {node["key"]: node["label"] for node in graph["unresolved"].values()}
    by_id = {entry["id"]: entry for entry in entries}

    for entry_id in list(dict.fromkeys([*added_ids, *declared.keys()])):
        entry = by_id.get(entry_id)
        if entry is None:
            continue
        claimed = declared.get(entry_id) or []
        for label in claimed:
            count = rewrite_refs(entries, label, entry_id)
            if count:
                resolved.append({"label": label, "entry": entry_id, "refs_rewritten": count, "via": "declared"})
        if entry_id not in added_ids:
            continue  # heuristic matching only for works catalogued this round
        claimed_keys = {dedupe_key({"title": label, "authors": []}) for label in claimed}
        for key, label in open_labels.items():
            if key in claimed_keys or not matches_frontier_label(label, entry):
                continue
            count = rewrite_refs(entries, label, entry_id)
            if count:
                resolved.append({"label": label, "entry": entry_id, "refs_rewritten": count, "via": "matched"})
    return resolved


def build_graph(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve every ref into either an internal edge or an unresolved frontier node."""
    index = index_entries(entries)
    edges: list[dict[str, Any]] = []
    unresolved: dict[str, dict[str, Any]] = {}
    in_degree = {entry["id"]: 0 for entry in entries}
    out_degree = {entry["id"]: 0 for entry in entries}

    for entry in entries:
        for raw_ref in entry.get("refs") or []:
            ref = parse_ref(raw_ref)
            target_entry = resolve_ref(ref, index)
            if target_entry is not None:
                if target_entry["id"] == entry["id"]:
                    continue
                edges.append(
                    {
                        "source": entry["id"],
                        "target": target_entry["id"],
                        "relation": ref.get("relation", "cites"),
                    }
                )
                in_degree[target_entry["id"]] = in_degree.get(target_entry["id"], 0) + 1
                out_degree[entry["id"]] = out_degree.get(entry["id"], 0) + 1
                continue

            label = str(ref.get("target"))
            key = dedupe_key({"title": label, "authors": ref.get("authors") or []})
            node = unresolved.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "relation": ref.get("relation", "cites"),
                    "supported_by": [],
                    "buckets": [],
                    "priority_sum": 0,
                    "note": ref.get("note"),
                    "suggested_bucket": ref.get("bucket"),
                },
            )
            if entry["id"] not in node["supported_by"]:
                node["supported_by"].append(entry["id"])
                node["priority_sum"] += int(entry.get("priority") or 3)
            if entry.get("bucket") and entry["bucket"] not in node["buckets"]:
                node["buckets"].append(entry["bucket"])
            if not node["suggested_bucket"]:
                node["suggested_bucket"] = entry.get("bucket")

    # Undirected connected components, so an isolated pocket of literature is visible.
    parent = {entry["id"]: entry["id"] for entry in entries}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    for edge in edges:
        a, b = find(edge["source"]), find(edge["target"])
        if a != b:
            parent[a] = b

    components: dict[str, list[str]] = {}
    for entry in entries:
        components.setdefault(find(entry["id"]), []).append(entry["id"])

    # Bridges: entries that connect two or more buckets. These carry the transfer value.
    bucket_of = {entry["id"]: entry.get("bucket") for entry in entries}
    bridge_buckets: dict[str, set[str]] = {entry["id"]: set() for entry in entries}
    for edge in edges:
        src_bucket, dst_bucket = bucket_of.get(edge["source"]), bucket_of.get(edge["target"])
        if src_bucket and dst_bucket and src_bucket != dst_bucket:
            bridge_buckets[edge["source"]].add(dst_bucket)
            bridge_buckets[edge["target"]].add(src_bucket)

    return {
        "edges": edges,
        "unresolved": unresolved,
        "in_degree": in_degree,
        "out_degree": out_degree,
        "components": sorted(components.values(), key=len, reverse=True),
        "bridges": {node_id: sorted(buckets) for node_id, buckets in bridge_buckets.items() if buckets},
        "isolated": [entry["id"] for entry in entries if not in_degree.get(entry["id"]) and not out_degree.get(entry["id"])],
    }


# --------------------------------------------------------------------------------------
# Coverage and saturation
# --------------------------------------------------------------------------------------


def coverage(entries: list[dict[str, Any]], taxonomy: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    buckets = taxonomy.get("buckets") or {}
    summary: dict[str, Any] = {}
    for name, spec in buckets.items():
        summary[name] = {
            "tier": spec.get("tier"),
            "target_pages": int(spec.get("target_pages") or 0),
            "entries": 0,
            "pages_mapped": 0,
            "pages_manifest_eligible": 0,
            "pages_reference_only": 0,
            "pages_needs_review": 0,
            "high_priority_open": 0,
            "dry_rounds": int((state.get("buckets") or {}).get(name, {}).get("dry_rounds") or 0),
        }

    unbucketed: list[str] = []
    for entry in entries:
        bucket = entry.get("bucket")
        if bucket not in summary:
            unbucketed.append(entry["id"])
            continue
        rights = derive_rights(entry)
        pages = int(entry.get("pages") or 0)
        row = summary[bucket]
        row["entries"] += 1
        row["pages_mapped"] += pages
        if rights["manifest_eligible"]:
            row["pages_manifest_eligible"] += pages
        elif rights["use_class"] == "needs_review":
            row["pages_needs_review"] += pages
        elif rights["use_class"] == "reference_only":
            row["pages_reference_only"] += pages
        if int(entry.get("priority") or 0) >= 4 and entry.get("status") in {"candidate", "reviewed"}:
            row["high_priority_open"] += 1

    for row in summary.values():
        target = row["target_pages"]
        row["mapped_pct"] = round(100.0 * row["pages_mapped"] / target, 1) if target else None
        row["eligible_pct"] = round(100.0 * row["pages_manifest_eligible"] / target, 1) if target else None
        row["pages_remaining"] = max(target - row["pages_mapped"], 0)

    return {"buckets": summary, "unbucketed": unbucketed}


def saturation_state(row: dict[str, Any], frontier_count: int, threshold: int) -> str:
    if row["dry_rounds"] >= threshold and frontier_count == 0:
        return "saturated"
    if row["dry_rounds"] >= 1:
        return "cooling"
    return "open"


# --------------------------------------------------------------------------------------
# Frontier
# --------------------------------------------------------------------------------------


def frontier(
    entries: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    state: dict[str, Any],
    bucket: str | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Rank unresolved references by co-citation support and bucket gap.

    This is the network-identification step: what several mapped works point at,
    in a bucket that is still short of its page target, is what to scout next.
    """
    graph = build_graph(entries)
    cover = coverage(entries, taxonomy, state)["buckets"]
    targets: list[dict[str, Any]] = []

    for node in graph["unresolved"].values():
        node_bucket = node.get("suggested_bucket")
        if bucket and node_bucket != bucket and bucket not in node["buckets"]:
            continue
        support = len(node["supported_by"])
        mean_priority = node["priority_sum"] / support if support else 3.0
        row = cover.get(node_bucket or "", {})
        target_pages = row.get("target_pages") or 0
        gap = (row.get("pages_remaining") or 0) / target_pages if target_pages else 0.5
        bridge_bonus = 0.5 if len(node["buckets"]) > 1 else 0.0
        score = 2.0 * math.log1p(support) + 0.6 * (mean_priority / 5.0) + 1.5 * gap + bridge_bonus
        targets.append(
            {
                "label": node["label"],
                "key": node["key"],
                "suggested_bucket": node_bucket,
                "support": support,
                "supported_by": node["supported_by"],
                "cross_bucket": len(node["buckets"]) > 1,
                "relation": node["relation"],
                "note": node["note"],
                "score": round(score, 3),
                "score_parts": {
                    "support": round(2.0 * math.log1p(support), 3),
                    "citing_priority": round(0.6 * (mean_priority / 5.0), 3),
                    "bucket_gap": round(1.5 * gap, 3),
                    "bridge": bridge_bonus,
                },
            }
        )

    targets.sort(key=lambda t: (-t["score"], t["label"]))
    return targets[:limit]


def verify_queue(entries: list[dict[str, Any]], limit: int = 25, bucket: str | None = None) -> list[dict[str, Any]]:
    """Entries whose rights tag is not yet load-bearing, ranked by what they would unlock."""
    rows = []
    for entry in entries:
        if bucket and entry.get("bucket") != bucket:
            continue
        rights = derive_rights(entry)
        if rights["manifest_eligible"] or rights["use_class"] == "excluded":
            continue
        if rights["use_class"] == "reference_only" and rights["confidence"] == "confirmed":
            continue  # settled: read-only, no further verification buys anything
        pages = int(entry.get("pages") or 0)
        # Rank by what a confirmation would unlock, not just by size. A commercial
        # textbook stays reference-only however carefully we check it.
        spec = RIGHTS_STATUS.get(rights["status"], RIGHTS_STATUS["unknown"])
        if spec["use_class"] in INGEST_CLASSES:
            upside = 1.0
        elif rights["status"] == "unknown":
            upside = 0.6
        else:
            upside = 0.15
        score = upside * int(entry.get("priority") or 3) * (1 + math.log1p(pages))
        rows.append(
            {
                "upside": upside,
                "id": entry["id"],
                "title": entry.get("title"),
                "bucket": entry.get("bucket"),
                "form": entry.get("form"),
                "pages": pages,
                "priority": entry.get("priority"),
                "rights_status": rights["status"],
                "rights_confidence": rights["confidence"],
                "use_class": rights["use_class"],
                "blockers": rights["reasons"],
                "score": round(score, 2),
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return rows[:limit]


def acquire_queue(entries: list[dict[str, Any]], limit: int = 25, bucket: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for entry in entries:
        if bucket and entry.get("bucket") != bucket:
            continue
        rights = derive_rights(entry)
        if not rights["manifest_eligible"]:
            continue
        acquisition = entry.get("acquisition") or {}
        if acquisition.get("state") == "owned" and acquisition.get("copy_path"):
            continue
        rows.append(
            {
                "id": entry["id"],
                "title": entry.get("title"),
                "bucket": entry.get("bucket"),
                "pages": entry.get("pages"),
                "use_class": rights["use_class"],
                "acquisition_state": acquisition.get("state"),
                "url": (entry.get("identifiers") or {}).get("url"),
            }
        )
    rows.sort(key=lambda r: (-(r["pages"] or 0), r["id"]))
    return rows[:limit]


# --------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------


def validate(entries: list[dict[str, Any]], taxonomy: dict[str, Any]) -> dict[str, Any]:
    buckets = set((taxonomy.get("buckets") or {}).keys())
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    seen_keys: dict[str, tuple[str, str]] = {}

    for entry in entries:
        entry_id = entry.get("id")
        if not entry.get("title"):
            errors.append(f"{entry_id}: missing title")
        if entry_id in seen_ids:
            errors.append(f"{entry_id}: duplicate id")
        seen_ids.add(entry_id)

        key = dedupe_key(entry)
        if key in seen_keys and seen_keys[key][0] != entry_id:
            other_id, other_title = seen_keys[key]
            if compatible_titles(entry.get("title", ""), other_title):
                warnings.append(f"{entry_id}: probable duplicate of {other_id} (key {key})")
        seen_keys.setdefault(key, (entry_id, entry.get("title", "")))

        if entry.get("form") not in FORMS:
            errors.append(f"{entry_id}: unknown form '{entry.get('form')}'")
        if buckets and entry.get("bucket") not in buckets:
            errors.append(f"{entry_id}: unknown bucket '{entry.get('bucket')}'")

        rights = entry.get("rights") or {}
        if rights.get("status") not in RIGHTS_STATUS:
            errors.append(f"{entry_id}: unknown rights status '{rights.get('status')}'")
        if rights.get("confidence") not in RIGHTS_CONFIDENCE:
            errors.append(f"{entry_id}: unknown rights confidence '{rights.get('confidence')}'")
        if rights.get("confidence") == "confirmed" and not rights.get("evidence"):
            errors.append(f"{entry_id}: rights confirmed without evidence")

        acquisition = entry.get("acquisition") or {}
        if acquisition.get("state") not in ACQUISITION_STATES:
            errors.append(f"{entry_id}: unknown acquisition state '{acquisition.get('state')}'")
        if entry.get("status") not in ENTRY_STATUS:
            errors.append(f"{entry_id}: unknown status '{entry.get('status')}'")
        if entry.get("pages") is not None and int(entry.get("pages") or 0) < 0:
            errors.append(f"{entry_id}: negative page count")

        seen_units: set[str] = set()
        unit_pages_total = 0
        for unit in entry.get("units") or []:
            unit_id = unit.get("unit_id")
            if unit_id in seen_units:
                errors.append(f"{entry_id}: duplicate unit '{unit_id}'")
            seen_units.add(unit_id)
            if not unit.get("topic") and not unit.get("title"):
                errors.append(f"{entry_id}/{unit_id}: unit needs a topic or a title")
            if unit.get("kind") not in UNIT_KINDS:
                errors.append(f"{entry_id}/{unit_id}: unknown unit kind '{unit.get('kind')}'")
            if unit.get("read_status") not in READ_STATUS:
                errors.append(f"{entry_id}/{unit_id}: unknown read_status '{unit.get('read_status')}'")
            if unit.get("read_status") in {"skimmed", "read", "compiled"} and not unit.get("locator"):
                warnings.append(f"{entry_id}/{unit_id}: marked {unit.get('read_status')} but never located")
            unit_pages_total += int(unit.get("pages") or 0)
        if entry.get("pages") and unit_pages_total > int(entry["pages"]) * 1.05:
            warnings.append(
                f"{entry_id}: units total {unit_pages_total} pages against a {entry['pages']}-page source"
            )

    index = index_entries(entries)
    for entry in entries:
        for raw_ref in entry.get("refs") or []:
            ref = parse_ref(raw_ref)
            target = ref.get("target")
            if not target:
                errors.append(f"{entry.get('id')}: ref with no target")
            elif target.startswith("id:") and target[3:] not in index["by_id"]:
                errors.append(f"{entry.get('id')}: dangling id ref '{target}'")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "entry_count": len(entries)}


# --------------------------------------------------------------------------------------
# Rounds
# --------------------------------------------------------------------------------------


def round_dir(paths: dict[str, Path], number: int) -> Path:
    return paths["rounds"] / f"round-{number:03d}"


def render_request_markdown(request: dict[str, Any], taxonomy: dict[str, Any]) -> str:
    lines: list[str] = []
    mode = request["mode"]
    lines.append(f"# Corpus round {request['round']:03d} — {mode}")
    lines.append("")
    lines.append(f"Opened: {request['opened_at']}")
    lines.append(f"Buckets: {', '.join(request['buckets']) or 'all'}")
    lines.append("")
    lines.append("## What to do")
    lines.append("")
    if mode == "expand":
        lines.append(
            "Find the works below, identify them precisely, and map their neighbourhood. "
            "For each target, record the bibliographic identity, the form, the rights status "
            "with evidence, and the works *it* points at (`refs`) so the next round has a frontier."
        )
    elif mode == "verify":
        lines.append(
            "Resolve the rights of the entries below. A rights tag only counts when it is "
            "`confidence: confirmed` with an `evidence` URL and a `checked_at` date. "
            "Do not guess: if the licence page is silent, record `all_rights_reserved` (confirmed) "
            "or leave it `unknown` and say what you checked."
        )
    else:
        lines.append(
            "Acquire the entries below through a legitimate channel and record where the copy lives. "
            "Never record a copy path for anything that is not manifest-eligible."
        )
    lines.append("")
    lines.append(f"Write findings to `{request['findings_path']}`, then close the round.")
    lines.append("")

    if request.get("targets"):
        lines.append("## Targets")
        lines.append("")
        if mode == "expand":
            lines.append("| # | Target | Suggested bucket | Support | Cross-bucket | Score |")
            lines.append("|---|---|---|---|---|---|")
            for i, target in enumerate(request["targets"], 1):
                lines.append(
                    f"| {i} | {target['label']} | {target.get('suggested_bucket') or '—'} | "
                    f"{target['support']} | {'yes' if target['cross_bucket'] else 'no'} | {target['score']} |"
                )
        elif mode == "verify":
            lines.append("| # | Entry | Bucket | Pages | Current status | Blockers |")
            lines.append("|---|---|---|---|---|---|")
            for i, target in enumerate(request["targets"], 1):
                lines.append(
                    f"| {i} | {target['id']} | {target.get('bucket') or '—'} | {target.get('pages') or '—'} | "
                    f"{target['rights_status']}/{target['rights_confidence']} | {'; '.join(target['blockers']) or '—'} |"
                )
        else:
            lines.append("| # | Entry | Bucket | Pages | Use class | Acquisition | URL |")
            lines.append("|---|---|---|---|---|---|---|")
            for i, target in enumerate(request["targets"], 1):
                lines.append(
                    f"| {i} | {target['id']} | {target.get('bucket') or '—'} | {target.get('pages') or '—'} | "
                    f"{target['use_class']} | {target.get('acquisition_state')} | {target.get('url') or '—'} |"
                )
        lines.append("")

    lines.append("## Bucket state")
    lines.append("")
    lines.append("| Bucket | Target pages | Mapped | Manifest-eligible | Dry rounds |")
    lines.append("|---|---|---|---|---|")
    for name, row in request["coverage"].items():
        if request["buckets"] and name not in request["buckets"]:
            continue
        lines.append(
            f"| {name} | {row['target_pages']} | {row['pages_mapped']} | "
            f"{row['pages_manifest_eligible']} | {row['dry_rounds']} |"
        )
    lines.append("")
    lines.append("## Findings schema")
    lines.append("")
    lines.append("```yaml")
    lines.append("round: %d" % request["round"])
    lines.append("entries:")
    lines.append("  - id: null                     # leave null to auto-derive")
    lines.append("    title: \"...\"")
    lines.append("    authors: [\"...\"]")
    lines.append("    year: 0")
    lines.append("    bucket: %s" % (request["buckets"][0] if request["buckets"] else "<bucket>"))
    lines.append("    form: %s" % " | ".join(sorted(FORMS)[:6]) + " | ...")
    lines.append("    pages: 0")
    lines.append("    priority: 1-5")
    lines.append("    rights:")
    lines.append("      status: %s" % " | ".join(sorted(RIGHTS_STATUS)[:5]) + " | ...")
    lines.append("      confidence: confirmed | inferred | unknown")
    lines.append("      evidence: \"https://...\"      # required for confirmed")
    lines.append("      checked_at: \"YYYY-MM-DD\"")
    lines.append("    acquisition: {state: not_acquired}")
    lines.append("    resolves:                    # frontier labels from the table above that this entry IS")
    lines.append("      - \"Author — Title as it appears in the target list\"")
    lines.append("    refs:")
    lines.append("      - target: \"Work this points at\"")
    lines.append("        relation: cites | builds_on | syllabus_with | supersedes")
    lines.append("```")
    lines.append("")
    lines.append("Vocabularies: `labrat corpus vocab`. Nothing is ingestable without confirmed rights + evidence.")
    lines.append("")
    return "\n".join(lines)


def open_round(
    paths: dict[str, Path],
    entries: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    state: dict[str, Any],
    mode: str,
    buckets: list[str],
    limit: int,
) -> dict[str, Any]:
    number = int(state.get("round_counter") or 0) + 1
    directory = round_dir(paths, number)
    directory.mkdir(parents=True, exist_ok=True)

    if mode == "expand":
        if buckets:
            targets: list[dict[str, Any]] = []
            per_bucket = max(1, limit // len(buckets))
            for bucket in buckets:
                targets.extend(frontier(entries, taxonomy, state, bucket=bucket, limit=per_bucket))
        else:
            targets = frontier(entries, taxonomy, state, limit=limit)
    elif mode == "verify":
        targets = []
        for bucket in buckets or [None]:
            targets.extend(verify_queue(entries, limit=limit, bucket=bucket))
    else:
        targets = []
        for bucket in buckets or [None]:
            targets.extend(acquire_queue(entries, limit=limit, bucket=bucket))

    cover = coverage(entries, taxonomy, state)["buckets"]
    findings_path = directory / "findings.yaml"
    request = {
        "round": number,
        "mode": mode,
        "buckets": buckets,
        "limit": limit,
        "opened_at": now_iso(),
        "findings_path": str(findings_path),
        "targets": targets,
        "coverage": cover,
        "entry_count": len(entries),
    }
    write_json(directory / "request.json", request)
    write_text(directory / "request.md", render_request_markdown(request, taxonomy))
    if not findings_path.exists():
        write_text(
            findings_path,
            "# Fill this in, then run: labrat corpus round close\n"
            f"round: {number}\n"
            "entries: []\n",
        )

    state["round_counter"] = number
    state.setdefault("open_rounds", []).append({"round": number, "mode": mode, "buckets": buckets})
    save_state(paths, state)
    return request


def apply_findings_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge one finding into a stored entry. Rights only move on evidence."""
    changes: list[str] = []
    merged = json.loads(json.dumps(existing))

    stated = incoming.get("_stated")
    stated_nested = incoming.get("_stated_nested") or {}

    def was_written(field: str, key: str | None = None) -> bool:
        """Did the scout write this, or is it merge_defaults talking?"""
        if stated is None:
            return True  # called directly, e.g. from a test; take the payload at face value
        if key is None:
            return field in stated
        return key in (stated_nested.get(field) or set())

    for field in ("title", "authors", "year", "bucket", "form", "venue", "pages", "density", "priority", "notes", "status"):
        value = incoming.get(field)
        if value in (None, [], "") or not was_written(field):
            continue
        if merged.get(field) != value:
            merged[field] = value
            changes.append(field)

    for field in ("identifiers", "acquisition"):
        for key, value in (incoming.get(field) or {}).items():
            if value in (None, "") or not was_written(field, key):
                continue
            if (merged.get(field) or {}).get(key) != value:
                merged.setdefault(field, {})[key] = value
                changes.append(f"{field}.{key}")

    incoming_rights = {k: v for k, v in (incoming.get("rights") or {}).items() if was_written("rights", k)}
    if incoming_rights:
        current = merged.get("rights") or {}
        incoming_conf = incoming_rights.get("confidence")
        # A downgrade to unknown never overwrites a confirmed tag; an upgrade needs evidence.
        if incoming_conf == "confirmed" and not incoming_rights.get("evidence"):
            changes.append("rights.rejected_no_evidence")
        elif incoming_conf == "confirmed" or current.get("confidence") != "confirmed":
            for key, value in incoming_rights.items():
                if value in (None, ""):
                    continue
                if current.get(key) != value:
                    merged.setdefault("rights", {})[key] = value
                    changes.append(f"rights.{key}")

    incoming_tags = incoming.get("tags") or []
    for tag in incoming_tags:
        if tag not in merged.get("tags", []):
            merged.setdefault("tags", []).append(tag)
            changes.append("tags")

    # Units: a reading round's whole payload. Merge by unit_id, and let read_status
    # advance but never silently regress — a scout who did not open something must not
    # be able to un-read what someone else opened.
    incoming_units = incoming.get("units") or []
    if incoming_units and was_written("units"):
        by_id = {unit.get("unit_id"): unit for unit in (merged.get("units") or [])}
        order = {status: rank for rank, status in enumerate(READ_STATUS)}
        for unit in incoming_units:
            unit_id = unit.get("unit_id")
            if not unit_id:
                continue
            current = by_id.get(unit_id)
            if current is None:
                merged.setdefault("units", []).append(unit)
                by_id[unit_id] = unit
                changes.append(f"units.{unit_id}.added")
                continue
            for key, value in unit.items():
                if value in (None, "", []) or key == "unit_id":
                    continue
                if key == "read_status":
                    if order.get(value, -1) <= order.get(current.get("read_status"), -1) and value != "abandoned":
                        continue
                if current.get(key) != value:
                    current[key] = value
                    changes.append(f"units.{unit_id}.{key}")

    existing_refs = {json.dumps(parse_ref(r), sort_keys=True) for r in merged.get("refs") or []}
    for raw_ref in incoming.get("refs") or []:
        ref = parse_ref(raw_ref)
        if json.dumps(ref, sort_keys=True) not in existing_refs:
            merged.setdefault("refs", []).append(ref)
            changes.append("refs")

    return merged, sorted(set(changes))


def _key_match(index: dict[str, dict[str, Any]], incoming: dict[str, Any]) -> dict[str, Any] | None:
    """Prefix-key lookup, guarded so two volumes of one series stay distinct."""
    candidate = index["by_key"].get(dedupe_key(incoming))
    if candidate is None:
        return None
    return candidate if compatible_titles(incoming.get("title", ""), candidate.get("title", "")) else None


def close_round(
    paths: dict[str, Path],
    entries: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    state: dict[str, Any],
    number: int,
    findings_path: Path | None,
) -> dict[str, Any]:
    directory = round_dir(paths, number)
    request = load_json(directory / "request.json", {})
    if not request:
        raise SystemExit(f"ERROR: no request found for round {number} ({directory})")

    findings_file = findings_path or Path(request.get("findings_path") or (directory / "findings.yaml"))
    findings = load_yaml(findings_file, {}) or {}
    # merge_defaults fills the shape, so remember which keys the scout actually wrote.
    # Without this a finding that mentions only `units` silently resets acquisition
    # state to the default, which is a real edit nobody asked for.
    incoming_entries = []
    for raw in (findings.get("entries") or []):
        stated = {key for key, value in raw.items() if value not in (None, [], {}, "")}
        nested = {
            field: {k for k, v in (raw.get(field) or {}).items() if v not in (None, "")}
            for field in ("identifiers", "acquisition", "rights")
        }
        entry = merge_defaults(raw)
        entry["_stated"], entry["_stated_nested"] = stated, nested
        incoming_entries.append(entry)
    confirmed_before = sum(1 for e in entries if (e.get("rights") or {}).get("confidence") == "confirmed")
    eligible_before = build_manifest(entries, taxonomy)["include_pages"]
    graph_before = build_graph(entries)
    bridges_before, edges_before = len(graph_before["bridges"]), len(graph_before["edges"])

    index = index_entries(entries)
    added: list[str] = []
    updated: list[dict[str, Any]] = []
    unchanged: list[str] = []
    rejected: list[dict[str, Any]] = []
    declared: dict[str, list[str]] = {}

    for incoming in incoming_entries:
        claimed = incoming.pop("resolves", None) or []
        identifiers = incoming.get("identifiers") or {}
        isbn = normalize_identifier("isbn", identifiers.get("isbn"))
        doi = normalize_identifier("doi", identifiers.get("doi"))
        existing = (
            index["by_id"].get(incoming["id"])
            or (index["by_isbn"].get(isbn) if isbn else None)
            or (index["by_doi"].get(doi) if doi else None)
            or _key_match(index, incoming)
        )
        if existing is None:
            if not incoming.get("title"):
                rejected.append({"id": incoming.get("id"), "reason": "no title"})
                continue
            incoming["discovered"] = {
                "round": number,
                "method": incoming.get("discovered", {}).get("method") or request.get("mode", "expand"),
                "source": incoming.get("discovered", {}).get("source"),
            }
            incoming.pop("_stated", None)
            incoming.pop("_stated_nested", None)
            entries.append(incoming)
            index = index_entries(entries)
            added.append(incoming["id"])
            if claimed:
                declared.setdefault(incoming["id"], []).extend(claimed)
            continue

        merged, changes = apply_findings_entry(existing, incoming)
        if claimed:
            declared.setdefault(existing["id"], []).extend(claimed)
        if changes:
            entries[entries.index(existing)] = merged
            index = index_entries(entries)
            updated.append({"id": merged["id"], "changes": changes})
        else:
            unchanged.append(existing["id"])

    resolved = resolve_frontier(entries, added, declared)

    # Round metrics. `rediscovery_rate` is the saturation signal: when a round mostly
    # returns things already mapped, that bucket is close to exhausted.
    seen = len(incoming_entries)
    rediscovery_rate = round((len(updated) + len(unchanged)) / seen, 3) if seen else 0.0
    new_pages = {}
    new_high_priority = 0
    for entry_id in added:
        entry = index["by_id"][entry_id]
        bucket = entry.get("bucket") or "unbucketed"
        new_pages[bucket] = new_pages.get(bucket, 0) + int(entry.get("pages") or 0)
        if int(entry.get("priority") or 0) >= 4:
            new_high_priority += 1

    rights_confirmed = sum(1 for e in entries if (e.get("rights") or {}).get("confidence") == "confirmed")
    graph = build_graph(entries)

    # Only expansion rounds carry saturation evidence. A verify or acquire round that
    # adds no new work says nothing about whether the bucket still has material in it.
    touched_buckets = request.get("buckets") or sorted({e.get("bucket") for e in entries if e.get("bucket")})
    bucket_state = state.setdefault("buckets", {})
    for bucket in touched_buckets:
        row = bucket_state.setdefault(bucket, {"dry_rounds": 0, "last_round": None})
        if request.get("mode") == "expand":
            produced = any(index["by_id"][a].get("bucket") == bucket for a in added)
            row["dry_rounds"] = 0 if produced else int(row.get("dry_rounds") or 0) + 1
        row["last_round"] = number

    report = {
        "round": number,
        "mode": request.get("mode"),
        "buckets": request.get("buckets"),
        "closed_at": now_iso(),
        "findings_file": str(findings_file),
        "findings_seen": seen,
        "added": added,
        "updated": updated,
        "unchanged": unchanged,
        "rejected": rejected,
        "resolved_frontier": resolved,
        "new_entries": len(added),
        "new_high_priority": new_high_priority,
        "new_pages_by_bucket": new_pages,
        "rediscovery_rate": rediscovery_rate,
        "unresolved_frontier": len(graph["unresolved"]),
        "entries_total": len(entries),
        "rights_confirmed_total": rights_confirmed,
        "rights_confirmed_delta": rights_confirmed - confirmed_before,
        "eligible_pages_delta": build_manifest(entries, taxonomy)["include_pages"] - eligible_before,
        "edges_total": len(graph["edges"]),
        "edges_delta": len(graph["edges"]) - edges_before,
        "bridges_total": len(graph["bridges"]),
        "bridges_delta": len(graph["bridges"]) - bridges_before,
    }

    save_bibliography(paths, entries)
    write_json(directory / "merge_report.json", report)
    append_jsonl(paths["log"], report)
    state["open_rounds"] = [r for r in state.get("open_rounds", []) if r.get("round") != number]
    save_state(paths, state)
    return report


# --------------------------------------------------------------------------------------
# Manifest and reports
# --------------------------------------------------------------------------------------


def build_manifest(entries: list[dict[str, Any]], taxonomy: dict[str, Any]) -> dict[str, Any]:
    include: list[dict[str, Any]] = []
    hold: list[dict[str, Any]] = []
    for entry in entries:
        rights = derive_rights(entry)
        row = {
            "id": entry["id"],
            "title": entry.get("title"),
            "authors": entry.get("authors"),
            "bucket": entry.get("bucket"),
            "form": entry.get("form"),
            "pages": entry.get("pages"),
            "use_class": rights["use_class"],
            "rights_status": rights["status"],
            "evidence": (entry.get("rights") or {}).get("evidence"),
            "checked_at": (entry.get("rights") or {}).get("checked_at"),
            "attribution_required": rights["attribution_required"],
            "copy_path": (entry.get("acquisition") or {}).get("copy_path"),
        }
        if rights["manifest_eligible"]:
            include.append(row)
        else:
            hold.append({**row, "reasons": rights["reasons"] or [rights["status_note"]]})

    by_class: dict[str, int] = {}
    for row in include:
        by_class[row["use_class"]] = by_class.get(row["use_class"], 0) + 1

    return {
        "generated_at": now_iso(),
        "policy": "manifest requires rights.confidence == confirmed, an evidence URL, and a check date",
        "include_count": len(include),
        "hold_count": len(hold),
        "include_pages": sum(int(r["pages"] or 0) for r in include),
        "by_use_class": by_class,
        "include": include,
        "hold": hold,
    }


def status_payload(entries: list[dict[str, Any]], taxonomy: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    cover = coverage(entries, taxonomy, state)
    graph = build_graph(entries)
    threshold = int((taxonomy.get("defaults") or {}).get("saturation_dry_rounds") or 2)

    frontier_by_bucket: dict[str, int] = {}
    for node in graph["unresolved"].values():
        bucket = node.get("suggested_bucket") or "unbucketed"
        frontier_by_bucket[bucket] = frontier_by_bucket.get(bucket, 0) + 1

    for name, row in cover["buckets"].items():
        row["frontier_open"] = frontier_by_bucket.get(name, 0)
        row["saturation"] = saturation_state(row, row["frontier_open"], threshold)

    forms: dict[str, int] = {}
    rights_status: dict[str, int] = {}
    use_classes: dict[str, int] = {}
    for entry in entries:
        forms[entry.get("form")] = forms.get(entry.get("form"), 0) + 1
        derived = derive_rights(entry)
        rights_status[derived["status"]] = rights_status.get(derived["status"], 0) + 1
        use_classes[derived["use_class"]] = use_classes.get(derived["use_class"], 0) + 1

    manifest = build_manifest(entries, taxonomy)

    units_declared = sum(len(entry.get("units") or []) for entry in entries)
    unit_states: dict[str, int] = {}
    unit_pages_mapped = 0
    for entry in entries:
        for unit in entry.get("units") or []:
            unit_states[unit.get("read_status")] = unit_states.get(unit.get("read_status"), 0) + 1
            unit_pages_mapped += int(unit.get("pages") or 0)
    sources_decomposed = sum(1 for entry in entries if entry.get("units"))

    return {
        "generated_at": now_iso(),
        "entries": len(entries),
        "rounds_run": int(state.get("round_counter") or 0),
        "open_rounds": state.get("open_rounds", []),
        "pages_mapped": sum(int(e.get("pages") or 0) for e in entries),
        "pages_manifest_eligible": manifest["include_pages"],
        "target_pages": sum(row["target_pages"] for row in cover["buckets"].values()),
        "frontier_open": len(graph["unresolved"]),
        "edges": len(graph["edges"]),
        "components": len(graph["components"]),
        "largest_component": len(graph["components"][0]) if graph["components"] else 0,
        "isolated": len(graph["isolated"]),
        "bridges": len(graph["bridges"]),
        "forms": dict(sorted(forms.items(), key=lambda kv: -kv[1])),
        "rights_status": dict(sorted(rights_status.items(), key=lambda kv: -kv[1])),
        "use_classes": dict(sorted(use_classes.items(), key=lambda kv: -kv[1])),
        "buckets": cover["buckets"],
        "unbucketed": cover["unbucketed"],
        "units_declared": units_declared,
        "unit_states": dict(sorted(unit_states.items(), key=lambda kv: -kv[1])),
        # Read but not yet compiled. These leave the reading queue and are only
        # visible here, so the number is the backlog the compile queue owes.
        "units_awaiting_compile": unit_states.get("read", 0),
        "unit_pages_mapped": unit_pages_mapped,
        "sources_decomposed": sources_decomposed,
        "sources_not_decomposed": len(entries) - sources_decomposed,
        "corpus_saturated": all(row["saturation"] == "saturated" for row in cover["buckets"].values()) if cover["buckets"] else False,
    }


def render_report(
    entries: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    state: dict[str, Any],
    rounds: list[dict[str, Any]],
) -> str:
    status = status_payload(entries, taxonomy, state)
    graph = build_graph(entries)
    top_frontier = frontier(entries, taxonomy, state, limit=15)
    in_degree = graph["in_degree"]
    by_id = {entry["id"]: entry for entry in entries}
    hubs = sorted(in_degree.items(), key=lambda kv: -kv[1])[:12]

    lines: list[str] = []
    lines.append("# Corpus report")
    lines.append("")
    lines.append(f"Generated: {status['generated_at']}")
    lines.append("")
    lines.append(
        f"{status['entries']} entries · {status['pages_mapped']} pages mapped · "
        f"{status['pages_manifest_eligible']} pages manifest-eligible · "
        f"{status['frontier_open']} frontier targets open · {status['rounds_run']} rounds run"
    )
    lines.append("")
    lines.append("## Coverage by bucket")
    lines.append("")
    lines.append("| Bucket | Tier | Target | Mapped | Eligible | Reference-only | Needs review | Frontier | Saturation |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name, row in status["buckets"].items():
        lines.append(
            f"| {name} | {row['tier'] or '—'} | {row['target_pages']} | {row['pages_mapped']} | "
            f"{row['pages_manifest_eligible']} | {row['pages_reference_only']} | {row['pages_needs_review']} | "
            f"{row['frontier_open']} | {row['saturation']} |"
        )
    lines.append("")
    lines.append("## Rights posture")
    lines.append("")
    lines.append("| Use class | Entries |")
    lines.append("|---|---|")
    for use_class, count in status["use_classes"].items():
        lines.append(f"| {use_class} | {count} |")
    lines.append("")
    lines.append("Manifest gate: confirmed rights + evidence URL + check date. Everything else is study-only.")
    lines.append("")
    lines.append("## Form mix")
    lines.append("")
    lines.append("| Form | Entries |")
    lines.append("|---|---|")
    for form, count in status["forms"].items():
        lines.append(f"| {form} | {count} |")
    lines.append("")
    lines.append("## Network")
    lines.append("")
    lines.append(
        f"{status['edges']} internal edges · {status['components']} components "
        f"(largest {status['largest_component']}) · {status['isolated']} isolated · "
        f"{status['bridges']} cross-bucket bridges"
    )
    lines.append("")
    lines.append("### Most-referenced works")
    lines.append("")
    lines.append("| Entry | Bucket | In-degree |")
    lines.append("|---|---|---|")
    for entry_id, degree in hubs:
        if not degree:
            continue
        lines.append(f"| {entry_id} | {by_id[entry_id].get('bucket')} | {degree} |")
    lines.append("")
    lines.append("### Frontier (next scouting targets)")
    lines.append("")
    lines.append("| Target | Bucket | Support | Score |")
    lines.append("|---|---|---|---|")
    for target in top_frontier:
        lines.append(
            f"| {target['label']} | {target.get('suggested_bucket') or '—'} | {target['support']} | {target['score']} |"
        )
    lines.append("")
    if rounds:
        lines.append("## Round history")
        lines.append("")
        lines.append("| Round | Mode | New | Rediscovery | Frontier after | Entries |")
        lines.append("|---|---|---|---|---|---|")
        for record in rounds[-15:]:
            lines.append(
                f"| {record['round']:03d} | {record.get('mode')} | {record.get('new_entries')} | "
                f"{record.get('rediscovery_rate')} | {record.get('unresolved_frontier')} | {record.get('entries_total')} |"
            )
        lines.append("")
    return "\n".join(lines)



# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def self_test() -> dict[str, Any]:
    """Exercise the gates and the merge on adversarial input.

    Everything here is in-memory; nothing touches a corpus on disk.
    """
    checks: list[str] = []

    # Rights derivation: the two gates, in both directions.
    open_confirmed = merge_defaults(
        {
            "id": "x",
            "title": "T",
            "rights": {"status": "cc_by", "confidence": "confirmed", "evidence": "https://e", "checked_at": "2026-01-01"},
        }
    )
    assert derive_rights(open_confirmed)["manifest_eligible"], derive_rights(open_confirmed)
    no_evidence = merge_defaults({"id": "x", "title": "T", "rights": {"status": "cc_by", "confidence": "confirmed"}})
    assert derive_rights(no_evidence)["use_class"] == "needs_review", derive_rights(no_evidence)
    inferred = merge_defaults({"id": "x", "title": "T", "rights": {"status": "public_domain", "confidence": "inferred"}})
    assert derive_rights(inferred)["use_class"] == "needs_review", derive_rights(inferred)
    free_to_read = merge_defaults(
        {"id": "x", "title": "T", "rights": {"status": "author_hosted_free", "confidence": "confirmed", "evidence": "https://e", "checked_at": "2026-01-01"}}
    )
    assert derive_rights(free_to_read)["use_class"] == "reference_only", "free to read is not licensed"
    granted = merge_defaults(
        {
            "id": "x",
            "title": "T",
            "rights": {
                "status": "all_rights_reserved",
                "confidence": "confirmed",
                "evidence": "https://e",
                "checked_at": "2026-01-01",
                "grant": {"type": "written_permission", "evidence": "https://mail"},
            },
        }
    )
    assert derive_rights(granted)["use_class"] == "ingest_licensed", derive_rights(granted)
    hollow_grant = merge_defaults(
        {"id": "x", "title": "T", "rights": {"status": "all_rights_reserved", "confidence": "confirmed", "evidence": "https://e", "checked_at": "2026-01-01", "grant": {"type": "claimed"}}}
    )
    assert derive_rights(hollow_grant)["use_class"] == "reference_only", "a grant without evidence must not upgrade"
    excluded = merge_defaults({"id": "x", "title": "T", "rights": {"status": "proprietary_confidential", "confidence": "confirmed", "evidence": "https://e", "checked_at": "2026-01-01"}})
    assert derive_rights(excluded)["use_class"] == "excluded" and not derive_rights(excluded)["study_ok"]
    checks.append("rights: evidence gate, grant upgrade, hollow grant, free-to-read and exclusion all hold")

    # Dedupe: fuzzy enough to match a short-form citation, strict enough to keep volumes apart.
    assert compatible_titles("Trading and Exchanges", "Trading and Exchanges: Market Microstructure for Practitioners")
    assert not compatible_titles("Probabilistic Machine Learning: An Introduction", "Probabilistic Machine Learning: Advanced Topics")
    assert dedupe_key({"title": "The Theory of X", "authors": ["Jane Q. Doe"]}) == dedupe_key({"title": "Theory of X", "authors": ["Doe, Jane"]})
    checks.append("dedupe: short-form citations match, sibling volumes stay distinct")

    # Unicode and punctuation must not crash normalization.
    weird = merge_defaults({"title": "Étude — Прогноз, 第一版: A Study", "authors": ["Émile Borel"]})
    assert weird["id"] and slugify(weird["title"]), weird["id"]
    checks.append("normalization: unicode, em dashes and CJK survive id generation")

    # Graph: self-refs dropped, unresolved refs become frontier, bridges detected.
    entries = [
        merge_defaults({"id": "a", "title": "A", "bucket": "b1", "priority": 5, "refs": [{"target": "a"}, {"target": "b"}, {"target": "Unmapped Work On Queues", "bucket": "b2"}]}),
        merge_defaults({"id": "b", "title": "B", "bucket": "b2", "refs": [{"target": "Unmapped Work On Queues", "bucket": "b2"}]}),
    ]
    graph = build_graph(entries)
    assert [e["target"] for e in graph["edges"]] == ["b"], graph["edges"]
    assert len(graph["unresolved"]) == 1, graph["unresolved"]
    assert list(graph["unresolved"].values())[0]["supported_by"] == ["a", "b"], "co-citation support must aggregate"
    assert set(graph["bridges"]) == {"a", "b"}, graph["bridges"]
    checks.append("graph: self-references dropped, frontier support aggregates, bridges found")

    taxonomy = {"defaults": {"saturation_dry_rounds": 2}, "buckets": {"b1": {"tier": 1, "target_pages": 100}, "b2": {"tier": 1, "target_pages": 100}}}
    targets = frontier(entries, taxonomy, {"buckets": {}}, limit=5)
    assert targets and targets[0]["support"] == 2, targets
    checks.append("frontier: ranks a doubly-supported target first")

    # Validation must catch the vocabulary and structural errors.
    broken = [
        merge_defaults({"id": "dup", "title": "One", "bucket": "b1", "form": "not_a_form"}),
        merge_defaults({"id": "dup", "title": "Two", "bucket": "nope", "rights": {"status": "invented", "confidence": "confirmed"}}),
        merge_defaults({"id": "u", "title": "Three", "bucket": "b1", "units": [{"unit_id": "z", "topic": "t", "read_status": "invented"}]}),
    ]
    result = validate(broken, taxonomy)
    joined = " | ".join(result["errors"])
    assert not result["ok"]
    for expected in ["duplicate id", "unknown form", "unknown bucket", "unknown rights status", "confirmed without evidence", "unknown read_status"]:
        assert expected in joined, (expected, joined)
    checks.append("validate: duplicate ids, unknown vocabulary and unevidenced confirmations all rejected")

    # Findings merge: dedupe by title, reject untitled, respect the evidence rule.
    store = [merge_defaults({"id": "harris", "title": "Trading and Exchanges: Market Microstructure", "authors": ["Larry Harris"], "bucket": "b1", "pages": 656})]
    incoming = merge_defaults({"title": "Trading and Exchanges", "authors": ["Harris, Larry"], "bucket": "b1", "rights": {"status": "all_rights_reserved", "confidence": "confirmed"}})
    merged, changes = apply_findings_entry(store[0], incoming)
    assert "rights.rejected_no_evidence" in changes, changes
    assert merged["rights"]["confidence"] != "confirmed", merged["rights"]
    checks.append("merge: a confirmation without evidence is refused at the merge boundary")

    # Manifest gate: only confirmed-with-evidence gets in, with a reason for every hold.
    manifest = build_manifest([open_confirmed, free_to_read, inferred, excluded], taxonomy)
    assert manifest["include_count"] == 1 and manifest["hold_count"] == 3, manifest
    assert all(row["reasons"] for row in manifest["hold"]), manifest["hold"]
    checks.append("manifest: one eligible entry, every hold carries a reason")

    # Units and the reading queue.
    with_units = merge_defaults(
        {
            "id": "w",
            "title": "W",
            "bucket": "b1",
            "pages": 300,
            "units": [
                {"unit_id": "u1", "topic": "the useful chapter", "pages": 40, "priority": 5},
                {"unit_id": "u2", "topic": "already done", "pages": 40, "read_status": "compiled"},
                # Priority 5 and located, so it outscores u1 on every term. If reading
                # did not remove a unit, this would head the queue forever.
                {"unit_id": "u3", "topic": "opened, not yet compiled", "pages": 40,
                 "priority": 5, "locator": "pp. 1-40", "read_status": "read"},
            ],
        }
    )
    queue = reading_queue([with_units], taxonomy, {"buckets": {}}, limit=10)
    assert [row["unit_id"] for row in queue] == ["u1"], queue
    assert queue[0]["action"] == "map_first", queue
    assert entry_units(merge_defaults({"id": "n", "title": "N", "pages": 10}))[0]["unit_id"] == "whole"
    checks.append("units: read, compiled and abandoned units leave the reading queue; undecomposed sources fall back to one whole unit")

    # Units are a reading round's entire payload, and they were silently dropped once.
    stored = merge_defaults({"id": "u", "title": "T",
                             "units": [{"unit_id": "ch1", "topic": "a", "read_status": "unread"}],
                             "acquisition": {"state": "owned", "copy_path": "/tmp/u.pdf"}})
    reading = {"id": "u",
               "units": [{"unit_id": "ch1", "read_status": "read", "locator": "pp. 3-9"},
                         {"unit_id": "ch2", "topic": "b", "read_status": "read"}],
               "_stated": {"id", "units"}, "_stated_nested": {}}
    merged_units, unit_changes = apply_findings_entry(stored, reading)
    by_id = {u["unit_id"]: u for u in merged_units["units"]}
    assert by_id["ch1"]["read_status"] == "read" and by_id["ch1"]["locator"] == "pp. 3-9", by_id["ch1"]
    assert by_id["ch2"]["read_status"] == "read", "a new unit must be added, not ignored"
    assert any(c.startswith("units.") for c in unit_changes), unit_changes
    # A finding that says nothing about acquisition must not reset it to the default.
    assert merged_units["acquisition"]["state"] == "owned", merged_units["acquisition"]
    assert merged_units["acquisition"]["copy_path"] == "/tmp/u.pdf"
    # read_status may advance and must not regress.
    regressed, _ = apply_findings_entry(merged_units,
                                        {"id": "u", "units": [{"unit_id": "ch1", "read_status": "unread"}],
                                         "_stated": {"id", "units"}, "_stated_nested": {}})
    assert {u["unit_id"]: u["read_status"] for u in regressed["units"]}["ch1"] == "read", \
        "a scout who did not open it must not be able to un-read it"
    checks.append("merge: units merge by unit_id, read_status advances but never regresses, and an unmentioned field is not reset to its default")

    return {"ok": True, "checks": checks}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def resolve_corpus_dir(args: argparse.Namespace) -> Path:
    if args.corpus_dir:
        return args.corpus_dir.resolve()
    return (args.lab_dir / "corpus").resolve()


def cmd_init(paths: dict[str, Path], args: argparse.Namespace) -> int:
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["rounds"].mkdir(parents=True, exist_ok=True)
    if not paths["bibliography"].exists():
        write_yaml(paths["bibliography"], {"updated_at": now_iso(), "entries": []})
    if not paths["taxonomy"].exists():
        write_yaml(
            paths["taxonomy"],
            {
                "defaults": {"saturation_dry_rounds": 2, "round_limit": 25},
                "buckets": {
                    "example_bucket": {
                        "tier": 1,
                        "target_pages": 10000,
                        "description": "Replace with your own buckets.",
                    }
                },
            },
        )
    state = load_state(paths)
    state.setdefault("created_at", now_iso())
    save_state(paths, state)
    print(json.dumps({"corpus_dir": str(paths["root"]), "entries": len(load_bibliography(paths))}, indent=2))
    return 0


def cmd_validate(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    result = validate(entries, load_taxonomy(paths))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_status(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    taxonomy = load_taxonomy(paths)
    state = load_state(paths)
    payload = status_payload(entries, taxonomy, state)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print(f"corpus: {paths['root']}")
    print(
        f"  entries={payload['entries']} pages_mapped={payload['pages_mapped']} "
        f"eligible={payload['pages_manifest_eligible']} target={payload['target_pages']}"
    )
    print(
        f"  network: edges={payload['edges']} components={payload['components']} "
        f"bridges={payload['bridges']} isolated={payload['isolated']} frontier={payload['frontier_open']}"
    )
    print(f"  rounds_run={payload['rounds_run']} open={len(payload['open_rounds'])}")
    print(
        f"  reading: {payload['sources_decomposed']}/{payload['entries']} sources decomposed into "
        f"{payload['units_declared']} units ({payload['unit_pages_mapped']} pages targeted) "
        + (", ".join(f"{k}={v}" for k, v in payload["unit_states"].items()) or "none read")
    )
    if payload["units_awaiting_compile"]:
        print(f"  awaiting compile: {payload['units_awaiting_compile']} units read but not yet compiled")
    print("  buckets:")
    for name, row in payload["buckets"].items():
        print(
            f"    {name:<28} mapped={row['pages_mapped']:>6}/{row['target_pages']:<6} "
            f"eligible={row['pages_manifest_eligible']:>6} frontier={row['frontier_open']:>3} {row['saturation']}"
        )
    print("  use classes: " + ", ".join(f"{k}={v}" for k, v in payload["use_classes"].items()))
    return 0


def cmd_reading(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    rows = reading_queue(
        entries,
        load_taxonomy(paths),
        load_state(paths),
        bucket=args.bucket,
        limit=args.limit,
        include_unmapped=args.include_unmapped,
    )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        locator = row["locator"] or "not located"
        print(f"{row['score']:>6}  [{row['action']:<17}] {row['entry_id']}/{row['unit_id']}  ({locator}, {row['read_status']})")
        print(f"          {row['topic']}")
    if not rows:
        print("no reading units; decompose a source first (add `units:` to its entry)")
    return 0


def cmd_frontier(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    targets = frontier(entries, load_taxonomy(paths), load_state(paths), bucket=args.bucket, limit=args.limit)
    if args.json:
        print(json.dumps(targets, indent=2))
        return 0
    for target in targets:
        flag = " [bridge]" if target["cross_bucket"] else ""
        print(f"{target['score']:>6}  {target.get('suggested_bucket') or '—':<24} {target['label']}{flag}")
        print(f"        support={target['support']} via {', '.join(target['supported_by'][:4])}")
    if not targets:
        print("frontier empty for this selection")
    return 0


def cmd_round(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    taxonomy = load_taxonomy(paths)
    state = load_state(paths)

    if args.round_command == "list":
        rounds = load_jsonl(paths["log"])
        print(json.dumps({"closed": rounds, "open": state.get("open_rounds", [])}, indent=2))
        return 0

    if args.round_command == "open":
        limit = args.limit or int((taxonomy.get("defaults") or {}).get("round_limit") or 25)
        request = open_round(paths, entries, taxonomy, state, args.mode, args.bucket or [], limit)
        print(
            json.dumps(
                {
                    "round": request["round"],
                    "mode": request["mode"],
                    "targets": len(request["targets"]),
                    "request_md": str(round_dir(paths, request["round"]) / "request.md"),
                    "findings": request["findings_path"],
                },
                indent=2,
            )
        )
        return 0

    number = args.round or int(state.get("round_counter") or 0)
    if not number:
        raise SystemExit("ERROR: no round to close")
    report = close_round(paths, entries, taxonomy, state, number, args.findings)
    print(
        json.dumps(
            {
                "round": report["round"],
                "new_entries": report["new_entries"],
                "updated": len(report["updated"]),
                "rejected": len(report["rejected"]),
                "frontier_resolved": len(report["resolved_frontier"]),
                "rights_confirmed_delta": report["rights_confirmed_delta"],
                "eligible_pages_delta": report["eligible_pages_delta"],
                "rediscovery_rate": report["rediscovery_rate"],
                "frontier_open": report["unresolved_frontier"],
                "entries_total": report["entries_total"],
            },
            indent=2,
        )
    )
    return 0


def cmd_rights(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    if args.verify_queue:
        queue = verify_queue(entries, limit=args.limit, bucket=args.bucket)
        if args.json:
            print(json.dumps(queue, indent=2))
            return 0
        for row in queue:
            print(f"{row['score']:>7}  {row['id']}  (upside {row['upside']})")
            print(f"         {row['rights_status']}/{row['rights_confidence']} — {'; '.join(row['blockers']) or 'unverified'}")
        if not queue:
            print("verification queue empty")
        return 0

    rows = []
    for entry in entries:
        if args.bucket and entry.get("bucket") != args.bucket:
            continue
        derived = derive_rights(entry)
        rows.append({"id": entry["id"], "form": entry.get("form"), **derived})
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for row in rows:
        print(f"{row['use_class']:<22} {row['status']:<28} {row['confidence']:<10} {row['id']}")
    return 0


def cmd_manifest(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    manifest = build_manifest(entries, load_taxonomy(paths))
    out = args.out or paths["manifest"]
    write_json(out, manifest)
    print(
        json.dumps(
            {
                "manifest": str(out),
                "include": manifest["include_count"],
                "include_pages": manifest["include_pages"],
                "hold": manifest["hold_count"],
                "by_use_class": manifest["by_use_class"],
            },
            indent=2,
        )
    )
    return 0


def cmd_graph(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    graph = build_graph(entries)
    payload = {
        "generated_at": now_iso(),
        "nodes": [
            {
                "id": entry["id"],
                "bucket": entry.get("bucket"),
                "form": entry.get("form"),
                "priority": entry.get("priority"),
                "pages": entry.get("pages"),
                "use_class": derive_rights(entry)["use_class"],
                "in_degree": graph["in_degree"].get(entry["id"], 0),
                "out_degree": graph["out_degree"].get(entry["id"], 0),
                "bridges": graph["bridges"].get(entry["id"], []),
            }
            for entry in entries
        ],
        "edges": graph["edges"],
        "unresolved": sorted(graph["unresolved"].values(), key=lambda n: -len(n["supported_by"])),
        "components": graph["components"],
        "isolated": graph["isolated"],
    }
    out = args.out or paths["graph"]
    write_json(out, payload)
    print(
        json.dumps(
            {
                "graph": str(out),
                "nodes": len(payload["nodes"]),
                "edges": len(payload["edges"]),
                "unresolved": len(payload["unresolved"]),
                "components": len(payload["components"]),
            },
            indent=2,
        )
    )
    return 0


def cmd_report(paths: dict[str, Path], args: argparse.Namespace) -> int:
    entries = load_bibliography(paths)
    rounds = load_jsonl(paths["log"])
    markdown = render_report(entries, load_taxonomy(paths), load_state(paths), rounds)
    out = args.out or paths["report"]
    write_text(out, markdown + "\n")
    print(json.dumps({"report": str(out), "entries": len(entries)}, indent=2))
    return 0


def cmd_vocab(paths: dict[str, Path], args: argparse.Namespace) -> int:
    payload = {
        "forms": FORMS,
        "rights_status": {name: spec for name, spec in RIGHTS_STATUS.items()},
        "rights_confidence": RIGHTS_CONFIDENCE,
        "acquisition_states": ACQUISITION_STATES,
        "entry_status": ENTRY_STATUS,
        "ingest_use_classes": sorted(INGEST_CLASSES),
        "manifest_gate": "confidence == confirmed AND evidence AND checked_at",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("forms:")
    for name, description in FORMS.items():
        print(f"  {name:<20} {description}")
    print("\nrights status -> use class:")
    for name, spec in RIGHTS_STATUS.items():
        print(f"  {name:<28} {spec['use_class']:<22} {spec['note']}")
    print("\nmanifest gate: " + payload["manifest_gate"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Corpus bibliography network, rounds, and rights tagging")
    parser.add_argument("--lab-dir", type=Path, default=Path.cwd(), help="Lab root. The corpus lives in <lab>/corpus.")
    parser.add_argument("--corpus-dir", type=Path, default=None, help="Corpus directory override.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the corpus workspace.")

    validate_cmd = sub.add_parser("validate", help="Validate the bibliography against the vocabularies.")
    validate_cmd.add_argument("--json", action="store_true")

    status_cmd = sub.add_parser("status", help="Coverage, rights posture, network shape, saturation.")
    status_cmd.add_argument("--json", action="store_true")

    frontier_cmd = sub.add_parser("frontier", help="Rank the next scouting targets.")
    frontier_cmd.add_argument("--bucket", default=None)
    frontier_cmd.add_argument("--limit", type=int, default=25)
    frontier_cmd.add_argument("--json", action="store_true")

    round_cmd = sub.add_parser("round", help="Open or close an iterative scouting round.")
    round_sub = round_cmd.add_subparsers(dest="round_command", required=True)
    round_open = round_sub.add_parser("open")
    round_open.add_argument("--mode", choices=ROUND_MODES, default="expand")
    round_open.add_argument("--bucket", action="append", default=None)
    round_open.add_argument("--limit", type=int, default=None)
    round_close = round_sub.add_parser("close")
    round_close.add_argument("--round", type=int, default=None)
    round_close.add_argument("--findings", type=Path, default=None)
    round_sub.add_parser("list")

    reading_cmd = sub.add_parser("reading", help="Chapter-level reading queue across decomposed sources.")
    reading_cmd.add_argument("--bucket", default=None)
    reading_cmd.add_argument("--limit", type=int, default=25)
    reading_cmd.add_argument("--include-unmapped", action="store_true", help="Also surface sources that have not been decomposed yet.")
    reading_cmd.add_argument("--json", action="store_true")

    rights_cmd = sub.add_parser("rights", help="Rights report and verification queue.")
    rights_cmd.add_argument("--verify-queue", action="store_true")
    rights_cmd.add_argument("--bucket", default=None)
    rights_cmd.add_argument("--limit", type=int, default=25)
    rights_cmd.add_argument("--json", action="store_true")

    manifest_cmd = sub.add_parser("manifest", help="Emit the rights-gated build manifest.")
    manifest_cmd.add_argument("--out", type=Path, default=None)

    graph_cmd = sub.add_parser("graph", help="Export the bibliography network.")
    graph_cmd.add_argument("--out", type=Path, default=None)

    report_cmd = sub.add_parser("report", help="Write the markdown corpus report.")
    report_cmd.add_argument("--out", type=Path, default=None)

    vocab_cmd = sub.add_parser("vocab", help="Print the form and rights vocabularies.")
    vocab_cmd.add_argument("--json", action="store_true")

    sub.add_parser("self-test", help="Exercise the rights, dedupe, graph, merge and unit logic on adversarial input.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "self-test":
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    paths = corpus_paths(resolve_corpus_dir(args))

    if args.command != "init" and not paths["bibliography"].exists():
        raise SystemExit(f"ERROR: no bibliography at {paths['bibliography']}. Run `corpus init` first.")

    handlers = {
        "init": cmd_init,
        "validate": cmd_validate,
        "status": cmd_status,
        "frontier": cmd_frontier,
        "reading": cmd_reading,
        "round": cmd_round,
        "rights": cmd_rights,
        "manifest": cmd_manifest,
        "graph": cmd_graph,
        "report": cmd_report,
        "vocab": cmd_vocab,
    }
    return handlers[args.command](paths, args)


if __name__ == "__main__":
    raise SystemExit(main())
