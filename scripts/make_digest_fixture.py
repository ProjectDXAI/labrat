#!/usr/bin/env python3
"""Build the smoke fixture the digest arms are measured against.

Without extracted text every anchor collapses to the card tier, all three arms spend
zero tokens, and the comparison passes whatever the allocator does. That is a test that
cannot fail, which is worse than no test. This writes a small synthetic passage store
against one entry the bibliography already licenses for ingest, so `never`, `policy` and
`always` land in three different places and the assertion has something to catch.

The text is obvious filler on purpose. The fixture exercises token accounting and tier
selection; it is not pretending to be the paper.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ENTRY = "he-2022-fundamentals-perpetual-futures"

CONTEXT = {
    "context_id": "ctx-smoke-digest",
    "timestamp": "2026-03-04T14:02:11Z",
    "market_type": "perp_dex",
    "instrument": "ETH-PERP",
    "decision_type": "entry",
    "horizon": "hours",
    "observables_available": [
        "mark_price",
        "oracle_price",
        "funding_rate",
        "mid_price_series",
        "position_state",
        "fee_schedule",
    ],
    "tools_available": [],
    "latency_budget_seconds": 30.0,
    "uncertainties": ["does the no-arbitrage relation hold on this venue after funding"],
    "question": "should we carry the basis given the funding rate and the observed deviation",
}


def main() -> int:
    root = Path(".")
    if not (root / "corpus" / "bibliography.yaml").exists():
        print("ERROR: run from a lab root holding corpus/bibliography.yaml", file=sys.stderr)
        return 1

    out = root / "corpus" / "passages"
    out.mkdir(parents=True, exist_ok=True)
    body = (
        "Synthetic fixture page for the digest smoke test. The perpetual mark price tracks "
        "the index through a funding payment, and the no-arbitrage relation ties the two "
        "together whenever the funding interval is short relative to the holding period. "
    ) * 6

    with (out / "passages.jsonl").open("w") as handle:
        for page in range(1, 7):
            handle.write(json.dumps({
                "passage_id": f"{ENTRY}#{ENTRY}:p{page}",
                "entry_id": ENTRY,
                "file": f"{ENTRY}.pdf",
                "page": page,
                "use_class": "ingest_attribution",
                "rights_status": "cc_by",
                "text": f"[page {page}] {body}",
            }) + "\n")

    (root / ".digest-ctx.json").write_text(json.dumps(CONTEXT, indent=2))
    print(f"  fixture: 6 synthetic pages for {ENTRY}, context ctx-smoke-digest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
