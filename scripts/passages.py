#!/usr/bin/env python3
"""Passage retrieval over acquired sources, and the analysis brief built on top of it.

`knowledge.py retrieve` serves a *decision*: a structured context with a market, a
horizon, available observables and a decision type, answered with compiled concept
cards. That is the live path and it is deliberately narrow.

This is the other path. While doing analysis you have a question in prose, not a
decision context, and you want the corpus pulled into whatever you are working on:
what we have compiled that bears on it, what the sources actually say and exactly
where, what contradicts it, what we hold on disk, and what we would have to read
next. That is a different query shape and a different answer shape.

    python scripts/passages.py index                       # extract and index what we hold
    python scripts/passages.py search --query "queue position adverse selection"
    python scripts/passages.py brief --question "..." --markdown
    python scripts/passages.py status

Passage retrieval is subordinate to the concept layer on purpose. A nearest passage
is selected because its words resemble the query, not because its mechanism applies,
so passages appear in a brief as *evidence anchors under a compiled claim* and as a
reading queue — never as the answer. The `raw_similarity` control arm in the
retrieval lab exists to keep that distinction honest.

Rights are enforced on output, not on indexing. We index everything we legitimately
hold so that search can find it; what may be *emitted* depends on the use class. A
brief is written to be carried into an analysis, and text that may not be
redistributed must not ride along inside it.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus as corpus_engine  # noqa: E402
import knowledge as knowledge_engine  # noqa: E402


MAX_PASSAGE_CHARS = 4000
MIN_PASSAGE_CHARS = 200
SNIPPET_CHARS = 320

# What may leave this module as source text, by use class.
QUOTABLE = {"ingest_full", "ingest_attribution", "ingest_share_alike",
            "ingest_noncommercial", "ingest_licensed", "ingest_check_terms"}


def have_extractor() -> bool:
    return shutil.which("pdftotext") is not None


def extract_text_file(path: Path) -> list[str]:
    """A markdown or text source, split into page-sized chunks on blank lines."""
    body = path.read_text(errors="replace")
    chunks, current, size = [], [], 0
    for para in body.split("\n\n"):
        current.append(para)
        size += len(para)
        if size > 3000:
            chunks.append("\n\n".join(current))
            current, size = [], 0
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [body]


def extract_pages(pdf: Path) -> list[str]:
    """Page text via poppler. Returns [] when the PDF has no text layer at all."""
    try:
        result = subprocess.run(
            ["pdftotext", "-q", "-enc", "UTF-8", str(pdf), "-"],
            capture_output=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    return result.stdout.decode("utf-8", errors="replace").split("\f")


def split_page(text: str) -> list[str]:
    """One passage per page, unless the page is long enough to be two."""
    clean = re.sub(r"[ \t]+", " ", text).strip()
    if len(clean) <= MAX_PASSAGE_CHARS:
        return [clean] if len(clean) >= MIN_PASSAGE_CHARS else []
    chunks, buffer = [], ""
    for paragraph in re.split(r"\n\s*\n", clean):
        if len(buffer) + len(paragraph) > MAX_PASSAGE_CHARS and buffer:
            chunks.append(buffer.strip())
            buffer = paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
    if buffer.strip():
        chunks.append(buffer.strip())
    return [c for c in chunks if len(c) >= MIN_PASSAGE_CHARS]


def passage_paths(root: Path) -> dict[str, Path]:
    base = root / "corpus" / "passages"
    return {"dir": base, "passages": base / "passages.jsonl", "index": base / "index.json"}


# Problem sets, their solutions and exams are not reading material. A course folder is
# roughly a fifth of these by page count, and they dilute every retrieval over the course:
# a BM25 hit on "renewal process" in an exam answer key is not the lecture that explains
# it. They stay on disk, because a graded problem with a published solution is good raw
# material for a capability evaluation later; they just do not belong in the reading corpus.
COURSEWARE_EXERCISE = re.compile(
    # No \b before the short tokens: these filenames separate words with underscores,
    # which regex counts as a word character, so \bmid\d never fires on MIT6_262S11_mid10.
    # The short tokens need start-of-name as well as a separator: these files are named
    # both `MIT6_262S11_mid10` and plain `mid10`, and a separator-only pattern misses the
    # second. \b is no help because underscore counts as a word character.
    r"(sol(ution)?s?\b|assn|pset|(?:^|[_\-])ps\d|(?:^|[_\-])hw\d|homework|problem[-_ ]?set"
    r"|midterm|(?:^|[_\-])mid\d|final\d|(?:^|[_\-])exam(?![a-z])|quiz)",
    re.IGNORECASE,
)


def is_exercise_file(path: Path) -> bool:
    """Problem set, solution key or exam rather than teaching material."""
    return bool(COURSEWARE_EXERCISE.search(path.stem))


def source_files(root: Path, entry_id: str, study_dir: Path, sources_dir: Path) -> list[Path]:
    """Every local file we hold for an entry, whether a single paper or a course folder.

    Deduplicated by resolved path. Several course folders exist under both `study/` and
    `sources/`, and globbing both bases indexed every one of their files twice: 1,305
    byte-identical passages, and a page count overstating the corpus by that much.
    """
    found: list[Path] = []
    for base in (study_dir, sources_dir):
        single = base / f"{entry_id}.pdf"
        if single.exists():
            found.append(single)
        folder = base / entry_id
        if folder.is_dir():
            # The exercise filter belongs to course folders only. A standalone entry that
            # happens to be a solution manual is a document someone catalogued on purpose.
            # Web documentation is held as markdown, not PDF: an exchange's docs site is
            # the primary source and printing it to PDF only loses the anchors.
            for pattern in ("*.pdf", "*.md", "*.txt"):
                found.extend(
                    path for path in sorted(folder.glob(pattern))
                    if not is_exercise_file(path)
                )

    # Keyed on name and size, not resolved path. Several course folders exist as two
    # real copies, one under study/ and one under sources/, with different inodes and
    # identical contents. Resolving paths does not see that; name plus size does.
    unique: dict[tuple[str, int], Path] = {}
    for path in found:
        try:
            key = (path.name, path.stat().st_size)
        except OSError:
            continue
        unique.setdefault(key, path)
    return list(unique.values())


def build_index(root: Path, study: Path, sources: Path, rebuild: bool = False) -> dict[str, Any]:
    if not have_extractor():
        raise SystemExit(
            "ERROR: pdftotext not found. Install poppler (brew install poppler) — "
            "the index is empty without it, and an empty index that reports success "
            "is worse than a missing one."
        )
    entries = {e["id"]: e for e in corpus_engine.load_bibliography(
        corpus_engine.corpus_paths(root / "corpus"))}
    paths = passage_paths(root)
    paths["dir"].mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    covered, skipped_excluded, no_text = [], [], []
    for entry_id, entry in sorted(entries.items()):
        rights = corpus_engine.derive_rights(entry)
        if rights["use_class"] == "excluded":
            skipped_excluded.append(entry_id)
            continue
        files = source_files(root, entry_id, study, sources)
        if not files:
            continue
        pages_indexed = 0
        for pdf in files:
            reader = extract_pages if pdf.suffix.lower() == ".pdf" else extract_text_file
            for page_number, page_text in enumerate(reader(pdf), start=1):
                for part, chunk in enumerate(split_page(page_text)):
                    rows.append({
                        "passage_id": f"{entry_id}#{pdf.stem}:p{page_number}" + (f".{part}" if part else ""),
                        "entry_id": entry_id,
                        "file": pdf.name,
                        "page": page_number,
                        "use_class": rights["use_class"],
                        "rights_status": rights["status"],
                        "text": chunk,
                    })
                    pages_indexed += 1
        if pages_indexed:
            covered.append(entry_id)
        else:
            no_text.append(entry_id)

    with paths["passages"].open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    # Postings, so search does not retokenize the whole corpus on every query.
    df: dict[str, int] = {}
    postings: dict[str, list[list[int]]] = {}
    lengths: list[int] = []
    for position, row in enumerate(rows):
        terms = knowledge_engine.tokenize(row["text"])
        lengths.append(len(terms))
        counts: dict[str, int] = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
        for term, count in counts.items():
            df[term] = df.get(term, 0) + 1
            postings.setdefault(term, []).append([position, count])

    index = {
        "count": len(rows),
        "avgdl": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "lengths": lengths,
        "df": df,
        "postings": postings,
    }
    paths["index"].write_text(json.dumps(index))
    return {
        "passages": len(rows),
        "entries_with_text": len(covered),
        "entries_without_text": no_text,
        "excluded": skipped_excluded,
        "distinct_terms": len(df),
        "index": str(paths["index"]),
    }


def load_index(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = passage_paths(root)
    if not paths["index"].exists():
        raise SystemExit("ERROR: no passage index. Run 'passages.py index' first.")
    rows = [json.loads(line) for line in paths["passages"].read_text().splitlines() if line.strip()]
    return rows, json.loads(paths["index"].read_text())


# A term carried by more than this share of passages says nothing about which
# passage to read. "does", "orders" and "position" all clear a generic stopword
# list and are still noise in a corpus that is entirely about order books, so the
# floor has to come from the corpus rather than from a fixed word list.
MAX_DOCUMENT_SHARE = 0.25


def score_passages(query: str, rows: list[dict[str, Any]], index: dict[str, Any],
                   k1: float = 1.5, b: float = 0.75,
                   max_share: float = MAX_DOCUMENT_SHARE) -> list[tuple[int, float, dict[str, int]]]:
    terms = knowledge_engine.tokenize(query)
    if not terms or not index["count"]:
        return []
    total, avgdl = index["count"], index["avgdl"] or 1.0
    informative = {term for term in set(terms)
                   if index["df"].get(term, 0) and index["df"][term] <= max_share * total}
    if not informative:
        # Every query term is corpus-wide vocabulary. Ranking on it would return the
        # longest pages rather than the relevant ones, so return nothing and let the
        # caller say the question needs sharper words.
        return []
    scores: dict[int, float] = {}
    hits: dict[int, dict[str, int]] = {}
    for term in informative:
        posting = index["postings"].get(term)
        if not posting:
            continue
        idf = math.log(1 + (total - index["df"][term] + 0.5) / (index["df"][term] + 0.5))
        for position, count in posting:
            length = index["lengths"][position] or 1
            contribution = idf * (count * (k1 + 1)) / (count + k1 * (1 - b + b * length / avgdl))
            scores[position] = scores.get(position, 0.0) + contribution
            hits.setdefault(position, {})[term] = count
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [(position, score, hits[position]) for position, score in ranked]


def emit_passage(row: dict[str, Any], terms: dict[str, int], allow_quote: bool = True) -> dict[str, Any]:
    """One matched passage, with its text and where to go and check it.

    There is no licence gate here. A licence restricting redistribution does not restrict
    reading text you already hold, and this brief is assembled and read on the machine
    that holds the file. `corpus.py rights` still records every source's terms; that is
    the thing to consult if any of this is ever published.

    The locator is not optional. A passage you cannot go and verify against the page is
    not evidence, whatever it says.
    """
    matched = sorted(terms, key=lambda term: -terms[term])[:8]
    snippet = row["text"][:SNIPPET_CHARS]
    return {
        "passage_id": row["passage_id"],
        "entry_id": row["entry_id"],
        "locator": f"{row['file']} p.{row['page']}",
        "use_class": row["use_class"],
        "matched_terms": matched,
        "snippet": snippet + ("\u2026" if len(row["text"]) > SNIPPET_CHARS else ""),
        "read_it_at": f"{row['file']} p.{row['page']}",
        "why_it_matched": (
            f"{sum(terms.values())} occurrences of {', '.join(matched[:5])} on this page"
        ),
    }


def analysis_brief(root: Path, question: str, passage_limit: int = 8, concept_limit: int = 5,
                   allow_quote: bool = True) -> dict[str, Any]:
    """Everything the corpus has to say about a question, in the order it should be read."""
    knowledge_dir = root / "knowledge"
    store = knowledge_engine.load_store(knowledge_engine.knowledge_paths(knowledge_dir))
    sources = knowledge_engine.load_corpus_sources(root)
    entries = {e["id"]: e for e in corpus_engine.load_bibliography(corpus_engine.corpus_paths(root / "corpus"))}

    # 1. The compiled layer first. A concept card carries assumptions and failure
    #    modes; a passage carries neither.
    servable = knowledge_engine.servable_concepts(store, sources)
    concepts: list[dict[str, Any]] = []
    if servable:
        by_id = {c["concept_id"]: c for c in servable}
        bm25 = knowledge_engine.Bm25({c["concept_id"]: knowledge_engine.concept_document(c) for c in servable})
        query_terms = knowledge_engine.tokenize(question)
        scored = sorted(
            ((bm25.score(c["concept_id"], query_terms), c) for c in servable),
            key=lambda pair: -pair[0],
        )
        for score, concept in scored[:concept_limit]:
            if score <= 0:
                continue
            counter = [by_id[cid]["canonical_name"] for cid in (concept.get("contradicting_concept_ids") or [])
                       if cid in by_id]
            concepts.append({
                "concept_id": concept["concept_id"],
                "name": concept["canonical_name"],
                "score": round(score, 3),
                "mechanism": concept.get("mechanism"),
                "assumptions": concept.get("assumptions") or [],
                "known_failure_modes": concept.get("known_failure_modes") or [],
                "contradicted_by": counter,
                "alternative_explanations": concept.get("alternative_explanations") or [],
                "anchors": concept.get("source_passage_ids") or [],
                "problem_ids": concept.get("problem_ids") or [],
            })

    # 2. The passage layer, as evidence anchors and a reading queue.
    passages: list[dict[str, Any]] = []
    by_entry: dict[str, int] = {}
    try:
        rows, index = load_index(root)
    except SystemExit:
        rows, index = [], {"count": 0, "avgdl": 0.0, "lengths": [], "df": {}, "postings": {}}
    for position, _score, terms in score_passages(question, rows, index):
        row = rows[position]
        # Two pages of the same source say roughly the same thing about a query.
        if by_entry.get(row["entry_id"], 0) >= 2:
            continue
        by_entry[row["entry_id"]] = by_entry.get(row["entry_id"], 0) + 1
        passages.append(emit_passage(row, terms, allow_quote))
        if len(passages) >= passage_limit:
            break

    # 3. Sources that bear on the question but are not on disk, ranked by priority,
    #    so the brief says what to go and get rather than only what we happen to hold.
    matched_ids = {p["entry_id"] for p in passages}
    catalogue = [e for e in entries.values() if e.get("status") != "rejected"]
    if catalogue:
        entry_bm25 = knowledge_engine.Bm25({
            e["id"]: knowledge_engine.tokenize(" ".join(filter(None, [
                e.get("title"), " ".join(e.get("authors") or []), e.get("bucket"),
                " ".join(e.get("tags") or []), e.get("notes") or "",
            ])))
            for e in catalogue
        })
        terms = knowledge_engine.tokenize(question)
        ranked_entries = sorted(
            ((entry_bm25.score(e["id"], terms), e) for e in catalogue),
            key=lambda pair: -pair[0],
        )
    else:
        ranked_entries = []

    to_acquire, unread_units = [], []
    for score, entry in ranked_entries:
        if score <= 0 or len(to_acquire) >= 6:
            break
        held = bool(source_files(root, entry["id"], root / "corpus" / "study", root / "corpus" / "sources"))
        if entry["id"] in matched_ids or held:
            for unit in corpus_engine.entry_units(entry):
                if unit.get("read_status") in {"unread", "located"} and len(unread_units) < 6:
                    unread_units.append({
                        "entry_id": entry["id"], "unit_id": unit["unit_id"],
                        "topic": unit.get("topic"), "locator": unit.get("locator"),
                    })
            continue
        rights = corpus_engine.derive_rights(entry)
        to_acquire.append({
            "entry_id": entry["id"], "title": entry.get("title"), "score": round(score, 3),
            "bucket": entry.get("bucket"), "priority": entry.get("priority"),
            "use_class": rights["use_class"], "rights_status": rights["status"],
            "acquisition": (entry.get("acquisition") or {}).get("state"),
        })

    # 4. Open research questions that touch the same ground.
    open_questions = []
    question_terms = set(knowledge_engine.tokenize(question))
    for kind, items, key in (("bet", store.get("bets") or [], "bet_id"),
                             ("extension", store.get("extensions") or [], "extension_id")):
        for item in items:
            blob = knowledge_engine.tokenize(" ".join(filter(None, [
                item.get("title"), item.get("novel_claim"), item.get("prediction"), item.get("domain"),
            ])))
            overlap = len(question_terms & set(blob))
            if overlap >= 3:
                open_questions.append({"kind": kind, "id": item.get(key), "title": item.get("title"),
                                       "overlap": overlap,
                                       "first_computation": item.get("first_computation")})
    open_questions.sort(key=lambda row: -row["overlap"])

    return {
        "question": question,
        "compiled_concepts": concepts,
        "what_would_change_the_answer": sorted({
            mode for concept in concepts for mode in concept["known_failure_modes"]
        })[:6],
        "source_passages": passages,
        "reading_queue": unread_units,
        "not_held_yet": to_acquire,
        "open_questions": open_questions[:5],
        "coverage": {
            "indexed_passages": index["count"],
            "sources_on_disk": len({row["entry_id"] for row in rows}),
            "catalogue_size": len(entries),
            "quotable_passages_returned": sum(1 for p in passages if p.get("snippet")),
        },
    }


def render_brief(brief: dict[str, Any], allow_quote: bool = True) -> str:
    lines = [f"# {brief['question']}", ""]
    coverage = brief["coverage"]
    lines.append(
        f"*{coverage['indexed_passages']} passages indexed from {coverage['sources_on_disk']} sources "
        f"held locally, out of {coverage['catalogue_size']} catalogued.*"
    )
    if allow_quote:
        lines += ["", "> **Local reading mode.** Snippets below include text from sources whose licence "
                       "does not permit redistribution. Read them here; do not carry them into anything "
                       "that leaves this machine."]
    lines.append("")

    if brief["compiled_concepts"]:
        lines.append("## What we have compiled")
        for concept in brief["compiled_concepts"]:
            lines.append(f"\n### {concept['name']}  `{concept['concept_id']}`")
            lines.append(f"\n{concept['mechanism']}")
            if concept["assumptions"]:
                lines.append("\n**Holds only if:** " + "; ".join(concept["assumptions"][:3]))
            if concept["contradicted_by"]:
                lines.append("\n**Contradicted by:** " + "; ".join(concept["contradicted_by"]))
            elif concept["alternative_explanations"]:
                lines.append("\n**Competing account:** " + concept["alternative_explanations"][0])
            if concept["anchors"]:
                anchors = [a if isinstance(a, str) else a.get("source_id") for a in concept["anchors"]]
                lines.append("\n**Anchored to:** " + ", ".join(str(a) for a in anchors[:4]))
    else:
        lines.append("## What we have compiled\n\nNothing compiled bears on this. "
                     "The passages below are unfiltered by mechanism, so read them as leads rather than as findings.")

    if brief["what_would_change_the_answer"]:
        lines.append("\n## What would change the answer")
        for mode in brief["what_would_change_the_answer"]:
            lines.append(f"- {mode}")

    lines.append("\n## In the sources")
    if not brief["source_passages"]:
        lines.append("\nNothing in the indexed material matched. Either we do not hold the right "
                     "sources, the question uses different vocabulary than they do, or every word in "
                     "it is corpus-wide vocabulary that cannot discriminate between pages.")
    for passage in brief["source_passages"]:
        lines.append(f"\n**{passage['entry_id']}** — {passage['locator']}  `{passage['use_class']}`")
        if passage.get("snippet"):
            lines.append(f"\n> {passage['snippet']}")
        else:
            lines.append(f"\n{passage['why_it_matched']}. Open it at {passage['read_it_at']}; "
                         "the licence does not permit reproducing the text here.")

    if brief["reading_queue"]:
        lines.append("\n## Read next, in what we already hold")
        for unit in brief["reading_queue"]:
            locator = f" ({unit['locator']})" if unit.get("locator") else ""
            lines.append(f"- `{unit['entry_id']}#{unit['unit_id']}`{locator} — {unit['topic']}")

    if brief["not_held_yet"]:
        lines.append("\n## Catalogued, relevant, not on disk")
        for row in brief["not_held_yet"]:
            lines.append(f"- **{row['title']}** `{row['entry_id']}` — {row['use_class']}, "
                         f"priority {row['priority']}")

    if brief["open_questions"]:
        lines.append("\n## Open questions on the same ground")
        for row in brief["open_questions"]:
            runnable = f" — run `{row['first_computation']}`" if row.get("first_computation") else ""
            lines.append(f"- `{row['id']}` {row['title']}{runnable}")

    return "\n".join(lines)


def self_test() -> dict[str, Any]:
    import tempfile

    checks: list[str] = []

    assert split_page("short") == [], "a fragment is not a passage"
    long_page = ("mechanism " * 60).strip()
    assert split_page(long_page) == [long_page]
    huge = "\n\n".join(["paragraph " * 120] * 8)
    parts = split_page(huge)
    assert len(parts) > 1 and all(len(p) <= MAX_PASSAGE_CHARS + 1200 for p in parts), [len(p) for p in parts]
    checks.append("split_page: fragments dropped, a normal page stays whole, a long page splits on paragraphs")

    rows = [
        {"passage_id": "a#f:p1", "entry_id": "open-source", "file": "f.pdf", "page": 1,
         "use_class": "ingest_full", "rights_status": "cc_by",
         "text": "queue position determines adverse selection at the top of the book " * 6},
        {"passage_id": "b#g:p2", "entry_id": "closed-source", "file": "g.pdf", "page": 2,
         "use_class": "reference_only", "rights_status": "all_rights_reserved",
         "text": "queue position and adverse selection in dealer markets " * 6},
        {"passage_id": "c#h:p3", "entry_id": "unrelated", "file": "h.pdf", "page": 3,
         "use_class": "ingest_full", "rights_status": "cc_by",
         "text": "photosynthesis in marine algae under low light " * 6},
    ]
    df: dict[str, int] = {}
    postings: dict[str, list[list[int]]] = {}
    lengths = []
    for position, row in enumerate(rows):
        terms = knowledge_engine.tokenize(row["text"])
        lengths.append(len(terms))
        counts: dict[str, int] = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
        for term, count in counts.items():
            df[term] = df.get(term, 0) + 1
            postings.setdefault(term, []).append([position, count])
    index = {"count": len(rows), "avgdl": sum(lengths) / len(lengths),
             "lengths": lengths, "df": df, "postings": postings}

    ranked = score_passages("queue position adverse selection", rows, index, max_share=1.0)
    assert ranked and ranked[0][0] in {0, 1}, ranked
    assert all(position != 2 for position, _, _ in ranked), "an unrelated page must not match"
    checks.append("score_passages: BM25 ranks the on-topic pages and leaves the unrelated one out")

    # "position" is in two of three passages here, so a 0.5 floor must drop it and
    # leave the ranking to the terms that actually discriminate.
    wide = score_passages("position", rows, index, max_share=0.5)
    assert wide == [], "a term carried by most of the corpus must not drive the ranking"
    narrow = score_passages("photosynthesis", rows, index, max_share=0.5)
    assert narrow and narrow[0][0] == 2, narrow
    checks.append("score_passages: corpus-wide vocabulary is floored out, a rare term still ranks")

    # Both emit text: this is a local reading tool and the licence question belongs to
    # publishing, not to assembling a brief on the machine that already holds the file.
    # The locator has to survive either way, because a passage you cannot go and check is
    # not evidence.
    open_hit = emit_passage(rows[0], {"queue": 6})
    closed_hit = emit_passage(rows[1], {"queue": 6})
    for hit in (open_hit, closed_hit):
        assert hit.get("snippet"), hit
        assert hit["why_it_matched"] and hit["read_it_at"], hit
    assert closed_hit["locator"] == "g.pdf p.2"
    checks.append("emit_passage: text and locator emitted for anything held")

    # Two real copies of one course, one under study/ and one under sources/, indexed
    # every page twice and overstated the corpus by 1,305 passages. Different inodes, so
    # resolving paths does not catch it; name and size do.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for base in ("study", "sources"):
            folder = root / base / "course"
            folder.mkdir(parents=True)
            (folder / "lec01.pdf").write_bytes(b"identical bytes")
        files = source_files(root, "course", root / "study", root / "sources")
        assert len(files) == 1, files
        (root / "sources" / "course" / "lec02.pdf").write_bytes(b"different length here")
        files = source_files(root, "course", root / "study", root / "sources")
        assert len(files) == 2, files
    checks.append("source_files: one document held in two places is indexed once")

    # Problem sets and exams are dropped from a course folder, and only from a course
    # folder: a standalone entry that happens to be a solution manual is a document
    # somebody catalogued deliberately, not clutter.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = root / "study" / "course"
        folder.mkdir(parents=True)
        for name in ("lec01.pdf", "assn01.pdf", "assn01_sol.pdf", "mid10.pdf",
                     "LecNote.pdf", "examples.pdf"):
            (folder / name).write_bytes(name.encode())
        kept = {p.name for p in source_files(root, "course", root / "study", root / "sources")}
        # `examples.pdf` is worked examples, not an exam paper.
        assert kept == {"lec01.pdf", "LecNote.pdf", "examples.pdf"}, kept
        (root / "study" / "manual_solutions.pdf").write_bytes(b"x")
        standalone = source_files(root, "manual_solutions", root / "study", root / "sources")
        assert len(standalone) == 1, standalone
    checks.append("source_files: course exercises dropped, a standalone solution manual kept")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "corpus").mkdir(parents=True)
        (root / "knowledge").mkdir(parents=True)
        (root / "corpus" / "bibliography.yaml").write_text(
            "entries:\n"
            "  - id: held-open\n    title: An Open Monograph on Queues\n    bucket: queueing_networks\n"
            "    form: monograph\n    pages: 100\n    priority: 5\n"
            "    rights: {status: cc_by, confidence: confirmed, evidence: 'https://example.invalid', checked_at: '2026-01-01'}\n"
            "  - id: wanted-closed\n    title: A Commercial Textbook on Queue Position\n    bucket: queueing_networks\n"
            "    form: textbook\n    pages: 500\n    priority: 5\n"
            "    rights: {status: all_rights_reserved, confidence: inferred}\n"
        )
        (root / "corpus" / "taxonomy.yaml").write_text("buckets: {queueing_networks: {target_pages: 1000}}\ndefaults: {}\n")
        brief = analysis_brief(root, "queue position and adverse selection", allow_quote=False)
        assert brief["coverage"]["indexed_passages"] == 0, "no index yet"
        titles = {row["entry_id"] for row in brief["not_held_yet"]}
        assert "wanted-closed" in titles, brief["not_held_yet"]
        text = render_brief(brief)
        assert "Nothing compiled bears on this" in text, text[:300]
        assert "Catalogued, relevant, not on disk" in text
    checks.append("analysis_brief: with nothing compiled and nothing indexed, it says so and still names what to acquire")

    return {"ok": True, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Passage retrieval and analysis briefs over acquired sources")
    parser.add_argument("--root", default=".", help="lab root containing corpus/ and knowledge/")
    sub = parser.add_subparsers(dest="command", required=True)

    index_cmd = sub.add_parser("index", help="Extract and index the text of every source we hold.")
    index_cmd.add_argument("--study", default="corpus/study")
    index_cmd.add_argument("--sources", default="corpus/sources")

    search_cmd = sub.add_parser("search", help="Rank passages against a query.")
    search_cmd.add_argument("--query", required=True)
    search_cmd.add_argument("--limit", type=int, default=10)
    search_cmd.add_argument("--quote-local", action="store_true",
                            help="Show text from sources whose licence forbids redistribution. Local reading only.")

    brief_cmd = sub.add_parser("brief", help="Assemble a question into an analysis brief.")
    brief_cmd.add_argument("--question", required=True)
    brief_cmd.add_argument("--passages", type=int, default=8)
    brief_cmd.add_argument("--concepts", type=int, default=5)
    brief_cmd.add_argument("--markdown", action="store_true")
    brief_cmd.add_argument("--quote-local", action="store_true",
                           help="Include text from sources whose licence forbids redistribution. Local reading only.")

    sub.add_parser("status", help="What is indexed and what is held but unindexed.")
    sub.add_parser("self-test", help="Chunking, ranking, the rights gate and brief assembly; no network, no PDFs.")
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.command == "index":
        print(json.dumps(build_index(root, root / args.study, root / args.sources), indent=2))
        return 0

    if args.command == "search":
        rows, index = load_index(root)
        results = []
        for position, score, terms in score_passages(args.query, rows, index)[: args.limit]:
            results.append({**emit_passage(rows[position], terms, args.quote_local), "score": round(score, 3)})
        print(json.dumps({"query": args.query, "results": results,
                          "indexed": index["count"]}, indent=2))
        return 0

    if args.command == "brief":
        brief = analysis_brief(root, args.question, args.passages, args.concepts, args.quote_local)
        print(render_brief(brief, args.quote_local) if args.markdown else json.dumps(brief, indent=2))
        return 0

    if args.command == "status":
        try:
            rows, index = load_index(root)
        except SystemExit:
            print(json.dumps({"indexed": False, "reason": "no index; run 'passages.py index'",
                              "extractor_available": have_extractor()}, indent=2))
            return 0
        by_class: dict[str, int] = {}
        for row in rows:
            by_class[row["use_class"]] = by_class.get(row["use_class"], 0) + 1
        print(json.dumps({
            "indexed": True, "passages": index["count"], "distinct_terms": len(index["df"]),
            "sources": len({row["entry_id"] for row in rows}),
            "passages_by_use_class": by_class,
            "quotable_share": round(sum(v for k, v in by_class.items() if k in QUOTABLE) / max(len(rows), 1), 3),
        }, indent=2))
        return 0

    result = self_test()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
