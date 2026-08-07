#!/usr/bin/env python3
"""One screen of where the corpus actually stands.

Written because every other command answers one question well and none of them answer
"what is the state of this thing". Ordered by what is actionable rather than by what is
large: the blocked chains first, then compilation, then coverage, then the backlog.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import corpus as corpus_engine  # noqa: E402
import digest as digest_engine  # noqa: E402
import knowledge as knowledge_engine  # noqa: E402


def main() -> int:
    lab = HERE.parent
    corpus_dir = lab / "corpus"
    paths = corpus_engine.corpus_paths(corpus_dir)
    entries = corpus_engine.load_bibliography(paths)
    store = knowledge_engine.load_store(knowledge_engine.knowledge_paths(lab / "knowledge"))
    sources = knowledge_engine.load_corpus_sources(lab)
    passages = digest_engine.load_passages(corpus_dir)
    assessment = knowledge_engine.assess(store, sources)
    adm = knowledge_engine.admission(store, sources, {e["id"] for e in entries if passages.get(e["id"])})

    units = [u for e in entries for u in corpus_engine.entry_units(e) if u.get("unit_id") != "whole"]
    read = [u for u in units if u.get("read_status") in {"read", "compiled"}]
    held = [e for e in entries if passages.get(e["id"])]
    tokens = sum(len(r.get("text") or "") for rows in passages.values() for r in rows) // 4

    print("CORPUS")
    print(f"  {len(entries):>5} sources catalogued")
    print(f"  {len(held):>5} held with extracted text  ({tokens:,} tokens across "
          f"{sum(len(v) for v in passages.values()):,} passages)")
    print(f"  {len(read):>5} of {len(units)} reading units read")
    print()

    print("WHAT CANNOT BE ACTED ON")
    broken = [r for r in assessment["chains"] if not r["complete_chains"]]
    if broken:
        for row in broken:
            print(f"  {row['problem_id']}: {row['concepts']} cards, "
                  f"{row['with_method']} with a method, {row['with_hypothesis']} with a hypothesis, "
                  f"{row['with_decision_card']} with a decision card, 0 carrying all three")
    else:
        print("  every problem has a card reaching a decision")
    unearned = assessment["high_confidence_on_unread"]
    print(f"  {len(unearned)} cards hold confidence >= 0.6 on an anchor nobody opened")
    print()

    print("COMPILATION  (this measures our work, not source quality)")
    print(f"  {adm['admitted']:>5} compiled")
    print(f"  {adm['card_incomplete']:>5} have a card, one artifact short")
    print(f"  {adm['no_card_yet']:>5} held but not compiled yet")
    for item in adm["next_artifact"]:
        print(f"        next: {item}")
    print()

    print("GROUNDING")
    print(f"  {assessment['grounded_share']:.0%} of cards rest on a unit someone opened")
    print(f"  {len(assessment['contradiction']['clusters'])} contradiction clusters across "
          f"{assessment['contradiction']['concepts_in_a_contradiction']} cards")
    print()

    print("NOT HELD")
    wanted = [e for e in entries if (e.get("acquisition") or {}).get("state") in {"open_url", "purchasable"}]
    free = [e for e in wanted if (e.get("acquisition") or {}).get("state") == "open_url"]
    # `open_url` without a source_url is a claim that a free copy exists somewhere, with
    # no way to go and get it. That is a research task, not a download, and counting the
    # two together overstates what `make fetch` can do by an order of magnitude.
    fetchable = [e for e in free if (e.get("acquisition") or {}).get("source_url", "").startswith("http")]
    print(f"  {len(fetchable):>5} free with a URL recorded, ready to download  (make fetch)")
    print(f"  {len(free) - len(fetchable):>5} believed free but with no URL recorded, so nothing can fetch them")
    print(f"  {len(wanted) - len(free):>5} need buying or a library")
    ocr = [e for e in entries if "needs-ocr" in (e.get("tags") or [])]
    if ocr:
        print(f"  {len(ocr):>5} held but with no text layer, needing OCR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
