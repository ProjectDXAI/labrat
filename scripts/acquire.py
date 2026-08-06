#!/usr/bin/env python3
"""Rank what to acquire next by what the knowledge store cannot currently support.

`compile-queue` ranks what to read from material already held. This ranks what is *not*
held, which is a different question and the one that actually blocks progress: 57 of this
corpus's 105 reading units sit behind a source nobody has a copy of, so no amount of
reading discipline moves them.

A source's score is not its citation count or its fame. It is how much of the store
currently rests on it without evidence:

    cards            how many concept cards anchor to it at all
    unearned         cards holding confidence >= 0.6 on an anchor nobody opened
    contested        cards inside a live contradiction cluster, which the card text
                     cannot settle -- only the sources can
    broken chain     cards covering a problem that has no complete chain to a decision
    load-bearing     anchors that two or more cards depend on, where one bad reading
                     propagates

The weights are deliberately blunt. The ordering is what matters, and the reason for a
source's position is printed next to it so a human can disagree with it.
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
import digest as digest_engine  # noqa: E402
import knowledge as knowledge_engine  # noqa: E402

WEIGHTS = {
    "card": 1.0,
    "unearned": 3.0,
    "contested": 2.5,
    "broken_chain": 2.0,
    "load_bearing": 1.5,
    "priority": 0.4,
}


def build(lab_root: Path) -> dict[str, Any]:
    corpus_dir = lab_root / "corpus"
    entries = {e["id"]: e for e in corpus_engine.load_bibliography(corpus_engine.corpus_paths(corpus_dir))}
    store = knowledge_engine.load_store(knowledge_engine.knowledge_paths(lab_root / "knowledge"))
    sources = knowledge_engine.load_corpus_sources(lab_root)
    assessment = knowledge_engine.assess(store, sources)
    passages = digest_engine.load_passages(corpus_dir)

    unearned = {row["concept_id"] for row in assessment["high_confidence_on_unread"]}
    contested = {cid for cluster in assessment["contradiction"]["clusters"] for cid in cluster}
    broken = {row["problem_id"] for row in assessment["chains"] if not row["complete_chains"]}

    # Which sources does each card rest on, and how many cards share an anchor.
    anchor_cards: dict[str, set[str]] = {}
    source_cards: dict[str, list[dict[str, Any]]] = {}
    for concept in store.get("concepts") or []:
        for raw in concept.get("source_passage_ids") or []:
            ref = knowledge_engine.parse_passage_ref(raw)
            key = f"{ref['source_id']}#{ref['anchor']}" if ref.get("anchor") else ref["source_id"]
            anchor_cards.setdefault(key, set()).add(concept["concept_id"])
            source_cards.setdefault(ref["source_id"], []).append(concept)

    rows = []
    for source_id, cards in source_cards.items():
        entry = entries.get(source_id)
        held_pages = len(passages.get(source_id) or [])
        if held_pages:
            continue  # already have the text; this list is about what is missing

        reasons = []
        score = 0.0

        card_ids = sorted({c["concept_id"] for c in cards})
        score += WEIGHTS["card"] * len(card_ids)
        reasons.append(f"{len(card_ids)} card{'s' if len(card_ids) != 1 else ''} rest on it")

        hit_unearned = sorted(set(card_ids) & unearned)
        if hit_unearned:
            score += WEIGHTS["unearned"] * len(hit_unearned)
            reasons.append(f"{len(hit_unearned)} holding confidence nobody earned ({', '.join(hit_unearned[:3])})")

        hit_contested = sorted(set(card_ids) & contested)
        if hit_contested:
            score += WEIGHTS["contested"] * len(hit_contested)
            reasons.append(f"{len(hit_contested)} inside a live contradiction")

        problems = {p for c in cards for p in (c.get("problem_ids") or [])}
        hit_broken = sorted(problems & broken)
        if hit_broken:
            score += WEIGHTS["broken_chain"] * len(hit_broken)
            reasons.append(f"covers {', '.join(hit_broken)}, which reaches no decision")

        shared = [k for k, v in anchor_cards.items() if k.startswith(f"{source_id}#") and len(v) >= 2]
        if shared:
            score += WEIGHTS["load_bearing"] * len(shared)
            reasons.append(f"{len(shared)} anchor{'s' if len(shared) != 1 else ''} carrying two or more cards")

        priority = (entry or {}).get("priority") or 0
        score += WEIGHTS["priority"] * priority

        identifiers = (entry or {}).get("identifiers") or {}
        rows.append({
            "source_id": source_id,
            "title": (entry or {}).get("title"),
            "authors": (entry or {}).get("authors") or [],
            "year": (entry or {}).get("year"),
            "bucket": (entry or {}).get("bucket"),
            "form": (entry or {}).get("form"),
            "pages": (entry or {}).get("pages"),
            "priority": priority,
            "doi": identifiers.get("doi"),
            "url": identifiers.get("url"),
            "score": round(score, 2),
            "cards": card_ids,
            "why": reasons,
        })

    rows.sort(key=lambda r: -r["score"])

    # Sources nothing cites yet, but the taxonomy budgeted pages for. These are the
    # general foundations: not blocking a card today, and the reason whole buckets have
    # no card worth writing.
    taxonomy = corpus_engine.load_taxonomy(corpus_engine.corpus_paths(corpus_dir))
    state = corpus_engine.load_state(corpus_engine.corpus_paths(corpus_dir))
    coverage = corpus_engine.coverage(entries.values(), taxonomy, state)
    cited_buckets = {entries[r["source_id"]].get("bucket") for r in rows if r["source_id"] in entries}
    thin = []
    for name, row in coverage["buckets"].items():
        target = row.get("target_pages") or 0
        mapped = row.get("pages_mapped") or 0
        held = sum(
            1
            for e in entries.values()
            if e.get("bucket") == name and passages.get(e["id"])
        )
        total = sum(1 for e in entries.values() if e.get("bucket") == name)
        if total and held / total < 0.25:
            thin.append({
                "bucket": name,
                "entries": total,
                "held": held,
                "held_share": round(held / total, 2),
                "pages_mapped": mapped,
                "target_pages": target,
                "cited_by_a_card": name in cited_buckets,
            })
    thin.sort(key=lambda r: (r["held_share"], -r["entries"]))

    return {
        "blocking": rows,
        "thin_buckets": thin,
        "totals": {
            "sources_cited_by_a_card": len(source_cards),
            "of_those_not_held": len(rows),
            "units_behind_missing_sources": sum(
                1
                for e in entries.values()
                if not passages.get(e["id"])
                for u in corpus_engine.entry_units(e)
                if u.get("unit_id") != "whole" and u.get("read_status") not in {"read", "compiled"}
            ),
        },
    }


def render(result: dict[str, Any], limit: int) -> str:
    lines = ["# What to acquire next", ""]
    t = result["totals"]
    lines.append(
        f"{t['of_those_not_held']} of the {t['sources_cited_by_a_card']} sources a concept card "
        f"cites are not held. {t['units_behind_missing_sources']} unread reading units sit behind them."
    )
    lines.append("")
    lines.append("## Blocking a card that already exists")
    lines.append("")
    for index, row in enumerate(result["blocking"][:limit], 1):
        authors = ", ".join(row["authors"][:2]) + (" et al." if len(row["authors"]) > 2 else "")
        lines.append(f"### {index}. {row['title']}")
        lines.append("")
        lines.append(
            f"`{row['source_id']}` · {authors or 'unknown'}"
            + (f" · {row['year']}" if row["year"] else "")
            + (f" · {row['pages']}pp" if row["pages"] else "")
            + f" · {row['bucket']} · score {row['score']}"
        )
        lines.append("")
        for reason in row["why"]:
            lines.append(f"- {reason}")
        if row["doi"]:
            lines.append(f"- doi: `{row['doi']}`")
        elif row["url"]:
            lines.append(f"- at: {row['url']}")
        lines.append("")

    lines.append("## Buckets where we hold almost nothing")
    lines.append("")
    lines.append(
        "Not blocking a card today, which is the point: a field we hold nothing from "
        "produces no cards to block. These are the general foundations."
    )
    lines.append("")
    lines.append("| bucket | entries | held | pages mapped / target |")
    lines.append("| --- | ---: | ---: | ---: |")
    for row in result["thin_buckets"]:
        lines.append(
            f"| {row['bucket']} | {row['entries']} | {row['held']} "
            f"({row['held_share']:.0%}) | {row['pages_mapped']:,} / {row['target_pages']:,} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank what to acquire against what the store cannot support")
    parser.add_argument("--lab", default="corpus-lab")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build(Path(args.lab).resolve())
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    text = render(result, args.limit)
    if args.out:
        args.out.write_text(text)
        print(json.dumps({"out": str(args.out), **result["totals"]}, indent=2))
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
