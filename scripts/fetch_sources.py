#!/usr/bin/env python3
"""Download the sources whose entries already record a legitimate free location.

This fetches exactly what the bibliography says is freely available and nothing else. It
reads `acquisition.source_url` on entries whose `acquisition.state` is `open_url`, which
is set only where a research pass found a publisher, author or repository copy. It does
not search, follow alternative links, or try a second location when the first fails: a
source that does not download is reported as not downloaded, and stays a purchase.

Behaviour worth knowing before running it:

- A response that is not a PDF is discarded rather than saved. Publishers commonly answer
  a bot with an HTML interstitial at HTTP 200, and a saved interstitial would index as
  hundreds of pages of navigation text under a real paper's id.
- Existing files are never overwritten. Re-running is safe and only picks up what is
  missing.
- One request at a time with a delay between them. These are university and publisher
  servers hosting things for free.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

UA = "labrat-corpus/1.0 (research bibliography; contact via repository)"
PDF_MAGIC = b"%PDF"

# Venue documentation is a website, not a paper. Fetching it as a PDF was always going to
# miss, so exchange docs are pulled as HTML, reduced to text, and written as markdown into
# `corpus/sources/<id>/` where the indexer already reads markdown.
HTML_FORMS = {"exchange_doc", "api_doc", "software_docs", "rulebook", "standard"}

SCRIPT_BLOCK = re.compile(r"<(script|style|noscript|svg)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
BLANKS = re.compile(r"\n{3,}")


def html_to_text(body: bytes) -> str:
    """Enough of a reduction to index. Not a renderer, and not trying to be."""
    text = body.decode("utf-8", errors="replace")
    text = SCRIPT_BLOCK.sub(" ", text)
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = TAG.sub(" ", text)
    for entity, char in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                         ("&quot;", '"'), ("&#39;", "'"), ("&mdash;", "-"), ("&ndash;", "-")):
        text = text.replace(entity, char)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return BLANKS.sub("\n\n", text).strip()


def fetch_html(url: str, timeout: int) -> tuple[str | None, str]:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; labrat-corpus/1.0; research bibliography)",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, type(exc).__name__
    text = html_to_text(body)
    if len(text) < 500:
        return None, f"page rendered to {len(text)} characters; probably JavaScript-only"
    return text, "ok"


def fetch(url: str, timeout: int) -> tuple[bytes | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            ctype = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 - network failures are the expected case here
        return None, type(exc).__name__

    if not body.startswith(PDF_MAGIC):
        # arXiv /abs/ pages are HTML; the PDF lives at /pdf/. Worth one retry because the
        # manifests recorded both forms.
        return None, f"not a PDF ({ctype.split(';')[0] or 'unknown'}, {len(body)} bytes)"
    return body, "ok"


def arxiv_pdf(url: str) -> str | None:
    if "arxiv.org/abs/" in url:
        return url.replace("/abs/", "/pdf/")
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download sources the bibliography records as freely available")
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="stop after this many downloads, 0 for no limit")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--today", default="2026-08-06")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    biblio = args.lab / "corpus" / "bibliography.yaml"
    study = args.lab / "corpus" / "study"
    study.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(biblio.read_text())

    targets = []
    for entry in data["entries"]:
        acq = entry.get("acquisition") or {}
        if acq.get("state") != "open_url":
            continue
        url = acq.get("source_url")
        if not url or not url.startswith("http"):
            continue
        if entry.get("form") in HTML_FORMS:
            folder = args.lab / "corpus" / "sources" / entry["id"]
            destination = folder / "docs.md"
        else:
            destination = study / f"{entry['id']}.pdf"
        if destination.exists() or destination.is_symlink():
            continue
        targets.append((entry, url, destination))

    print(f"{len(targets)} sources recorded as freely available and not yet held", file=sys.stderr)
    if args.dry_run:
        for entry, url, _ in targets:
            print(f"  {entry['id']}\n      {url}")
        return 0

    got, failed = [], []
    for index, (entry, url, destination) in enumerate(targets, 1):
        if args.limit and len(got) >= args.limit:
            break
        if entry.get("form") in HTML_FORMS:
            text, why = fetch_html(url, args.timeout)
            body = text.encode() if text else None
            if body is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                header = f"# {entry['title']}\n\nFetched {args.today} from {url}\n\n"
                body = (header + text).encode()
        else:
            body, why = fetch(url, args.timeout)
            if body is None:
                alt = arxiv_pdf(url)
                if alt:
                    time.sleep(args.delay)
                    body, why = fetch(alt, args.timeout)
        if body is None:
            failed.append({"id": entry["id"], "url": url, "why": why})
            print(f"  [{index}/{len(targets)}] MISS {entry['id']}: {why}", file=sys.stderr)
        else:
            destination.write_bytes(body)
            got.append({"id": entry["id"], "kilobytes": round(len(body) / 1024, 1)})
            print(f"  [{index}/{len(targets)}] got  {entry['id']} ({len(body) // 1024} KB)", file=sys.stderr)
            entry.setdefault("acquisition", {})["state"] = "owned"
            entry["acquisition"]["copy_path"] = str(destination.relative_to(args.lab))
            entry["acquisition"]["obtained_at"] = args.today
        time.sleep(args.delay)

    if got:
        biblio.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    print(json.dumps({
        "downloaded": len(got),
        "failed": len(failed),
        "megabytes": round(sum(g["kilobytes"] for g in got) / 1024, 1),
        "misses": failed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
