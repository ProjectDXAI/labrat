# Phase prompt — corpus scouting round

Shared by Claude Code (`/corpus-round`) and Codex (`$corpus-scout`). The runtime decides *what* to look for; you supply the facts and the evidence.

## The loop

```bash
# 1. what state is the corpus in
python scripts/corpus.py status
python scripts/corpus.py frontier --limit 15

# 2. open a bounded round (mode: expand | verify | acquire)
python scripts/corpus.py round open --mode expand --bucket market_microstructure --limit 15

# 3. read the brief, do the work, fill in the findings file
#    corpus/rounds/round-NNN/request.md
#    corpus/rounds/round-NNN/findings.yaml

# 4. merge, score, and report
python scripts/corpus.py round close
python scripts/corpus.py report
```

When the round was opened by the runtime (a leased candidate rather than a hand-run round), close it by re-running the candidate instead of `round close` — the runner merges the findings and scores the round in one step:

```bash
python scripts/run_experiment.py --candidate <artifact_dir>/candidate.json --output <artifact_dir>/result.json
```

## What each mode asks of you

**expand** — For each target in the brief: establish the bibliographic identity (title, authors, year, venue), the `form`, an estimated page count, a priority (1-5), the rights status, and — this is the part that keeps the loop alive — the works *it* points at, as `refs`. A round that adds entries with no refs starves the next round's frontier.

Use `resolves:` to name the frontier labels an entry closes. Labels are matched heuristically too, but declaring them is exact.

**verify** — Resolve rights. Read the actual licence page, the publisher permission, or the docs repository's LICENSE file. Then record:

```yaml
rights:
  status: cc_by_nc_sa            # from `python scripts/corpus.py vocab`
  confidence: confirmed
  evidence: "https://…"          # the page you actually read
  checked_at: "YYYY-MM-DD"
  notes: "quote the operative sentence"
```

**acquire** — Record where a legitimately obtained copy lives, in `acquisition.copy_path`. Only for entries that are already manifest-eligible.

## Rules that are not negotiable

- **Confirmed means you read it.** `confidence: confirmed` without an `evidence` URL is rejected at merge. Never confirm from memory or inference.
- **A silent licence page is `all_rights_reserved`, confirmed** — not `unknown`. Say what you checked in `notes`. That answer is a real result and it retires the entry from the verify queue.
- **Free to read is not licensed.** An author-hosted PDF is `author_hosted_free` → `reference_only`, however freely it is served.
- **Confidential material is `proprietary_confidential`, `status: rejected`.** Do not acquire it, do not link to a copy of it, do not ingest it. Record the entry so the exclusion is remembered.
- **Do not invent identifiers.** Leave `isbn`, `doi`, and `url` null unless you read them off the source. A wrong ISBN is worse than a missing one.
- **Estimate page counts, and say so in notes if you are guessing.** They drive coverage accounting, not billing.

## What a good round looks like

- Targets worked in the brief's order, or an explicit note on why not.
- New entries carry refs, so the frontier grows as it shrinks.
- Rights tags moved in at least one direction with evidence attached.
- Cross-bucket refs recorded where they genuinely exist — `bridge_discovery` is a decisive challenge and it cannot be faked by volume.
- Findings written to the round's `findings.yaml`, nothing hand-edited in `corpus/bibliography.yaml`.

## When to stop

`python scripts/corpus.py status` reports a per-bucket saturation state. Two consecutive *expansion* rounds with nothing new and an empty frontier means that bucket is done at this depth: switch channel or move to another bucket. Verification rounds never count toward saturation.
