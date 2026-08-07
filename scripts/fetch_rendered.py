#!/usr/bin/env python3
"""Fetch documentation pages that only exist after JavaScript runs.

`fetch_sources.py` handles anything served as bytes. This handles the rest: exchange
documentation built as a single-page app, where a scripted GET returns a shell and the
content arrives from an API call afterwards. Binance's futures FAQ renders to zero
characters without a browser and about 23,000 with one.

Scope, deliberately narrow:

- Public documentation only. Every URL here is a page anyone can open without an account.
- No paywall or bot-block circumvention. Publishers that answer 403 are refusing scripted
  access to copyrighted material and that refusal is respected; where those papers are
  wanted, the arXiv version is used instead and the publisher URL stays as the citation.
- One page at a time with a delay, and a real user agent rather than a forged one.

Requires playwright and its chromium build:

    pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

BOILERPLATE = re.compile(
    r"^(buy crypto|markets?|trade|futures|earn|square|more|log in|sign up|download|"
    r"skip to (main )?content|cookie|accept|we use cookies|menu|search|home)$",
    re.IGNORECASE,
)


def clean(text: str) -> str:
    """Drop navigation chrome. A docs page is mostly menu by line count."""
    out, blank = [], 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            blank += 1
            if blank < 2:
                out.append("")
            continue
        blank = 0
        if BOILERPLATE.match(line) or len(line) < 2:
            continue
        out.append(line)
    return "\n".join(out).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch JavaScript-rendered documentation pages")
    parser.add_argument("--pages", required=True, type=Path,
                        help='JSON: {"entry-id": [["unit-name","url"], ...]}')
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--delay", type=float, default=3.0)
    parser.add_argument("--timeout", type=int, default=60000)
    parser.add_argument("--min-chars", type=int, default=1200,
                        help="below this the page is treated as not rendered, not as content")
    parser.add_argument("--today", default="2026-08-07")
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed.\n"
              "  pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return 1

    pages = json.loads(args.pages.read_text())
    base = args.lab / "corpus" / "sources"
    got, missed = [], []

    with sync_playwright() as engine:
        browser = engine.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        for entry_id, items in pages.items():
            folder = base / entry_id
            folder.mkdir(parents=True, exist_ok=True)
            for name, url in items:
                destination = folder / f"{name}.md"
                if destination.exists():
                    continue
                page = context.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=args.timeout)
                    text = clean(page.inner_text("body"))
                except Exception as exc:  # noqa: BLE001 - a failed page is data, not a crash
                    missed.append({"id": f"{entry_id}/{name}", "why": type(exc).__name__})
                    print(f"  MISS {entry_id}/{name}: {type(exc).__name__}", file=sys.stderr)
                    page.close()
                    time.sleep(args.delay)
                    continue
                page.close()

                if len(text) < args.min_chars:
                    missed.append({"id": f"{entry_id}/{name}", "why": f"rendered to {len(text)} chars"})
                    print(f"  MISS {entry_id}/{name}: only {len(text)} chars", file=sys.stderr)
                else:
                    destination.write_text(
                        f"# {entry_id} / {name}\n\nRendered {args.today} from {url}\n\n{text}")
                    got.append({"id": f"{entry_id}/{name}", "kilobytes": round(len(text) / 1024, 1)})
                    print(f"  got  {entry_id}/{name} ({len(text) // 1024} KB)", file=sys.stderr)
                time.sleep(args.delay)
        browser.close()

    print(json.dumps({"rendered": len(got), "missed": len(missed), "misses": missed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
