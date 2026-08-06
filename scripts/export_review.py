#!/usr/bin/env python3
"""Render the structural findings as one self-contained page.

The findings file is the primary artifact of this corpus and it is YAML, which is
the right format to write and the wrong one to review twenty-five entries in. This
emits a single HTML file with the findings embedded, filterable by status, domain
and text. No build step and no network: the page is opened directly or published.

    python scripts/export_review.py --out review.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT_KNOWLEDGE = REPO / "profiles" / "dxap-knowledge" / "knowledge"
DEFAULT_CORPUS = REPO / "profiles" / "quant-finance-corpus" / "corpus"

STATUS_NOTE = {
    "read": "Taken from primary material opened in this repository.",
    "tension": "Two read sources make claims that may not be mutually consistent.",
    "conjecture": "A pattern proposed from what was read, not itself asserted anywhere.",
}


def load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text()) or default


def collect(knowledge_dir: Path, corpus_dir: Path) -> dict[str, Any]:
    findings_doc = load(knowledge_dir / "structural_findings.yaml", {})
    findings = findings_doc.get("findings") or []
    shapes = findings_doc.get("recurring_shapes") or []

    bib = load(corpus_dir / "bibliography.yaml", {})
    entries = bib.get("entries") if isinstance(bib, dict) else bib
    entries = entries or []

    units = [u for e in entries for u in (e.get("units") or [])]
    read_units = [u for u in units if u.get("read_status") in {"read", "compiled"}]

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["status"]] = counts.get(finding["status"], 0) + 1

    domain_counts: dict[str, int] = {}
    for finding in findings:
        for domain in finding.get("domains") or []:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    return {
        "findings": findings,
        "shapes": shapes,
        "status_counts": counts,
        "domains": sorted(domain_counts.items(), key=lambda kv: (-kv[1], kv[0])),
        "stats": {
            "records": len(entries),
            "decomposed": sum(1 for e in entries if e.get("units")),
            "units": len(units),
            "read": len(read_units),
            "findings": len(findings),
            "shapes": len(shapes),
        },
    }


# --------------------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------------------

CSS = """
:root {
  color-scheme: light dark;

  /* Cool slate, biased toward the teal accent so the greys read as chosen. */
  --ground: #f6f8f8;
  --raised: #ffffff;
  --ink: #101a1d;
  --ink-soft: #3d5257;
  --ink-mute: #6b8085;
  --rule: #d4dfe0;
  --rule-soft: #e4ecec;

  --accent: #0d6f78;
  --accent-soft: #e2f0f1;

  --read: #0d6f78;
  --tension: #a1650a;
  --tension-soft: #f8ecd6;
  --conjecture: #97365b;
  --conjecture-soft: #f8e4ea;

  --mono: ui-monospace, "SF Mono", SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
  --prose: ui-serif, Charter, "Bitstream Charter", "Iowan Old Style", "Source Serif Pro", Georgia, serif;
  --ui: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

@media (prefers-color-scheme: dark) {
  :root {
    --ground: #0c1315;
    --raised: #121c1f;
    --ink: #dfe8e9;
    --ink-soft: #a7bbbe;
    --ink-mute: #74898d;
    --rule: #223437;
    --rule-soft: #1a292c;

    --accent: #45c3cb;
    --accent-soft: #17383b;

    --read: #45c3cb;
    --tension: #e0a850;
    --tension-soft: #33270f;
    --conjecture: #eb8daa;
    --conjecture-soft: #341a23;
  }
}

:root[data-theme="dark"] {
  --ground: #0c1315;
  --raised: #121c1f;
  --ink: #dfe8e9;
  --ink-soft: #a7bbbe;
  --ink-mute: #74898d;
  --rule: #223437;
  --rule-soft: #1a292c;
  --accent: #45c3cb;
  --accent-soft: #17383b;
  --read: #45c3cb;
  --tension: #e0a850;
  --tension-soft: #33270f;
  --conjecture: #eb8daa;
  --conjecture-soft: #341a23;
}

:root[data-theme="light"] {
  --ground: #f6f8f8;
  --raised: #ffffff;
  --ink: #101a1d;
  --ink-soft: #3d5257;
  --ink-mute: #6b8085;
  --rule: #d4dfe0;
  --rule-soft: #e4ecec;
  --accent: #0d6f78;
  --accent-soft: #e2f0f1;
  --read: #0d6f78;
  --tension: #a1650a;
  --tension-soft: #f8ecd6;
  --conjecture: #97365b;
  --conjecture-soft: #f8e4ea;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--prose);
  font-size: 17px;
  line-height: 1.62;
  -webkit-font-smoothing: antialiased;
}

.wrap {
  max-width: 1040px;
  margin: 0 auto;
  padding: 0 28px 96px;
}

/* ---- masthead ---------------------------------------------------------------- */

.mast { padding: 64px 0 0; }

.eyebrow {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 0 0 20px;
}

h1 {
  font-family: var(--prose);
  font-size: clamp(30px, 4.4vw, 44px);
  line-height: 1.16;
  letter-spacing: -0.018em;
  font-weight: 600;
  text-wrap: balance;
  margin: 0 0 20px;
  max-width: 20ch;
}

.standfirst {
  font-size: 18.5px;
  color: var(--ink-soft);
  max-width: 66ch;
  margin: 0 0 8px;
}

/* The corpus's own recurring motif: an object, its projection, and the measured
   gap between them. Used as the section rule rather than a plain hairline. */
.gaprule {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 44px 0 32px;
}
.gaprule::before,
.gaprule::after {
  content: "";
  height: 1px;
  background: var(--rule);
  flex: 1;
}
.gaprule::before { flex: 0 0 56px; }
.gaprule span {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-mute);
  white-space: nowrap;
}

/* ---- stats ------------------------------------------------------------------- */

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(116px, 1fr));
  gap: 1px;
  background: var(--rule);
  border: 1px solid var(--rule);
  border-radius: 3px;
  overflow: hidden;
  margin: 32px 0 0;
}
.stat { background: var(--raised); padding: 14px 16px 15px; }
.stat b {
  display: block;
  font-family: var(--mono);
  font-size: 25px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.stat span {
  font-family: var(--ui);
  font-size: 11.5px;
  color: var(--ink-mute);
  letter-spacing: 0.02em;
}

/* ---- controls ---------------------------------------------------------------- */

.controls {
  position: sticky;
  top: 0;
  z-index: 5;
  background: color-mix(in srgb, var(--ground) 92%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--rule);
  padding: 14px 0 13px;
  margin: 0 0 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
}

.search {
  font-family: var(--ui);
  font-size: 14px;
  color: var(--ink);
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: 7px 11px;
  min-width: 210px;
  flex: 1 1 210px;
}
.search::placeholder { color: var(--ink-mute); }
.search:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

.chips { display: flex; flex-wrap: wrap; gap: 6px; }

.chip {
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.03em;
  color: var(--ink-soft);
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: 999px;
  padding: 4px 11px;
  cursor: pointer;
  transition: border-color 120ms, color 120ms;
}
.chip:hover { border-color: var(--ink-mute); }
.chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.chip[aria-pressed="true"] {
  color: var(--ground);
  background: var(--ink);
  border-color: var(--ink);
}
.chip .n { opacity: 0.55; margin-left: 5px; font-variant-numeric: tabular-nums; }

.count {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-mute);
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}

/* ---- findings ---------------------------------------------------------------- */

.list { display: flex; flex-direction: column; gap: 10px; }

.card {
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: 3px;
  border-left: 2px solid var(--edge, var(--rule));
  overflow: hidden;
}
.card[data-status="read"] { --edge: var(--read); }
.card[data-status="tension"] { --edge: var(--tension); }
.card[data-status="conjecture"] { --edge: var(--conjecture); }
.card[hidden] { display: none; }

.card > summary {
  cursor: pointer;
  padding: 16px 20px;
  list-style: none;
  display: grid;
  gap: 7px;
}
.card > summary::-webkit-details-marker { display: none; }
.card > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

.idline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 9px;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--ink-mute);
}

.tag {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2.5px 7px;
  border-radius: 2px;
}
.tag.read { color: var(--read); background: var(--accent-soft); }
.tag.tension { color: var(--tension); background: var(--tension-soft); }
.tag.conjecture { color: var(--conjecture); background: var(--conjecture-soft); }
.tag.impl {
  color: var(--ink-soft);
  background: var(--rule-soft);
  text-transform: none;
  letter-spacing: 0.02em;
}

.card h3 {
  font-family: var(--prose);
  font-size: 19.5px;
  font-weight: 600;
  line-height: 1.32;
  letter-spacing: -0.011em;
  margin: 0;
  text-wrap: balance;
  color: var(--ink);
}

.struct {
  font-family: var(--ui);
  font-size: 13.5px;
  color: var(--ink-soft);
  margin: 0;
  max-width: 76ch;
}

.doms { display: flex; flex-wrap: wrap; gap: 5px; }
.dom {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-mute);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 1.5px 6px;
}

.body {
  padding: 4px 20px 22px;
  border-top: 1px solid var(--rule-soft);
  margin-top: 4px;
}

.field { margin: 18px 0 0; }
.field > h4 {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin: 0 0 6px;
  font-weight: 500;
}
.field > p {
  margin: 0;
  max-width: 74ch;
  font-size: 16.5px;
  color: var(--ink);
}
.field.seed > p { color: var(--ink-soft); }
.field.seed {
  background: var(--accent-soft);
  border-radius: 3px;
  padding: 14px 16px 15px;
}
.field.open > p { color: var(--ink); }
.field.open {
  background: var(--tension-soft);
  border-radius: 3px;
  padding: 14px 16px 15px;
}

.srcs { margin: 0; padding: 0; list-style: none; display: grid; gap: 5px; }
.srcs li {
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.5;
  color: var(--ink-soft);
  padding-left: 15px;
  position: relative;
  overflow-wrap: anywhere;
}
.srcs li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.62em;
  width: 8px;
  height: 1px;
  background: var(--ink-mute);
}

/* ---- shapes ------------------------------------------------------------------ */

.shapes { display: grid; gap: 1px; background: var(--rule); border: 1px solid var(--rule); border-radius: 3px; overflow: hidden; }
.shape { background: var(--raised); padding: 16px 20px 17px; display: grid; gap: 7px; }
.shape .n {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
.shape .s { font-size: 17px; font-weight: 600; margin: 0; letter-spacing: -0.008em; text-wrap: balance; }
.shape .w { font-family: var(--ui); font-size: 13.5px; color: var(--ink-soft); margin: 0; max-width: 80ch; }
.shape .refs { display: flex; flex-wrap: wrap; gap: 5px; }
.shape .refs code {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--ink-mute);
  border: 1px solid var(--rule);
  border-radius: 2px;
  padding: 1.5px 6px;
}
.shape[data-multi="1"] { border-left: 2px solid var(--accent); }

.foot {
  font-family: var(--ui);
  font-size: 13px;
  color: var(--ink-mute);
  max-width: 74ch;
  margin: 14px 0 0;
}
.foot code { font-family: var(--mono); font-size: 12px; }

.empty {
  font-family: var(--ui);
  font-size: 14px;
  color: var(--ink-mute);
  padding: 40px 0;
  text-align: center;
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

@media (max-width: 620px) {
  .wrap { padding: 0 18px 64px; }
  .mast { padding-top: 40px; }
  body { font-size: 16px; }
  .count { margin-left: 0; }
}
"""

JS = """
const cards = Array.from(document.querySelectorAll('.card'));
const search = document.getElementById('q');
const count = document.getElementById('count');
const chips = Array.from(document.querySelectorAll('.chip'));
const active = { status: new Set(), domain: new Set() };

function apply() {
  const q = search.value.trim().toLowerCase();
  let shown = 0;
  for (const card of cards) {
    const okStatus = active.status.size === 0 || active.status.has(card.dataset.status);
    const doms = card.dataset.domains.split(' ');
    const okDomain = active.domain.size === 0 || doms.some((d) => active.domain.has(d));
    const okText = q === '' || card.dataset.hay.includes(q);
    const show = okStatus && okDomain && okText;
    card.hidden = !show;
    if (show) shown += 1;
  }
  count.textContent = shown + (shown === 1 ? ' finding' : ' findings');
}

for (const chip of chips) {
  chip.addEventListener('click', () => {
    const set = active[chip.dataset.kind];
    const value = chip.dataset.value;
    const on = chip.getAttribute('aria-pressed') === 'true';
    if (on) { set.delete(value); } else { set.add(value); }
    chip.setAttribute('aria-pressed', String(!on));
    apply();
  });
}

search.addEventListener('input', apply);
apply();
"""


def para(text: str | None) -> str:
    return html.escape((text or "").strip())


def render(data: dict[str, Any]) -> str:
    stats = data["stats"]
    counts = data["status_counts"]

    stat_cells = "".join(
        f'<div class="stat"><b>{value}</b><span>{label}</span></div>'
        for label, value in [
            ("findings", stats["findings"]),
            ("recurring shapes", stats["shapes"]),
            ("units read", stats["read"]),
            ("sources mapped", stats["records"]),
            ("sources decomposed", stats["decomposed"]),
        ]
    )

    status_chips = "".join(
        f'<button class="chip" type="button" data-kind="status" data-value="{key}" '
        f'aria-pressed="false" title="{html.escape(STATUS_NOTE[key])}">{key}'
        f'<span class="n">{counts.get(key, 0)}</span></button>'
        for key in ("read", "tension", "conjecture")
        if counts.get(key)
    )

    domain_chips = "".join(
        f'<button class="chip" type="button" data-kind="domain" data-value="{html.escape(name)}" '
        f'aria-pressed="false">{html.escape(name.replace("_", " "))}'
        f'<span class="n">{n}</span></button>'
        for name, n in data["domains"]
    )

    cards = []
    for finding in data["findings"]:
        doms = finding.get("domains") or []
        hay = " ".join(
            [
                finding.get("finding_id", ""),
                finding.get("title", ""),
                finding.get("structure", ""),
                finding.get("correspondence", ""),
                finding.get("what_it_buys", ""),
                finding.get("agent_seed", ""),
                finding.get("open_question", "") or "",
                " ".join(doms),
                " ".join(finding.get("sources_read") or []),
            ]
        ).lower()

        fields = [
            ("correspondence", "The correspondence", finding.get("correspondence"), ""),
            ("buys", "What it buys", finding.get("what_it_buys"), ""),
            ("open", "Open question", finding.get("open_question"), " open"),
            ("impl", "Implemented as", finding.get("implemented_as"), ""),
        ]
        body = "".join(
            f'<div class="field{extra}"><h4>{label}</h4><p>{para(value)}</p></div>'
            for _key, label, value, extra in fields
            if value
        )

        sources = finding.get("sources_read") or []
        if sources:
            items = "".join(f"<li>{html.escape(s)}</li>" for s in sources)
            body += f'<div class="field"><h4>Sources read</h4><ul class="srcs">{items}</ul></div>'

        seed = finding.get("agent_seed")
        if seed:
            body += f'<div class="field seed"><h4>Agent seed</h4><p>{para(seed)}</p></div>'

        impl_tag = '<span class="tag impl">implemented</span>' if finding.get("implemented_as") else ""
        dom_tags = "".join(f'<span class="dom">{html.escape(d.replace("_", " "))}</span>' for d in doms)

        cards.append(
            f'<details class="card" data-status="{finding["status"]}" '
            f'data-domains="{html.escape(" ".join(doms))}" data-hay="{html.escape(hay)}">'
            f"<summary>"
            f'<div class="idline"><span class="tag {finding["status"]}">{finding["status"]}</span>'
            f'<span>{html.escape(finding["finding_id"])}</span>{impl_tag}</div>'
            f'<h3>{html.escape(finding["title"])}</h3>'
            f'<p class="struct">{para(finding.get("structure"))}</p>'
            f'<div class="doms">{dom_tags}</div>'
            f"</summary>"
            f'<div class="body">{body}</div>'
            f"</details>"
        )

    shapes = []
    for shape in data["shapes"]:
        refs = shape.get("instances") or []
        multi = "1" if len(refs) > 1 else "0"
        ref_html = "".join(f"<code>{html.escape(r)}</code>" for r in refs)
        plural = "instance" if len(refs) == 1 else "instances"
        shapes.append(
            f'<div class="shape" data-multi="{multi}">'
            f'<div class="n">{len(refs)} {plural}</div>'
            f'<p class="s">{html.escape(shape["shape"])}</p>'
            f'<p class="w">{para(shape.get("why_it_matters"))}</p>'
            f'<div class="refs">{ref_html}</div>'
            f"</div>"
        )

    return f"""<title>Structural findings — labrat corpus</title>
<style>{CSS}</style>
<div class="wrap">
  <header class="mast">
    <p class="eyebrow">labrat · dxap-knowledge · exploratory</p>
    <h1>Patterns that showed up in more than one field</h1>
    <p class="standfirst">Every entry here came from opening a source, not from adding one to a
    bibliography. A finding qualifies when the same structure turns up in two or more domains that
    do not cite each other — and each carries an <em>agent seed</em>, written to hand to a coding
    agent as direction when building in that area.</p>
    <div class="stats">{stat_cells}</div>
  </header>

  <div class="gaprule"><span>Findings</span></div>

  <div class="controls">
    <input id="q" class="search" type="search" placeholder="Search titles, mechanisms, seeds…"
           aria-label="Search findings" autocomplete="off" />
    <div class="chips">{status_chips}</div>
    <span id="count" class="count"></span>
  </div>
  <div class="controls" style="position:static;border:0;padding-top:0;margin-bottom:22px;background:none;backdrop-filter:none;">
    <div class="chips">{domain_chips}</div>
  </div>

  <div class="list">{"".join(cards)}</div>
  <p class="empty" hidden>Nothing matches those filters.</p>

  <div class="gaprule"><span>Recurring shapes</span></div>
  <p class="standfirst" style="margin-bottom:24px;">The meta-layer: shapes seen more than once are
  marked. These are what the corpus is actually accumulating — a finding is one observation, a shape
  is the thing worth carrying into the next problem.</p>
  <div class="shapes">{"".join(shapes)}</div>

  <div class="gaprule"><span>How to read this</span></div>
  <p class="foot"><strong>read</strong> — taken from primary material opened in this repository.
  <strong>tension</strong> — two read sources make claims that may not be mutually consistent; a
  tension must state its open question or validation refuses it. <strong>conjecture</strong> — a
  pattern proposed from what was read, not itself asserted in any source.</p>
  <p class="foot">Generated from <code>profiles/dxap-knowledge/knowledge/structural_findings.yaml</code>,
  which stays the source of truth. Regenerate with <code>make review</code>. The same data is
  queryable from the command line: <code>python scripts/knowledge.py findings --verbose</code>.</p>
</div>
<script>{JS}</script>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the structural findings as one page")
    parser.add_argument("--knowledge-dir", default=str(DEFAULT_KNOWLEDGE))
    parser.add_argument("--corpus-dir", default=str(DEFAULT_CORPUS))
    parser.add_argument("--out", default="review.html")
    args = parser.parse_args()

    data = collect(Path(args.knowledge_dir), Path(args.corpus_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out} — {data['stats']['findings']} findings, {data['stats']['shapes']} shapes")


if __name__ == "__main__":
    main()
