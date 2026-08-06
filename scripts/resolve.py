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
import html
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
UNPAYWALL = "https://api.unpaywall.org/v2"
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


def crossref_search(title: str, cache: Cache, delay: float = 0.12,
                    authors: list[str] | None = None, year: int | None = None) -> list[dict[str, Any]]:
    # Author and year go into the query, not just into the check afterwards. A
    # bibliographic query carrying them puts the right record at the top, which is
    # what lets the match rule stay strict without refusing everything.
    bibliographic = normalize(title)[:220]
    if authors:
        bibliographic += " " + " ".join(surname(a) for a in authors[:3] if surname(a))
    if year:
        bibliographic += f" {year}"
    key = f"cr2::{normalize(bibliographic)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = urllib.parse.quote_plus(bibliographic)
    url = f"{CROSSREF}?query.bibliographic={query}&rows=8&mailto={MAILTO}"
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


def arxiv_search(title: str, cache: Cache, delay: float = 1.0) -> list[dict[str, Any]]:
    """Search arXiv through its public results page.

    The Atom API refuses this environment outright (persistent 429 on every query,
    including with the documented three-second delay), while the site itself serves
    normally. The results page carries everything the match rule needs: identifier,
    full title, author list and the original announcement year.
    """
    key = f"axh::{normalize(title)}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    query = urllib.parse.urlencode({"searchtype": "title", "query": normalize(title)[:200], "size": 25})
    # arXiv throttles hard and recovers. Back off and retry rather than recording a
    # 429 as "this paper does not exist", which is the same class of mistake as
    # caching a quota failure.
    body = b""
    for attempt in range(3):
        status, body = http_get(f"https://arxiv.org/search/?{query}", accept="text/html")
        if status == 200:
            break
        if status != 429:
            raise ApiError(f"arxiv search http {status}")
        time.sleep(delay * (2 ** attempt))
    else:
        raise ApiError("arxiv search http 429 after 3 attempts")
    page = body.decode("utf-8", errors="replace")

    results: list[dict[str, Any]] = []
    for block in page.split('<li class="arxiv-result">')[1:]:
        ident = re.search(r"arxiv\.org/abs/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z\-]+/\d{7})", block)
        heading = re.search(r'<p class="title is-5 mathjax">(.*?)</p>', block, flags=re.S)
        if not ident or not heading:
            continue
        clean = html.unescape(re.sub(r"<[^>]+>", " ", heading.group(1)))
        names = [html.unescape(re.sub(r"<[^>]+>", "", name)).strip()
                 for name in re.findall(r'<a href="/search/\?searchtype=author[^"]*">(.*?)</a>', block, flags=re.S)]
        # "originally announced March 2022" is the date of record; a v3 revision year
        # would put a 2015 paper in 2024 and fail the year check for the wrong reason.
        flat = re.sub(r"<[^>]+>", " ", block)
        announced = re.search(r"originally announced\s+\w+\s+(\d{4})", flat, flags=re.I)
        submitted = re.search(r"Submitted\s+\d+\s+\w+,\s+(\d{4})", flat)
        year = int((announced or submitted).group(1)) if (announced or submitted) else None
        arxiv_id = ident.group(1)
        results.append({
            "display_name": re.sub(r"\s+", " ", clean).strip(),
            "publication_year": year,
            "doi": f"10.48550/arXiv.{arxiv_id.split('v')[0]}",
            "id": f"arxiv:{arxiv_id}",
            "authorships": [{"author": {"display_name": name}} for name in names],
            "licenses": [],
            "links": [{"url": f"https://arxiv.org/pdf/{arxiv_id}", "content_type": "application/pdf"}],
            "container": "arXiv",
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            "arxiv_id": arxiv_id,
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


def unpaywall(doi: str, cache: Cache, delay: float = 0.12) -> dict[str, Any]:
    """Where a free copy of this DOI lives, and under what licence, if any."""
    key = f"upw::{doi.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    url = f"{UNPAYWALL}/{urllib.parse.quote(doi)}?email={MAILTO}"
    status, body = http_get(url, accept="application/json")
    if status == 404:
        result = {"is_oa": False, "not_in_index": True}
        cache.put(key, result)
        return result
    if status != 200:
        raise ApiError(f"unpaywall http {status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ApiError(f"unpaywall parse: {error}") from error
    best = payload.get("best_oa_location") or {}
    locations = payload.get("oa_locations") or []
    result = {
        "is_oa": bool(payload.get("is_oa")),
        "oa_status": payload.get("oa_status"),
        "licence": best.get("license"),
        "pdf_url": best.get("url_for_pdf"),
        "landing_url": best.get("url_for_landing_page"),
        "host_type": best.get("host_type"),
        "repository": best.get("repository_institution"),
        "alternates": [
            {"pdf_url": loc.get("url_for_pdf"), "licence": loc.get("license"), "host_type": loc.get("host_type")}
            for loc in locations if loc.get("url_for_pdf")
        ][:4],
    }
    cache.put(key, result)
    time.sleep(delay)
    return result


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
    def is_preprint(row: dict[str, Any]) -> bool:
        return str(row.get("doi") or "").lower().startswith("10.48550/")

    rivals = [row for row in scored[1:] if row["similarity"] >= 0.85 and row["doi"] != best["doi"]]
    if rivals:
        # A preprint DOI and a publisher DOI for the same title are one work with two
        # locations, which is a fact about where to find it rather than an ambiguity.
        # Prefer the version of record and remember the preprint as an alternate.
        published = [row for row in [best, *rivals] if not is_preprint(row)]
        preprints = [row for row in [best, *rivals] if is_preprint(row)]
        if len(published) == 1 and preprints:
            chosen = published[0]
            chosen["preprint_doi"] = preprints[0]["doi"]
            return chosen, scored[:3], "matched (published version; preprint recorded as an alternate)"
        if not published and len(preprints) >= 1:
            return preprints[0], scored[:3], "matched (preprint only)"
        return None, scored[:3], "ambiguous: two published candidates clear the threshold"
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
    preprint_pdfs: dict[str, str | None] = {}
    arxiv_failures, arxiv_down = 0, False
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
            candidates = crossref_search(entry.get("title") or "", cache,
                                          authors=entry.get("authors"), year=entry.get("year"))
        except ApiError as error:
            errors.append({"id": entry["id"], "stage": "crossref", "error": str(error)})
        best, shortlist, reason = (None, [], "no candidates returned")
        if candidates:
            best, shortlist, reason = match(entry, candidates)

        # arXiv is consulted when the DOI registries could not place the work, and
        # for anything we recorded as a preprint. It is a second index, not a second
        # opinion: the same match rule applies to what it returns.
        preprintable = entry.get("form") in {"paper", "working_paper", "survey", "proceedings", "thesis"}
        if (not best or entry.get("form") == "working_paper") and args.arxiv and preprintable and not arxiv_down:
            try:
                preprints = arxiv_search(entry.get("title") or "", cache)
                arxiv_failures = 0
            except ApiError as error:
                preprints = []
                arxiv_failures += 1
                errors.append({"id": entry["id"], "stage": "arxiv", "error": str(error)})
                # A throttle that does not lift is a blocked index, and grinding through
                # the remaining titles at eighty seconds each buys nothing. Stop asking,
                # and say so, rather than turning a block into hundreds of silent misses.
                if arxiv_failures >= args.arxiv_give_up:
                    arxiv_down = True
                    errors.append({"id": "-", "stage": "arxiv",
                                   "error": f"abandoned after {arxiv_failures} consecutive failures; "
                                            "remaining titles were not searched on arXiv"})
            if preprints:
                matched_preprint, preprint_shortlist, preprint_reason = match(entry, preprints)
                if matched_preprint:
                    if best:
                        preprint_urls[entry["id"]] = matched_preprint["raw"].get("abs_url")
                        preprint_pdfs[entry["id"]] = f"https://arxiv.org/pdf/{matched_preprint['raw'].get('arxiv_id')}"
                    else:
                        best, shortlist, reason = matched_preprint, preprint_shortlist, "matched on arXiv"
                elif not best:
                    shortlist, reason = preprint_shortlist, f"arXiv: {preprint_reason}"

        if not candidates and args.openalex_fallback and not best:
            try:
                extra = openalex_search(entry.get("title") or "", cache)
            except ApiError as error:
                extra = []
                errors.append({"id": entry["id"], "stage": "openalex", "error": str(error)})
            if extra:
                best, shortlist, reason = match(entry, extra)

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
                "preprint_doi": best.get("preprint_doi"),
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
                "direct_pdf": (full_text_links(raw)[0] if raw.get("source") == "arxiv" and full_text_links(raw)
                               else preprint_pdfs.get(entry["id"])),
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
        "arxiv_abandoned": arxiv_down,
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


def cmd_study(args: argparse.Namespace) -> int:
    """Download reading copies of anything with a freely served full text.

    This is deliberately separate from `fetch`. `fetch` builds the corpus and is
    gated by the manifest, because putting a text into a corpus is a distribution
    and derivative use. Reading a paper the publisher serves for free is neither,
    and the corpus model already draws that line: `reference_only` means read it,
    learn from it, write our own explanations, do not copy it in. A study copy is
    the "read it" half. Nothing here changes a rights tag or a use class, and an
    entry that arrives with an open licence is still the only kind `fetch` takes.
    """
    root = Path(args.root)
    entries = load_entries(root)
    cache = Cache(root / "corpus" / ".resolve-cache")
    identified = {}
    if args.identified and Path(args.identified).exists():
        identified = {r["id"]: r for r in json.loads(Path(args.identified).read_text())["resolved"]}

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    got, skipped, errors = [], [], []
    record: list[dict[str, Any]] = []
    considered = 0

    for entry in entries:
        if considered >= args.limit:
            break
        rights = (entry.get("rights") or {}).get("status")
        if rights in {"proprietary_confidential"} or entry.get("status") == "rejected":
            skipped.append({"id": entry["id"], "reason": "excluded material is not acquired at all"})
            continue

        row = identified.get(entry["id"]) or {}
        oa_record = row.get("_oa") or {}
        direct = oa_record.get("direct_pdf")

        # A course or notes page: many free PDFs behind one entry. Same reasoning as
        # a single study copy, so it belongs here rather than behind the manifest.
        index_url = (entry.get("acquisition") or {}).get("download_index")
        if index_url:
            considered += 1
            status, body = http_get(index_url, timeout=45, accept="text/html")
            if status != 200:
                skipped.append({"id": entry["id"], "reason": f"notes index unreachable (http {status})"})
                continue
            origin = "/".join(index_url.split("/")[:3])
            stem = index_url.rsplit("/", 1)[0] + "/"
            links = sorted({
                link if link.startswith("http") else (origin + link if link.startswith("/") else stem + link)
                for link in re.findall(r'href="([^"]+\.pdf)"', body.decode("utf-8", errors="replace"))
            })[: args.max_files]
            folder = dest / entry["id"]
            folder.mkdir(parents=True, exist_ok=True)
            taken = 0
            for link in links:
                target = folder / link.rsplit("/", 1)[-1].split("?")[0]
                if target.exists():
                    taken += 1
                    continue
                code, blob = http_get(link, timeout=90, accept="application/pdf")
                if code == 200 and blob.startswith(b"%PDF"):
                    target.write_bytes(blob)
                    taken += 1
                time.sleep(0.25)
            if not taken:
                skipped.append({"id": entry["id"], "reason": "notes index had no retrievable PDFs"})
                continue
            total = sum(f.stat().st_size for f in folder.glob("*.pdf"))
            got.append({"id": entry["id"], "path": str(folder), "bytes": total, "files": taken,
                        "host": "course_page", "licence": None})
            record.append({
                "id": entry["id"],
                "acquisition": {
                    "state": "owned", "copy_path": str(folder), "source_url": index_url,
                    "obtained_at": str(date.today()),
                    "note": "Study copies of the notes the course serves publicly. Rights tag unchanged.",
                },
            })
            continue

        doi = ((entry.get("identifiers") or {}).get("doi") or (row.get("identifiers") or {}).get("doi"))

        location: dict[str, Any] = {}
        if direct:
            location = {"is_oa": True, "pdf_url": direct, "host_type": "repository",
                        "licence": None, "alternates": []}
        elif doi:
            try:
                location = unpaywall(doi, cache)
            except ApiError as error:
                errors.append({"id": entry["id"], "error": str(error)})
                continue
        else:
            skipped.append({"id": entry["id"], "reason": "no DOI and no direct link; cannot locate a free copy"})
            continue
        considered += 1

        if not location.get("is_oa") or not location.get("pdf_url"):
            skipped.append({"id": entry["id"], "reason": "no freely served full text found"})
            continue

        target = dest / f"{entry['id']}.pdf"
        if not target.exists():
            status, body = http_get(location["pdf_url"], timeout=90, accept="application/pdf")
            if status != 200 or not body.startswith(b"%PDF"):
                for alternate in location.get("alternates") or []:
                    status, body = http_get(alternate["pdf_url"], timeout=90, accept="application/pdf")
                    if status == 200 and body.startswith(b"%PDF"):
                        location = {**location, "pdf_url": alternate["pdf_url"], "host_type": alternate.get("host_type")}
                        break
            if status != 200 or not body.startswith(b"%PDF"):
                skipped.append({"id": entry["id"], "reason": f"download failed (http {status})"})
                time.sleep(0.2)
                continue
            target.write_bytes(body)
            time.sleep(args.delay)

        got.append({"id": entry["id"], "path": str(target), "bytes": target.stat().st_size,
                    "host": location.get("host_type"), "licence": location.get("licence")})
        record.append({
            "id": entry["id"],
            "acquisition": {
                "state": "owned",
                "copy_path": str(target),
                "source_url": location["pdf_url"],
                "obtained_at": str(date.today()),
                "note": (f"Study copy from the {location.get('host_type') or 'publisher'} copy the publisher serves "
                         f"free. Rights tag unchanged; this is a reading copy, not a corpus grant."),
            },
        })

    if record:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump({"round": args.round, "entries": record}, sort_keys=False,
                                      allow_unicode=True, width=120))
    by_host: dict[str, int] = {}
    for row in got:
        by_host[row.get("host") or "unknown"] = by_host.get(row.get("host") or "unknown", 0) + 1
    print(json.dumps({
        "considered": considered, "downloaded": len(got), "skipped": len(skipped), "api_errors": len(errors),
        "megabytes": round(sum(r["bytes"] for r in got) / 1e6, 1), "by_host": by_host,
        "dest": str(dest), "findings": args.out if record else None,
    }, indent=2))
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
    checks.append("match: refuses on year gap, on author mismatch, and on two published candidates clearing the bar")

    with_preprint = good + [dict(good[0], id="W3", doi="10.48550/arxiv.1105.1694")]
    chosen, _, reason3 = match(entry, with_preprint)
    assert chosen and chosen["doi"] == good[0]["doi"], (chosen, reason3)
    assert chosen.get("preprint_doi", "").startswith("10.48550/"), chosen
    only_preprint, _, _ = match(entry, [dict(good[0], id="W4", doi="10.48550/arxiv.1105.1694")])
    assert only_preprint and only_preprint["doi"].startswith("10.48550/"), only_preprint
    checks.append("match: a preprint beside its published version is one work with two locations, not an ambiguity")

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
    identify.add_argument("--openalex-fallback", action="store_true", help="Try OpenAlex when nothing else matched (metered API).")
    identify.add_argument("--no-arxiv", dest="arxiv", action="store_false", default=True, help="Skip the arXiv index.")
    identify.add_argument("--arxiv-give-up", type=int, default=6, help="Consecutive arXiv failures before abandoning that index for the run.")

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

    study = sub.add_parser("study", help="Download reading copies of freely served full texts. Separate from the corpus manifest.")
    study.add_argument("--identified", default="corpus/resolved.json")
    study.add_argument("--dest", default="corpus/study")
    study.add_argument("--limit", type=int, default=500)
    study.add_argument("--delay", type=float, default=0.4)
    study.add_argument("--round", type=int, default=1)
    study.add_argument("--out", default="corpus/study-findings.yaml")
    study.add_argument("--max-files", type=int, default=60, help="cap per multi-file source")

    sub.add_parser("self-test", help="Matching and licence-classification checks; no network.")
    args = parser.parse_args(argv)

    if args.command == "identify":
        return cmd_identify(args)
    if args.command == "licence":
        return cmd_licence(args)
    if args.command == "fetch":
        return cmd_fetch(args)
    if args.command == "study":
        return cmd_study(args)

    result = self_test()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
