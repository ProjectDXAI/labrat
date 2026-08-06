#!/usr/bin/env python3
"""Declare reading units on held sources that have none.

A source with no unit cannot be read against, cannot be compiled from, and cannot pass the
admission gate however good it is. Ninety-one held sources were in that state.

Two shapes, because two kinds of thing are held.

A paper is one unit. Splitting a thirty-page paper into declared sections without having
read it invents structure, and a locator that does not correspond to anything is worse
than one that says "the whole paper". The topic is taken from the entry's own notes, which
came from the research pass that catalogued it, rather than being written fresh here.

A venue documentation set is one unit per fetched page, because each page was fetched
separately and covers a distinct mechanism: the funding formula is not the liquidation
waterfall. Those are scoped with `file:` locators against the markdown actually on disk.

Books are skipped. A six-hundred-page textbook declared as one unit is not a reading plan,
and deciding what to read inside one requires opening it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus as corpus_engine  # noqa: E402
import digest as digest_engine  # noqa: E402

DOC_FORMS = {"exchange_doc", "api_doc", "software_docs", "rulebook", "standard"}
MAX_PAPER_PAGES = 80


def topic_from(entry: dict[str, Any]) -> str:
    note = (entry.get("notes") or "").strip()
    if note:
        first = re.split(r"(?<=[.!?])\s+", note)[0]
        return first[:240]
    return f"{entry.get('title')} in full"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Declare reading units on held sources that lack them")
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    corpus_dir = args.lab / "corpus"
    passages = digest_engine.load_passages(corpus_dir)
    path = corpus_dir / "bibliography.yaml"
    data = yaml.safe_load(path.read_text())

    papers, docs, skipped, recounted = 0, 0, [], []
    for entry in data["entries"]:
        rows = passages.get(entry["id"]) or []
        if not rows:
            continue

        # Where we hold the text, the extracted page count is measured and the declared one
        # was somebody's estimate. Several entries declare fewer pages than the PDF has,
        # which then reads as units overflowing their source. Measured wins.
        measured = len({row.get("page") for row in rows})
        declared = entry.get("pages")
        if entry.get("form") not in DOC_FORMS and (declared is None or declared < measured):
            recounted.append({"id": entry["id"], "declared": declared, "measured": measured})
            entry["pages"] = measured
        existing = [u for u in (entry.get("units") or []) if u.get("unit_id") != "whole"]
        if existing:
            continue

        if entry.get("form") in DOC_FORMS:
            files = sorted({row.get("file") for row in rows if row.get("file")})
            units = []
            for name in files:
                stem = Path(name).stem
                units.append({
                    "unit_id": stem,
                    "title": None,
                    "topic": f"{entry.get('venue') or entry['id']}: {stem.replace('-', ' ')}",
                    "locator": f"file:{name}",
                    "kind": "section",
                    "pages": len({row.get("page") for row in rows if row.get("file") == name}),
                    "priority": entry.get("priority") or 4,
                    "read_status": "unread",
                    "concepts_expected": [],
                    "notes": None,
                })
            if units:
                entry.setdefault("units", []).extend(units)
                docs += len(units)
            continue

        pages = len({row.get("page") for row in rows})
        if pages <= MAX_PAPER_PAGES:
            entry.setdefault("units", []).append({
                "unit_id": "whole-paper",
                "title": None,
                "topic": topic_from(entry),
                "locator": "the whole paper",
                "kind": "whole" if pages <= 12 else "section",
                "pages": pages,
                "priority": entry.get("priority") or 4,
                "read_status": "unread",
                "concepts_expected": [],
                "notes": None,
            })
            papers += 1
        else:
            skipped.append({"id": entry["id"], "pages": pages, "form": entry.get("form")})

    if not args.dry_run and (papers or docs or recounted):
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    print(json.dumps({
        "paper_units": papers,
        "doc_units": docs,
        "page_counts_corrected": len(recounted),
        "skipped_needs_a_reading_plan": len(skipped),
        "skipped_examples": skipped[:8],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
