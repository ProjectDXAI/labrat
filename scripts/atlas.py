#!/usr/bin/env python3
"""One browsable map of everything: what we claim, what it rests on, what we hold.

The store is six YAML files, a passage index, and a bibliography. That is the right shape
for editing and the wrong shape for orienting, whether the reader is a person opening the
project after a month or an agent deciding where to start. This writes the flat views.

Two formats, because they answer different questions.

`MAP.md` is one file to read start to finish. It is self-describing, so an agent that has
never seen this project can read it once and know what exists, what is grounded, what is
contested, and what is missing. That is usually the one you want.

The CSVs are for filtering. `concepts.csv`, `sources.csv`, `units.csv` and `chains.csv`
are flat, one row per thing, no nesting -- greppable, sortable, and loadable into anything
without a YAML parser. Use them when you know what you are looking for.

Both are generated. Neither is a source of truth: edit the YAML, regenerate these.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus as corpus_engine  # noqa: E402
import digest as digest_engine  # noqa: E402
import knowledge as knowledge_engine  # noqa: E402


def gather(lab_root: Path) -> dict[str, Any]:
    corpus_dir = lab_root / "corpus"
    paths = corpus_engine.corpus_paths(corpus_dir)
    entries = corpus_engine.load_bibliography(paths)
    store = knowledge_engine.load_store(knowledge_engine.knowledge_paths(lab_root / "knowledge"))
    sources = knowledge_engine.load_corpus_sources(lab_root)
    assessment = knowledge_engine.assess(store, sources)
    passages = digest_engine.load_passages(corpus_dir)
    opened = knowledge_engine.read_units(sources)

    by_id = {e["id"]: e for e in entries}
    unearned = {r["concept_id"] for r in assessment["high_confidence_on_unread"]}
    contested = {c for cl in assessment["contradiction"]["clusters"] for c in cl}
    methods_for: dict[str, list[str]] = {}
    for binding in store.get("methods") or []:
        for cid in binding.get("concept_ids") or []:
            methods_for.setdefault(cid, []).append(binding["method_id"])

    concepts = []
    for c in store.get("concepts") or []:
        anchors = []
        for raw in c.get("source_passage_ids") or []:
            ref = knowledge_engine.parse_passage_ref(raw)
            key = f"{ref['source_id']}#{ref['anchor']}" if ref.get("anchor") else ref["source_id"]
            anchors.append({
                "key": key,
                "source_id": ref["source_id"],
                "read": key in opened,
                "held": bool(passages.get(ref["source_id"])),
            })
        concepts.append({
            "id": c["concept_id"],
            "name": c.get("canonical_name"),
            "plain": c.get("plain_description"),
            "workstream": c.get("workstream") or "cross_cutting",
            "status": c.get("implementation_status"),
            "confidence": c.get("confidence"),
            "problems": c.get("problem_ids") or [],
            "contradicts": c.get("contradicting_concept_ids") or [],
            "methods": sorted(methods_for.get(c["concept_id"], [])),
            "anchors": anchors,
            "grounded": any(a["read"] for a in anchors),
            "unearned": c["concept_id"] in unearned,
            "contested": c["concept_id"] in contested,
        })
    concepts.sort(key=lambda r: (-(r["confidence"] or 0), r["id"]))

    units = []
    for e in entries:
        for u in corpus_engine.entry_units(e):
            if u.get("unit_id") == "whole":
                continue
            units.append({
                "source_id": e["id"],
                "unit_id": u["unit_id"],
                "topic": u.get("topic"),
                "locator": u.get("locator"),
                "read": u.get("read_status") in {"read", "compiled"},
                "held": bool(passages.get(e["id"])),
                "has_note": bool(u.get("notes")),
            })

    source_rows = []
    for e in entries:
        pages_held = len(passages.get(e["id"]) or [])
        e_units = [u for u in units if u["source_id"] == e["id"]]
        source_rows.append({
            "id": e["id"],
            "title": e.get("title"),
            "authors": "; ".join(e.get("authors") or []),
            "year": e.get("year"),
            "bucket": e.get("bucket"),
            "form": e.get("form"),
            "pages": e.get("pages"),
            "priority": e.get("priority"),
            "pages_held": pages_held,
            "held": bool(pages_held),
            "needs_ocr": "needs-ocr" in (e.get("tags") or []),
            "units": len(e_units),
            "units_read": sum(1 for u in e_units if u["read"]),
        })
    source_rows.sort(key=lambda r: (r["bucket"] or "", -(r["priority"] or 0), r["id"]))

    return {
        "concepts": concepts,
        "sources": source_rows,
        "units": units,
        "chains": assessment["chains"],
        "problems": store.get("problems") or [],
        "assessment": assessment,
        "buckets": corpus_engine.coverage(entries, corpus_engine.load_taxonomy(paths),
                                          corpus_engine.load_state(paths))["buckets"],
        "by_id": by_id,
    }


def write_csvs(data: dict[str, Any], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def dump(name: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
        path = out_dir / name
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        written.append(path)

    dump("concepts.csv", [
        {**c,
         "anchors": " ".join(a["key"] for a in c["anchors"]),
         "anchors_read": sum(1 for a in c["anchors"] if a["read"]),
         "anchors_held": sum(1 for a in c["anchors"] if a["held"]),
         "problems": " ".join(c["problems"]),
         "contradicts": " ".join(c["contradicts"]),
         "methods": " ".join(c["methods"]),
         "plain": (c["plain"] or "").replace("\n", " ")}
        for c in data["concepts"]
    ], ["id", "name", "workstream", "status", "confidence", "grounded", "unearned", "contested",
        "problems", "contradicts", "methods", "anchors_read", "anchors_held", "anchors", "plain"])

    dump("sources.csv", data["sources"],
         ["id", "title", "authors", "year", "bucket", "form", "pages", "priority",
          "held", "pages_held", "needs_ocr", "units", "units_read"])

    dump("units.csv", data["units"],
         ["source_id", "unit_id", "topic", "locator", "read", "held", "has_note"])

    dump("chains.csv", [
        {**row, "complete_chains": " ".join(row.get("complete_chains") or [])}
        for row in data["chains"]
    ], ["problem_id", "workstream", "weight", "concepts", "with_method", "with_hypothesis",
        "with_decision_card", "complete_chains"])
    return written


def write_map(data: dict[str, Any], path: Path) -> None:
    a = data["assessment"]
    held = [s for s in data["sources"] if s["held"]]
    read_units = [u for u in data["units"] if u["read"]]
    lines: list[str] = []
    add = lines.append

    add("# Corpus map")
    add("")
    add("Generated by `scripts/atlas.py`. Every number here is computed from the same")
    add("functions the CLI uses. Edit the YAML in `knowledge/` and `corpus/`, then regenerate.")
    add("")
    add("## What exists")
    add("")
    add(f"- **{len(data['sources'])} sources** catalogued, **{len(held)} held** with extracted text "
        f"({sum(s['pages_held'] for s in held):,} pages)")
    add(f"- **{len(data['concepts'])} concept cards**, {sum(1 for c in data['concepts'] if c['grounded'])} "
        f"resting on a unit someone opened")
    add(f"- **{len(data['units'])} reading units**, {len(read_units)} read")
    add(f"- **{len(data['problems'])} problems**, {len(a['complete_chain_problems'])} with a complete "
        f"chain to a decision")
    add(f"- **{len(a['contradiction']['clusters'])} contradiction clusters** across "
        f"{a['contradiction']['concepts_in_a_contradiction']} cards")
    add("")

    add("## Read this first: what cannot be acted on")
    add("")
    broken = [r for r in data["chains"] if not r["complete_chains"]]
    if broken:
        add("A problem is served only when one card covering it has a bound method, a hypothesis,")
        add("and a decision card together. These have the parts and no card carrying all of them:")
        add("")
        for row in broken:
            add(f"- **{row['problem_id']}** — {row['concepts']} cards, {row['with_method']} with a method, "
                f"{row['with_hypothesis']} with a hypothesis, {row['with_decision_card']} with a decision card")
        add("")
    if a["high_confidence_on_unread"]:
        add(f"{len(a['high_confidence_on_unread'])} cards hold confidence at or above 0.6 on an anchor")
        add("nobody opened. Not evidence they are wrong; evidence the confidence is a memory of the")
        add("literature rather than a reading of it:")
        add("")
        for row in a["high_confidence_on_unread"][:10]:
            add(f"- `{row['concept_id']}` at {row['confidence']:.2f} — {row['name']}")
        add("")

    add("## Concepts")
    add("")
    add("| id | name | conf | grounded | flags | problems |")
    add("| --- | --- | ---: | :---: | --- | --- |")
    for c in data["concepts"]:
        flags = []
        if c["contested"]:
            flags.append("contested")
        if c["unearned"]:
            flags.append("unearned")
        if not c["methods"]:
            flags.append("no-method")
        add(f"| `{c['id']}` | {c['name']} | {c['confidence'] or ''} | "
            f"{'yes' if c['grounded'] else 'no'} | {', '.join(flags) or '—'} | "
            f"{', '.join(c['problems']) or '—'} |")
    add("")

    add("## Contradictions")
    add("")
    add("Each cluster is a question with two defensible answers, not a defect.")
    add("")
    names = {c["id"]: c["name"] for c in data["concepts"]}
    for cluster in a["contradiction"]["clusters"]:
        add(f"- {' ↔ '.join(f'`{cid}`' for cid in cluster)}")
        for cid in cluster:
            add(f"  - {names.get(cid, '?')}")
    add("")

    add("## Sources by bucket")
    add("")
    add("| bucket | entries | held | pages held | units read |")
    add("| --- | ---: | ---: | ---: | ---: |")
    buckets: dict[str, list[dict[str, Any]]] = {}
    for s in data["sources"]:
        buckets.setdefault(s["bucket"] or "unfiled", []).append(s)
    for name in sorted(buckets):
        rows = buckets[name]
        h = [r for r in rows if r["held"]]
        add(f"| {name} | {len(rows)} | {len(h)} | {sum(r['pages_held'] for r in h):,} | "
            f"{sum(r['units_read'] for r in rows)}/{sum(r['units'] for r in rows)} |")
    add("")

    ocr = [s for s in data["sources"] if s["needs_ocr"]]
    if ocr:
        add("## Held but not readable")
        add("")
        add("We have the file and it has no text layer. Different problem from not having it.")
        add("")
        for s in ocr:
            add(f"- `{s['id']}` — {s['title']} ({s['pages']}pp)")
        add("")

    add("## Every held source")
    add("")
    add("| id | title | bucket | pages held | units read |")
    add("| --- | --- | --- | ---: | ---: |")
    for s in sorted(held, key=lambda r: -r["pages_held"]):
        add(f"| `{s['id']}` | {s['title']} | {s['bucket']} | {s['pages_held']:,} | "
            f"{s['units_read']}/{s['units']} |")
    add("")
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the flat browsable map of the corpus and store")
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--out", default="corpus-lab/map", type=Path)
    args = parser.parse_args(argv)

    data = gather(args.lab.resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    write_map(data, args.out / "MAP.md")
    written = write_csvs(data, args.out)
    print(json.dumps({
        "map": str(args.out / "MAP.md"),
        "csvs": [p.name for p in written],
        "concepts": len(data["concepts"]),
        "sources": len(data["sources"]),
        "held": sum(1 for s in data["sources"] if s["held"]),
        "units": len(data["units"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
