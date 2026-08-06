#!/usr/bin/env python3
"""Export the corpus and knowledge store as one JSON bundle for the explorer.

The web app is a reader, not a second source of truth. Everything it shows is
computed here from the same functions the CLI uses, so a number on screen and a
number from `knowledge.py assess` cannot drift apart.

    python scripts/export_web.py --lab corpus-lab --out web/public/corpus.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus as corpus_engine  # noqa: E402
import knowledge as knowledge_engine  # noqa: E402


def build(lab_root: Path) -> dict[str, Any]:
    corpus_paths = corpus_engine.corpus_paths(lab_root / "corpus")
    entries = corpus_engine.load_bibliography(corpus_paths)
    taxonomy = corpus_engine.load_taxonomy(corpus_paths)
    state = corpus_engine.load_state(corpus_paths)

    knowledge_paths = knowledge_engine.knowledge_paths(lab_root / "knowledge")
    store = knowledge_engine.load_store(knowledge_paths)
    sources = knowledge_engine.load_corpus_sources(lab_root)

    graph = corpus_engine.build_graph(entries)
    assessment = knowledge_engine.assess(store, sources)
    coverage = corpus_engine.coverage(entries, taxonomy, state)
    opened = knowledge_engine.read_units(sources)

    held: set[str] = set()
    for base in (lab_root / "corpus" / "study", lab_root / "corpus" / "sources"):
        if base.exists():
            held |= {p.stem for p in base.glob("*.pdf")}
            held |= {p.name for p in base.iterdir() if p.is_dir()}

    # Entries, flattened to what the explorer actually renders.
    slim_entries = []
    for entry in entries:
        rights = corpus_engine.derive_rights(entry)
        units = corpus_engine.entry_units(entry)
        slim_entries.append({
            "id": entry["id"],
            "title": entry.get("title"),
            "authors": entry.get("authors") or [],
            "year": entry.get("year"),
            "bucket": entry.get("bucket"),
            "form": entry.get("form"),
            "venue": entry.get("venue"),
            "pages": entry.get("pages"),
            "priority": entry.get("priority"),
            "tags": entry.get("tags") or [],
            "notes": entry.get("notes"),
            "workstream": entry.get("workstream"),
            "doi": (entry.get("identifiers") or {}).get("doi"),
            "url": (entry.get("identifiers") or {}).get("url"),
            "rights": {
                "status": rights["status"],
                "confidence": rights["confidence"],
                "use_class": rights["use_class"],
                "evidence": (entry.get("rights") or {}).get("evidence"),
            },
            "held": entry["id"] in held,
            "units": [
                {
                    "unit_id": unit.get("unit_id"),
                    "topic": unit.get("topic"),
                    "locator": unit.get("locator"),
                    "pages": corpus_engine.unit_pages(unit, entry),
                    "read_status": unit.get("read_status"),
                    "notes": unit.get("notes"),
                }
                for unit in units
                if unit.get("unit_id") != "whole"
            ],
            "refs": [corpus_engine.parse_ref(r) for r in (entry.get("refs") or [])],
        })

    # Concepts, with their resolved relationships and grounding.
    def grounded(concept: dict[str, Any]) -> list[str]:
        hits = []
        for raw in concept.get("source_passage_ids") or []:
            ref = knowledge_engine.parse_passage_ref(raw)
            key = f"{ref['source_id']}#{ref['anchor']}" if ref.get("anchor") else ref["source_id"]
            if key in opened:
                hits.append(key)
        return hits

    concept_rows = []
    method_by_concept: dict[str, list[str]] = {}
    for binding in store.get("methods") or []:
        for cid in binding.get("concept_ids") or []:
            method_by_concept.setdefault(cid, []).append(binding["method_id"])

    for concept in store.get("concepts") or []:
        anchors = []
        for raw in concept.get("source_passage_ids") or []:
            ref = knowledge_engine.parse_passage_ref(raw)
            key = f"{ref['source_id']}#{ref['anchor']}" if ref.get("anchor") else ref["source_id"]
            anchors.append({"key": key, "source_id": ref["source_id"], "anchor": ref.get("anchor"),
                            "read": key in opened})
        concept_rows.append({
            "id": concept["concept_id"],
            "name": concept.get("canonical_name"),
            "plain": concept.get("plain_description"),
            "mechanism": concept.get("mechanism"),
            "equations": concept.get("formal_equations"),
            "assumptions": concept.get("assumptions") or [],
            "failure_modes": concept.get("known_failure_modes") or [],
            "alternatives": concept.get("alternative_explanations") or [],
            "signature": concept.get("expected_empirical_signature"),
            "markets": concept.get("market_types") or [],
            "horizons": concept.get("relevant_horizons") or [],
            "observables": concept.get("required_observables") or [],
            "problems": concept.get("problem_ids") or [],
            "contradicts": concept.get("contradicting_concept_ids") or [],
            "supports": concept.get("supporting_concept_ids") or [],
            "status": concept.get("implementation_status"),
            "confidence": concept.get("confidence"),
            "workstream": concept.get("workstream") or "cross_cutting",
            "tags": concept.get("tags") or [],
            "anchors": anchors,
            "grounded": bool(grounded(concept)),
            "methods": sorted(method_by_concept.get(concept["concept_id"], [])),
        })

    return {
        "generated_from": str(lab_root),
        "counts": {
            "entries": len(entries),
            "concepts": len(concept_rows),
            "methods": len(store.get("methods") or []),
            "hypotheses": len(store.get("hypotheses") or []),
            "decisions": len(store.get("decisions") or []),
            "problems": len(store.get("problems") or []),
            "units": sum(len(e["units"]) for e in slim_entries),
            "units_read": sum(1 for e in slim_entries for u in e["units"]
                              if u["read_status"] in {"read", "compiled"}),
            "held": sum(1 for e in slim_entries if e["held"]),
        },
        "entries": slim_entries,
        "concepts": concept_rows,
        "problems": store.get("problems") or [],
        "methods": store.get("methods") or [],
        "hypotheses": store.get("hypotheses") or [],
        "decisions": store.get("decisions") or [],
        "bets": store.get("bets") or [],
        "extensions": store.get("extensions") or [],
        "assessment": assessment,
        "buckets": {
            name: {
                "target_pages": row.get("target_pages"),
                "pages_mapped": row.get("pages_mapped"),
                "entries": row.get("entries"),
                "label": (taxonomy.get("buckets", {}).get(name) or {}).get("label"),
            }
            for name, row in coverage["buckets"].items()
        },
        "graph": {
            # Nodes come from the bibliography, not the graph: an entry with no edges
            # is still a node, and dropping the isolated ones would hide 56 of them.
            "nodes": [
                {
                    "id": entry["id"],
                    "bucket": entry["bucket"],
                    "priority": entry["priority"],
                    "title": entry["title"],
                    "held": entry["held"],
                    "degree": graph["in_degree"].get(entry["id"], 0) + graph["out_degree"].get(entry["id"], 0),
                    # A bridge entry is cited from more than one bucket: the transfer edge.
                    "bridges": graph["bridges"].get(entry["id"], []),
                }
                for entry in slim_entries
            ],
            "edges": [{"source": e["source"], "target": e["target"], "relation": e.get("relation")}
                      for e in graph["edges"] if e.get("source") and e.get("target")],
            "components": len(graph.get("components", [])),
            "isolated": graph.get("isolated", []),
            "unresolved": len(graph.get("unresolved", {})),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the corpus as JSON for the explorer")
    parser.add_argument("--lab", default="corpus-lab", help="lab root holding corpus/ and knowledge/")
    parser.add_argument("--out", default="web/public/corpus.json")
    args = parser.parse_args(argv)

    lab_root = Path(args.lab).resolve()
    if not (lab_root / "corpus" / "bibliography.yaml").exists():
        raise SystemExit(f"ERROR: no corpus at {lab_root}. Scaffold a lab first with scripts/new_lab.py.")

    bundle = build(lab_root)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=None, separators=(",", ":")))
    size = out.stat().st_size
    print(json.dumps({
        "out": str(out),
        "kilobytes": round(size / 1024, 1),
        **bundle["counts"],
        "contradiction_clusters": len(bundle["assessment"]["contradiction"]["clusters"]),
        "graph_nodes": len(bundle["graph"]["nodes"]),
        "graph_edges": len(bundle["graph"]["edges"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
