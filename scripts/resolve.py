#!/usr/bin/env python3
"""Deterministic bibliographic resolution, licence verification and acquisition.

The corpus engine decides what to look for. This resolves what was found against
public bibliographic infrastructure, so an identifier is read off a record rather
than remembered, and a licence is read off the page that grants it.

Three subcommands, each writing a findings file the corpus round merges:

    python scripts/resolve.py identify --limit 50      # title -> DOI, via OpenAlex
    python scripts/resolve.py licence  --limit 50      # DOI -> licence, from the landing page
    python scripts/resolve.py fetch --dest corpus/sources

Matching is strict and refuses rather than guesses. A candidate must clear a title
similarity threshold, a year window and an author check, or it goes to quarantine
with its candidates listed. A wrong identifier is worse than a missing one, and it
is much harder to notice.

Licence verification never trusts the aggregator's `license` field on its own. It
fetches the landing page and requires the licence to be stated there, recording the
operative text as evidence. An aggregator's metadata is a lead, not a grant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import yaml

CROSSREF = "https://api.crossref.org/works"
OPENALEX = "https://api.openalex.org/works"
ARXIV = "http://export.arxiv.org/api/query"  # the https host times out from some networks
MAILTO = "corpus@dxrg.ai"
USER_AGENT = f"labrat-corpus-resolver/1.0 (mailto:{MAILTO})"

# Licence strings we accept, mapped to the corpus rights vocabulary. The key is
# what must literally appear on the landing page; the aggregator's opinion alone
# is not enough.
LICENCE_PATTERNS: list[tuple[str, str, str]] = [
    (r"creative\s+commons\s+attribution\s+4\.0|cc[\s\-]?by[\s\-]?4\.0|creativecommons\.org/licenses/by/4\.0", "cc_by", "CC BY 4.0"),
    (r"creative\s+commons\s+attribution\s+3\.0|creativecommons\.org/licenses/by/3\.0", "cc_by", "CC BY 3.0"),
    (r"creativecommons\.org/licenses/by-sa/", "cc_by_sa", "CC BY-SA"),
    (r"creativecommons\.org/licenses/by-nc-sa/", "cc_by_nc_sa", "CC BY-NC-SA"),
    (r"creativecommons\.org/licenses/by-nc-nd/", "cc_by_nc_nd", "CC BY-NC-ND"),
    (r"creativecommons\.org/licenses/by-nc/", "cc_by_nc", "CC BY-NC"),
    (r"creativecommons\.org/licenses/by-nd/", "cc_by_nd", "CC BY-ND"),
    (r"creativecommons\.org/publicdomain/zero/|cc0\s+1\.0", "cc0", "CC0"),
]

# arXiv's default grant is a licence to arXiv to distribute, not a licence to us.
# It reads like an open licence to a careless eye, which is why it is named here.
ARXIV_DEFAULT = r"arxiv\.org/licenses/nonexclusive-distrib"

STOP = {"the", "a", "an", "of", "and", "or", "in", "on", "for", "to", "with", "is", "are", "by", "from", "its"}


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def token_set(text: str) -> set[str]:
    return {t for t in normalize(text).split() if t and t not in STOP}


def title_similarity(a: str, b: str) -> float:
    """Symmetric token-set F1. Robust to subtitle drift, unforgiving of a different work."""
    left, right = token_set(a), token_set(b)
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    if not overlap:
        return 0.0
    precision, recall = overlap / len(left), overlap / len(right)
    return 2 * precision * recall / (precision + recall)


def token_containment(a: str, b: str) -> float:
    """Overlap over the smaller token set: 1.0 when one title's words are all in the other."""
    left, right = token_set(a), token_set(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def surname(author: str) -> str:
    parts = normalize(author).split()
    return parts[-1] if parts else ""


def http_get(url: str, timeout: int = 25, accept: str = "*/*") -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() if error.fp else b""
    except Exception as error:  # noqa: BLE001 - network failures are data here, not crashes
        return 0, str(error).encode()


class Cache:
    """On-disk response cache. Reruns must not re-hammer public infrastructure."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", key)[:150]
        return self.root / f"{safe}.json"

    def get(self, key: str) -> Any | None:
        target = self.path(key)
        if target.exists():
            try:
                return json.loads(target.read_text())
            except json.JSONDecodeError:
                return None
        return None

    def put(self, key: str, value: Any) -> None:
        self.path(key).write_text(json.dumps(value))


class ApiError(Exception):
    """A transport or quota failure. Distinct from 'no such work', and never cached:
    a rate limit silently stored as 'not found' is how a resolver quietly stops working."""


def crossref_search(title: str, cache: Cache, delay: float = 0.12) -> list[dict[str, Any]]:
    key = f"cr::{normalize(title)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = urllib.parse.quote_plus(normalize(title)[:250])
    url = f"{CROSSREF}?query.bibliographic={query}&rows=5&mailto={MAILTO}"
    status, body = http_get(url, accept="application/json")
    if status != 200:
        raise ApiError(f"crossref http {status}")
    try:
        items = json.loads(body)["message"]["items"]
    except (json.JSONDecodeError, KeyError) as error:
        raise ApiError(f"crossref parse: {error}") from error
    results = [
        {
            "display_name": (item.get("title") or [""])[0],
            "publication_year": ((item.get("issued") or {}).get("date-parts") or [[None]])[0][0],
            "doi": item.get("DOI"),
            "id": f"crossref:{item.get('DOI')}",
            "authorships": [
                {"author": {"display_name": " ".join(filter(None, [a.get("given"), a.get("family")]))}}
                for a in (item.get("author") or [])
            ],
            "licenses": [
                {"url": lic.get("URL"), "content_version": lic.get("content-version")}
                for lic in (item.get("license") or [])
            ],
            "links": [
                {"url": link.get("URL"), "content_type": link.get("content-type")}
                for link in (item.get("link") or [])
            ],
            "container": (item.get("container-title") or [None])[0],
            "source": "crossref",
        }
        for item in items
    ]
    cache.put(key, results)
    time.sleep(delay)
    return results


def arxiv_search(title: str, cache: Cache, delay: float = 3.0) -> list[dict[str, Any]]:
    """arXiv's API asks for one request every three seconds. Honour it."""
    key = f"ax::{normalize(title)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = urllib.parse.quote(f'ti:"{normalize(title)[:200]}"')
    url = f"{ARXIV}?search_query={query}&max_results=5"
    status, body = http_get(url, accept="application/atom+xml")
    if status != 200:
        raise ApiError(f"arxiv http {status}")
    feed = body.decode("utf-8", errors="replace")
    results = []
    for chunk in feed.split("<entry>")[1:]:
        def pick(tag: str) -> str:
            found = re.search(rf"<{tag}>(.*?)</{tag}>", chunk, flags=re.S)
            return re.sub(r"\s+", " ", found.group(1)).strip() if found else ""
        abs_url = pick("id")
        results.append({
            "display_name": pick("title"),
            "publication_year": int(pick("published")[:4]) if pick("published")[:4].isdigit() else None,
            "doi": None,
            "id": abs_url,
            "authorships": [{"author": {"display_name": re.sub(r"\s+", " ", name).strip()}}
                            for name in re.findall(r"<name>(.*?)</name>", chunk, flags=re.S)],
            "licenses": [],
            "links": [{"url": abs_url.replace("/abs/", "/pdf/"), "content_type": "application/pdf"}] if "/abs/" in abs_url else [],
            "container": "arXiv",
            "abs_url": abs_url,
            "source": "arxiv",
        })
    cache.put(key, results)
    time.sleep(delay)
    return results


def openalex_search(title: str, cache: Cache, delay: float = 0.15) -> list[dict[str, Any]]:
    key = f"oa::{normalize(title)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = urllib.parse.quote(normalize(title)[:250])
    url = f"{OPENALEX}?filter=title.search:{query}&per-page=5&mailto={MAILTO}"
    status, body = http_get(url, accept="application/json")
    if status != 200:
        raise ApiError(f"openalex http {status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ApiError(f"openalex parse: {error}") from error
    if "error" in payload:
        raise ApiError(f"openalex: {payload['error']}")
    results = [dict(row, source="openalex") for row in payload.get("results", [])]
    cache.put(key, results)
    time.sleep(delay)
    return results


def match(entry: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """Strict match, or a refusal with the reason and the candidates that failed."""
    title = entry.get("title") or ""
    year = entry.get("year")
    authors = entry.get("authors") or []
    wanted = {surname(a) for a in authors if surname(a)}

    scored = []
    for candidate in candidates:
        similarity = title_similarity(title, candidate.get("display_name") or "")
        containment = token_containment(title, candidate.get("display_name") or "")
        candidate_year = candidate.get("publication_year")
        year_gap = abs(int(year) - int(candidate_year)) if (year and candidate_year) else 99
        names = {
            surname((a.get("author") or {}).get("display_name") or "")
            for a in (candidate.get("authorships") or [])
        }
        author_hit = bool(wanted & names) if wanted else None
        scored.append(
            {
                "openalex_id": candidate.get("id"),
                "title": candidate.get("display_name"),
                "year": candidate_year,
                "doi": candidate.get("doi"),
                "similarity": round(similarity, 3),
                "containment": round(containment, 3),
                "year_gap": year_gap,
                "author_hit": author_hit,
                "raw": candidate,
            }
        )
    scored.sort(key=lambda row: -row["similarity"])
    if not scored:
        return None, [], "no candidates returned"

    best = scored[0]
    # Registries sometimes store a truncated title ("HotStuff" for a paper whose
    # title runs to eight words). Containment rescues that case, but only when the
    # year is exact and an author surname matches, so a one-word candidate cannot
    # capture an unrelated work that happens to share it.
    contained = best["containment"] >= 0.95 and best["year_gap"] == 0 and best["author_hit"] is True
    if best["similarity"] < 0.85 and not contained:
        return None, scored[:3], f"best title similarity {best['similarity']} below 0.85"
    if best["year_gap"] > 1:
        return None, scored[:3], f"year gap {best['year_gap']} exceeds 1"
    if best["author_hit"] is False:
        return None, scored[:3], "no author surname in common"
    runner_up = scored[1] if len(scored) > 1 else None
    if runner_up and runner_up["similarity"] >= 0.85 and runner_up["doi"] != best["doi"]:
        # Two records both clear the bar. Which is the work and which is a
        # preprint, a chapter reprint or a different edition is not decidable here.
        return None, scored[:3], "ambiguous: two candidates clear the threshold"
    return best, scored[:3], "matched"


def load_entries(root: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load((root / "corpus" / "bibliography.yaml").read_text()) or {}
    return raw.get("entries") or []


OPEN_LICENCE_URLS = {
    "creativecommons.org/licenses/by/": "cc_by",
    "creativecommons.org/licenses/by-sa/": "cc_by_sa",
    "creativecommons.org/licenses/by-nc/": "cc_by_nc",
    "creativecommons.org/licenses/by-nc-sa/": "cc_by_nc_sa",
    "creativecommons.org/licenses/by-nd/": "cc_by_nd",
    "creativecommons.org/licenses/by-nc-nd/": "cc_by_nc_nd",
    "creativecommons.org/publicdomain/zero/": "cc0",
}


def licence_hint(candidate: dict[str, Any]) -> tuple[str | None, str | None]:
    """Publisher-deposited licence URL, if there is one. A lead for verification, not a grant."""
    for licence in candidate.get("licenses") or []:
        url = (licence.get("url") or "").lower()
        for needle, status in OPEN_LICENCE_URLS.items():
            if needle in url:
                return status, licence.get("url")
    hint = candidate.get("best_oa_location") or {}
    if hint.get("license"):
        return None, hint.get("license")
    return None, None


def full_text_links(candidate: dict[str, Any]) -> list[str]:
    urls = [link["url"] for link in (candidate.get("links") or []) if link.get("url")]
    oa = candidate.get("best_oa_location") or {}
    if oa.get("pdf_url"):
        urls.append(oa["pdf_url"])
    return urls


def cmd_identify(args: argparse.Namespace) -> int:
    root = Path(args.root)
    entries = load_entries(root)
    cache = Cache(root / "corpus" / ".resolve-cache")

    resolved, quarantine, errors = [], [], []
    preprint_urls: dict[str, str | None] = {}
    considered = 0
    for entry in entries:
        identifiers = entry.get("identifiers") or {}
        if identifiers.get("doi"):
            continue
        if entry.get("form") in {"api_doc", "exchange_doc", "rulebook", "standard", "software_docs", "course", "blog", "notes_own"}:
            continue  # not scholarly records; a DOI registry is the wrong index for them
        if args.bucket and entry.get("bucket") != args.bucket:
            continue
        if considered >= args.limit:
            break
        considered += 1

        candidates: list[dict[str, Any]] = []
        try:
            candidates = crossref_search(entry.get("title") or "", cache)
        except ApiError as error:
            errors.append({"id": entry["id"], "stage": "crossref", "error": str(error)})
        if not candidates or entry.get("form") == "working_paper":
            try:
                preprints = arxiv_search(entry.get("title") or "", cache)
            except ApiError as error:
                preprints = []
                errors.append({"id": entry["id"], "stage": "arxiv", "error": str(error)})
            # A preprint is a second record of the same work, not a rival candidate:
            # only consult it when nothing else matched, or when we recorded the
            # entry as a preprint in the first place.
            if not candidates:
                candidates = preprints
            elif preprints:
                matched_preprint, _, _ = match(entry, preprints)
                if matched_preprint:
                    preprint_urls[entry["id"]] = matched_preprint["raw"].get("abs_url")
        if not candidates and args.openalex_fallback:
            try:
                candidates = openalex_search(entry.get("title") or "", cache)
            except ApiError as error:
                errors.append({"id": entry["id"], "stage": "openalex", "error": str(error)})

        if not candidates:
            quarantine.append({"id": entry["id"], "title": entry.get("title"),
                               "reason": "no candidates returned", "candidates": []})
            continue

        best, shortlist, reason = match(entry, candidates)
        if not best:
            quarantine.append({"id": entry["id"], "title": entry.get("title"), "reason": reason, "candidates": [
                {k: c.get(k) for k in ("title", "year", "doi", "similarity", "containment", "year_gap", "author_hit")}
                for c in shortlist
            ]})
            continue

        raw = best["raw"]
        status, licence_url = licence_hint(raw)
        oa_block = raw.get("open_access") or {}
        resolved.append({
            "id": entry["id"],
            "identifiers": {
                "doi": (best["doi"] or "").replace("https://doi.org/", "") or None,
                "registry_id": best["openalex_id"],
                "url": f"https://doi.org/{(best['doi'] or '').replace('https://doi.org/', '')}" if best["doi"] else None,
            },
            "_oa": {
                "source": raw.get("source"),
                "is_oa": oa_block.get("is_oa"),
                "licence_status_hint": status,
                "licence_url_hint": licence_url,
                "full_text_links": full_text_links(raw),
                "landing_page_url": f"https://doi.org/{(best['doi'] or '').replace('https://doi.org/', '')}" if best["doi"] else None,
                "container": raw.get("container"),
                "abs_url": raw.get("abs_url") or preprint_urls.get(entry["id"]),
            },
            "_match": {"similarity": best["similarity"], "containment": best["containment"],
                       "year_gap": best["year_gap"], "matched_title": best["title"]},
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"resolved": resolved, "quarantine": quarantine, "api_errors": errors}, indent=2))
    print(json.dumps({
        "considered": considered,
        "resolved": len(resolved),
        "quarantined": len(quarantine),
        "api_errors": len(errors),
        "with_open_licence_hint": sum(1 for r in resolved if r["_oa"].get("licence_status_hint")),
        "with_full_text_link": sum(1 for r in resolved if r["_oa"].get("full_text_links")),
        "out": str(out),
    }, indent=2))
    return 0


def read_licence(url: str, cache: Cache, delay: float = 0.4) -> dict[str, Any]:
    """Fetch a landing page and report the licence it actually states."""
    key = f"page::{url}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    status, body = http_get(url, accept="text/html,application/xhtml+xml")
    text = body.decode("utf-8", errors="replace")
    flat = re.sub(r"\s+", " ", text.lower())
    result: dict[str, Any] = {"status": status, "url": url}
    for pattern, rights_status, label in LICENCE_PATTERNS:
        found = re.search(pattern, flat)
        if found:
            window = flat[max(0, found.start() - 160): found.end() + 160]
            result.update({"rights_status": rights_status, "label": label, "quote": window.strip()[:300]})
            break
    else:
        if re.search(ARXIV_DEFAULT, flat):
            result.update({
                "rights_status": "author_hosted_free",
                "label": "arXiv non-exclusive distribution licence",
                "quote": "arXiv perpetual non-exclusive licence: the author grants arXiv the right to distribute. No licence is granted to us.",
            })
        else:
            result.update({"rights_status": None, "label": None, "quote": None})
    cache.put(key, result)
    time.sleep(delay)
    return result


def cmd_licence(args: argparse.Namespace) -> int:
    root = Path(args.root)
    resolved = json.loads(Path(args.identified).read_text())["resolved"]
    cache = Cache(root / "corpus" / ".resolve-cache")

    findings, unresolved = [], []
    checked = 0
    for row in resolved:
        oa = row["_oa"]
        landing = oa.get("abs_url") or oa.get("landing_page_url") or (
            f"https://doi.org/{row['identifiers']['doi']}" if row["identifiers"].get("doi") else None)
        if not landing:
            continue
        if args.only_oa and not (oa.get("abs_url") or oa.get("licence_status_hint") or oa.get("full_text_links")):
            continue
        if checked >= args.limit:
            break
        checked += 1

        page = read_licence(landing, cache)
        if not page.get("rights_status"):
            # A page we could not read tells us nothing. A page we DID read, which
            # grants nothing, tells us it is all rights reserved — and that is a
            # result, not a gap: it retires the entry from the verify queue.
            if page.get("status") == 200:
                findings.append({
                    "id": row["id"],
                    "identifiers": row["identifiers"],
                    "rights": {
                        "status": "all_rights_reserved",
                        "confidence": "confirmed",
                        "evidence": landing,
                        "checked_at": str(date.today()),
                        "notes": "Publisher landing page read in full; it states no open licence. "
                                 "Readable and citable, not ingestable.",
                    },
                })
                continue
            unresolved.append({"id": row["id"], "url": landing, "http_status": page.get("status"),
                               "reason": "page could not be read; absence of evidence is not evidence",
                               "aggregator_hint": oa.get("licence_url_hint")})
            continue
        findings.append({
            "id": row["id"],
            "identifiers": row["identifiers"],
            "rights": {
                "status": page["rights_status"],
                "confidence": "confirmed",
                "evidence": page["url"],
                "checked_at": str(date.today()),
                "notes": f"{page['label']} stated on the landing page. Read: \"{(page.get('quote') or '')[:180]}\"",
            },
        })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({"round": args.round, "entries": findings}, sort_keys=False, allow_unicode=True, width=120))
    Path(str(out) + ".unresolved.json").write_text(json.dumps(unresolved, indent=2))
    by_status: dict[str, int] = {}
    for row in findings:
        key = row["rights"]["status"]
        by_status[key] = by_status.get(key, 0) + 1
    print(json.dumps({"checked": checked, "confirmed": len(findings), "by_status": by_status,
                      "unresolved": len(unresolved), "out": str(out)}, indent=2))
    return 0


INGESTABLE = {"cc0", "cc_by", "cc_by_sa", "cc_by_nc", "cc_by_nc_sa", "public_domain", "government_work", "owned_by_us"}


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download only what the manifest already admits. The rights gate decides, not this."""
    root = Path(args.root)
    entries = {e["id"]: e for e in load_entries(root)}
    manifest_path = root / "corpus" / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit("ERROR: run 'corpus.py manifest' first; fetch downloads only what the manifest admits")
    manifest = json.loads(manifest_path.read_text())
    identified = {r["id"]: r for r in json.loads(Path(args.identified).read_text())["resolved"]} if args.identified else {}

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    got, skipped = [], []
    for row in manifest["include"]:
        entry = entries.get(row["id"]) or {}
        rights = (entry.get("rights") or {}).get("status")
        if rights not in INGESTABLE:
            skipped.append({"id": row["id"], "reason": f"rights '{rights}' not in the ingestable set"})
            continue
        acquisition = entry.get("acquisition") or {}
        index_url = acquisition.get("download_index")
        if index_url:
            # A course or docs site: one entry, many files. Scrape the index the
            # publisher provides rather than guessing filenames.
            status, body = http_get(index_url, timeout=45, accept="text/html")
            if status != 200:
                skipped.append({"id": row["id"], "reason": f"download index unreachable (http {status})"})
                continue
            page = body.decode("utf-8", errors="replace")
            origin = "/".join(index_url.split("/")[:3])
            links = sorted({
                link if link.startswith("http") else origin + link
                for link in re.findall(r'href="([^"]+\.pdf)"', page)
            })
            if args.max_files:
                links = links[: args.max_files]
            folder = dest / row["id"]
            folder.mkdir(parents=True, exist_ok=True)
            taken = 0
            for link in links:
                name = link.rsplit("/", 1)[-1]
                target = folder / name
                if target.exists():
                    taken += 1
                    continue
                code, blob = http_get(link, timeout=90, accept="application/pdf")
                if code == 200 and blob.startswith(b"%PDF"):
                    target.write_bytes(blob)
                    taken += 1
                time.sleep(0.3)
            if not taken:
                skipped.append({"id": row["id"], "reason": "index had no retrievable PDFs"})
                continue
            total = sum(f.stat().st_size for f in folder.glob("*.pdf"))
            got.append({"id": row["id"], "path": str(folder), "files": taken, "bytes": total})
            continue

        pdf = ((identified.get(row["id"]) or {}).get("_oa") or {}).get("pdf_url")
        if not pdf:
            skipped.append({"id": row["id"], "reason": "no open-access PDF location on record"})
            continue
        target = dest / f"{row['id']}.pdf"
        if target.exists():
            got.append({"id": row["id"], "path": str(target), "bytes": target.stat().st_size, "cached": True})
            continue
        status, body = http_get(pdf, timeout=60, accept="application/pdf")
        if status != 200 or not body.startswith(b"%PDF"):
            skipped.append({"id": row["id"], "reason": f"download failed (http {status}, {len(body)} bytes)"})
            continue
        target.write_bytes(body)
        got.append({"id": row["id"], "path": str(target), "bytes": len(body), "cached": False})
        time.sleep(0.5)

    print(json.dumps({"downloaded": len(got), "skipped": len(skipped), "dest": str(dest),
                      "files": got, "not_taken": skipped}, indent=2))
    return 0


def self_test() -> dict[str, Any]:
    checks: list[str] = []

    assert title_similarity("Optimal Dealer Pricing under Transactions and Return Uncertainty",
                            "Optimal dealer pricing under transactions and return uncertainty") == 1.0
    assert title_similarity("Bandit Algorithms", "Branching Processes") < 0.3
    checks.append("title_similarity: case and punctuation insensitive, unrelated titles score low")

    entry = {"title": "Anomalous Price Impact and the Critical Nature of Liquidity", "year": 2011, "authors": ["Bence Tóth"]}
    good = [{"display_name": "Anomalous Price Impact and the Critical Nature of Liquidity in Financial Markets",
             "publication_year": 2011, "doi": "https://doi.org/10.1103/physrevx.1.021006",
             "id": "W1", "authorships": [{"author": {"display_name": "Bence Tóth"}}]}]
    best, _, reason = match(entry, good)
    assert best and reason == "matched", reason
    checks.append("match: accepts a subtitle extension with the right year and author")

    wrong_year = [dict(good[0], publication_year=1999)]
    assert match(entry, wrong_year)[0] is None, "a four-year gap must refuse"
    wrong_author = [dict(good[0], authorships=[{"author": {"display_name": "Someone Else"}}])]
    assert match(entry, wrong_author)[0] is None, "no shared surname must refuse"
    ambiguous = good + [dict(good[0], id="W2", doi="https://doi.org/10.2139/ssrn.1836508")]
    best2, _, reason2 = match(entry, ambiguous)
    assert best2 is None and "ambiguous" in reason2, reason2
    checks.append("match: refuses on year gap, on author mismatch, and on two candidates clearing the bar")

    assert not any(p[1] == "cc_by" for p in LICENCE_PATTERNS if re.search(p[0], "arxiv.org/licenses/nonexclusive-distrib/1.0/")), \
        "the arXiv default grant must not read as an open licence"
    checks.append("licence: the arXiv distribution grant is not mistaken for a CC licence")

    return {"ok": True, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve, licence-check and acquire corpus sources")
    parser.add_argument("--root", default=".", help="lab root containing corpus/")
    sub = parser.add_subparsers(dest="command", required=True)

    identify = sub.add_parser("identify", help="Resolve titles to DOIs against OpenAlex; refuse rather than guess.")
    identify.add_argument("--limit", type=int, default=50)
    identify.add_argument("--bucket", default=None)
    identify.add_argument("--out", default="corpus/resolved.json")
    identify.add_argument("--openalex-fallback", action="store_true", help="Try OpenAlex when Crossref returns nothing (metered API).")

    licence = sub.add_parser("licence", help="Read the licence off the landing page and write verify findings.")
    licence.add_argument("--identified", default="corpus/resolved.json")
    licence.add_argument("--limit", type=int, default=50)
    licence.add_argument("--round", type=int, default=1)
    licence.add_argument("--only-oa", action="store_true", default=True)
    licence.add_argument("--out", default="corpus/licence-findings.yaml")

    fetch = sub.add_parser("fetch", help="Download the manifest-eligible open-access PDFs.")
    fetch.add_argument("--identified", default="corpus/resolved.json")
    fetch.add_argument("--dest", default="corpus/sources")
    fetch.add_argument("--max-files", type=int, default=60, help="cap per multi-file source")

    sub.add_parser("self-test", help="Matching and licence-classification checks; no network.")
    args = parser.parse_args(argv)

    if args.command == "identify":
        return cmd_identify(args)
    if args.command == "licence":
        return cmd_licence(args)
    if args.command == "fetch":
        return cmd_fetch(args)

    result = self_test()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
