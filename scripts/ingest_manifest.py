#!/usr/bin/env python3
"""Turn an acquisition manifest into bibliography entries.

The research agents return a YAML list per batch with metadata and, where one exists, a
legitimate free-access location. This maps that onto entries and refuses to invent
anything the manifest did not establish.

Two rules the mapping exists to enforce.

Nothing is marked owned. A manifest entry is something we have located, not something we
hold, and the difference is the whole point of the acquisition list. State is `open_url`
when a legitimate free copy was found and `purchasable` otherwise.

`free_access: none` means no legitimate free full text was found, not that none exists.
It records the search, so the entry says `licensed_purchase_required` and stops there
rather than reaching for a copy from somewhere else.

Fields the agent marked `uncertain` are carried into the entry notes verbatim, because a
page count someone was unsure about should not read as measured once it is in YAML.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus as corpus_engine  # noqa: E402

FREE_TO_RIGHTS = {
    "arxiv": "author_hosted_free",
    "author_hosted_pdf": "author_hosted_free",
    "preprint": "author_hosted_free",
    "publisher_open_access": "open_license_other",
    "public_docs": "public_but_restricted",
    "sample_chapters": "licensed_purchase_required",
    "none": "licensed_purchase_required",
}

FREE_TO_STATE = {
    "arxiv": "open_url",
    "author_hosted_pdf": "open_url",
    "preprint": "open_url",
    "publisher_open_access": "open_url",
    "public_docs": "open_url",
    "sample_chapters": "purchasable",
    "none": "purchasable",
}


def to_entry(row: dict[str, Any], bucket: str, today: str, priority: int) -> dict[str, Any]:
    free = (row.get("free_access") or "none").strip()
    rights_status = FREE_TO_RIGHTS.get(free, "unknown")
    state = FREE_TO_STATE.get(free, "not_acquired")

    uncertain = row.get("uncertain") or []
    note_parts = []
    if uncertain:
        note_parts.append("Manifest uncertain about: " + ", ".join(str(u) for u in uncertain) + ".")
    if free == "sample_chapters":
        note_parts.append("Only sample chapters are free; the full text is a purchase.")
    if free == "none":
        note_parts.append("No legitimate free full text found. Purchase or library.")

    form = row.get("form")
    if not form:
        form = "paper" if (row.get("arxiv_id") or row.get("venue")) and not row.get("publisher") else "textbook"

    return {
        "id": row["suggested_id"],
        "title": row["title"],
        "authors": row.get("authors") or [],
        "year": row.get("year"),
        "bucket": bucket,
        "form": form,
        "venue": row.get("publisher") or row.get("venue"),
        "identifiers": {
            "isbn": row.get("isbn"),
            "doi": row.get("doi"),
            "url": row.get("url"),
        },
        "pages": row.get("pages"),
        "density": "high",
        "priority": priority,
        "rights": {
            "status": rights_status,
            "confidence": "inferred",
            "evidence": row.get("free_url") or row.get("url"),
            "checked_at": today,
            "grant": None,
            "notes": None,
        },
        "acquisition": {
            "state": state,
            "copy_path": None,
            "source_url": row.get("free_url") or row.get("url"),
            "obtained_at": None,
            "note": " ".join(note_parts) or None,
        },
        "units": [],
        "refs": [],
        "discovered": {"round": 0, "method": "acquisition_manifest", "source": "research agent"},
        "status": "candidate",
        "tags": [],
        "notes": row.get("one_line"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add an acquisition manifest to the bibliography")
    parser.add_argument("--manifest", required=True, type=Path, help="YAML list from a research agent")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--priority", type=int, default=5)
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--today", default="2026-08-06")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = yaml.safe_load(args.manifest.read_text())
    if not isinstance(rows, list):
        print("ERROR: manifest must be a YAML list", file=sys.stderr)
        return 1

    path = args.lab / "corpus" / "bibliography.yaml"
    data = yaml.safe_load(path.read_text())
    existing = {e["id"] for e in data["entries"]}
    # Near-duplicate detection on the same key `corpus.py validate` warns on, because an
    # exact-id check let `harris-2003-trading-and-exchanges` in beside
    # `harris-2003-trading-exchanges`. A manifest is an acquire-or-promote list, and a book
    # already catalogued should be enriched rather than added again.
    existing_keys = {corpus_engine.dedupe_key(e): e["id"] for e in data["entries"]}

    added, skipped, bad, near_duplicates, enriched = [], [], [], [], []
    for row in rows:
        if not row.get("suggested_id") or not row.get("title"):
            bad.append(row.get("suggested_id") or row.get("title") or "<unnamed>")
            continue
        if row["suggested_id"] in existing:
            skipped.append(row["suggested_id"])
            continue
        candidate = to_entry(row, args.bucket, args.today, args.priority)
        key = corpus_engine.dedupe_key(candidate)
        clash = existing_keys.get(key)
        if clash and corpus_engine.compatible_titles(candidate["title"], next(
            (e.get("title", "") for e in data["entries"] if e["id"] == clash), ""
        )):
            # Enrich rather than skip. Seventy-four entries were marked freely available
            # with no URL recorded, so nothing could fetch them; a manifest that found the
            # URL should fill that in, not be discarded for describing a book we already
            # knew about. Only empty fields are written, so a curated value always wins.
            existing_entry = next(e for e in data["entries"] if e["id"] == clash)
            filled = []
            ids = existing_entry.setdefault("identifiers", {})
            for key in ("doi", "isbn", "url"):
                if not ids.get(key) and candidate["identifiers"].get(key):
                    ids[key] = candidate["identifiers"][key]
                    filled.append(key)
            acq = existing_entry.setdefault("acquisition", {})
            if not acq.get("source_url") and candidate["acquisition"].get("source_url"):
                acq["source_url"] = candidate["acquisition"]["source_url"]
                filled.append("source_url")
                if acq.get("state") in {None, "not_acquired", "open_url"}:
                    acq["state"] = candidate["acquisition"]["state"]
            if not existing_entry.get("pages") and candidate.get("pages"):
                existing_entry["pages"] = candidate["pages"]
                filled.append("pages")
            if filled:
                enriched.append(f"{clash}: filled {', '.join(filled)}")
            else:
                near_duplicates.append(f"{row['suggested_id']} -> already catalogued as {clash}")
            continue
        added.append(candidate)
        existing_keys[key] = candidate["id"]

    if not args.dry_run and (added or enriched):
        data["entries"].extend(added)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    print(json.dumps({
        "added": len(added),
        "open_url": sum(1 for e in added if e["acquisition"]["state"] == "open_url"),
        "purchasable": sum(1 for e in added if e["acquisition"]["state"] == "purchasable"),
        "already_present": skipped,
        "near_duplicates_skipped": near_duplicates,
        "existing_entries_enriched": enriched,
        "unusable_rows": bad,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
