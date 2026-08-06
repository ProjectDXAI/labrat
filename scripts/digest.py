#!/usr/bin/env python3
"""Source-text digest: decide how much of the corpus a decision actually needs to read.

`knowledge.py retrieve` answers *which claims apply*. It returns concept cards, which
are compressed by construction. This module answers the next question: for each card in
that packet, how much of the underlying source do we put in front of the model?

The lazy answer is "all of it" and the cheap answer is "none of it". Both are wrong in
the same way: they refuse to look at the packet. A card whose anchor nobody opened is
worth the page it came from. A card that is uncontested, read, and confidently held is
worth its own summary and nothing more.

So each anchor is offered at four tiers:

    0 card     the concept card's own fields; no source text
    1 note     the reading note recorded on that unit when someone read it
    2 excerpt  quoted passage text from the held pages, capped
    3 unit     every page the unit spans

Three things decide the tier, in this order.

**Rights cap it.** A `reference_only` source can be cited and paraphrased from our own
notes; its text does not go in the packet. This is a ceiling, not a preference, and no
trigger can lift it.

**Triggers raise it.** Escalation is never a vibe. Each one names a condition that the
card text demonstrably cannot settle -- a live contradiction, an anchor nobody opened,
confidence below the bar, query terms that appear in the source but not the card -- and
every fired trigger is written into the digest next to the passage it paid for.

**The budget allocates it.** Given tiers with costs and values, picking the top-k cards
and reading them fully is the wrong shape: it spends everything on the first two anchors
and abstains on the rest. This is a multiple-choice knapsack -- at most one tier per
anchor, maximise total value under a token ceiling -- and it will happily buy four notes
instead of one full unit when that is the better packet.

There are two control arms, and they exist so the policy has to justify itself:
`--arm never` (cards only) and `--arm always` (every anchor at its rights ceiling). If
the policy arm does not land closer to `always` at a fraction of the cost, the triggers
are not earning their tokens and should be changed.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------
# Tiers and rights
# --------------------------------------------------------------------------------------

TIER_CARD = 0
TIER_NOTE = 1
TIER_EXCERPT = 2
TIER_UNIT = 3
TIER_SOURCE = 4

TIER_NAMES = {
    TIER_CARD: "card",
    TIER_NOTE: "note",
    TIER_EXCERPT: "excerpt",
    TIER_UNIT: "unit",
    TIER_SOURCE: "source",
}
TIER_ORDER = [TIER_NAMES[i] for i in sorted(TIER_NAMES)]

# What each tier is worth relative to the card alone. Strongly diminishing: the whole
# unit is rarely twice the packet a well-chosen excerpt is, and it costs far more. The
# source tier barely gains over the unit on value alone -- it is not chosen for its score,
# it is chosen because someone said this source comes in whole.
TIER_GAIN = {
    TIER_CARD: 1.0,
    TIER_NOTE: 1.30,
    TIER_EXCERPT: 1.75,
    TIER_UNIT: 1.95,
    TIER_SOURCE: 2.05,
}

# Two different questions get called "rights", and conflating them is how a local
# reading tool ends up refusing to show you a paper sitting on your own disk.
#
# `corpus.py` answers the redistribution question: may this text go into a corpus, a
# manifest, a published artifact, a model someone deploys. CC BY-NC and "subscription
# required" bite hard there, and that engine is right to be strict.
#
# This module answers a different one: how much of a source you already hold should be
# put in front of a model, locally, to help you read it. A licence restricting
# redistribution does not restrict reading, so `personal` mode does not cap on it.
#
# `redistribution` mode exists for when a digest is going to leave the machine -- pasted
# into something published, shipped with a product, used to build a dataset. It restores
# the corpus ceilings. Every served passage carries its rights class either way, so the
# constraint is recorded and can be re-applied to anything that gets published later.
REDISTRIBUTION_CEILING = {
    "ingest_full": TIER_SOURCE,
    "ingest_attribution": TIER_SOURCE,
    "ingest_share_alike": TIER_SOURCE,
    "ingest_noncommercial": TIER_SOURCE,
    "ingest_check_terms": TIER_NOTE,
    "reference_only": TIER_NOTE,
    "needs_review": TIER_NOTE,
    "excluded": TIER_CARD,
}

# Personal reading has one real limit, and it is not a copyright ceiling. `excluded` is
# `proprietary_confidential`: leaked, NDA-bound, or otherwise material the corpus engine
# says we should not be holding at all. That stays out whatever mode is set, because the
# objection to it was never about redistribution.
PERSONAL_CEILING = {name: TIER_SOURCE for name in REDISTRIBUTION_CEILING}
PERSONAL_CEILING["excluded"] = TIER_CARD

RIGHTS_MODES = {"personal": PERSONAL_CEILING, "redistribution": REDISTRIBUTION_CEILING}

# Kept as the name the rest of the module reads, so a mode swap is one lookup.
RIGHTS_CEILING = REDISTRIBUTION_CEILING

# Anything the corpus vocabulary grows that this module has not been taught falls to the
# card tier under redistribution rules. Failing closed is right when the question is what
# may be published; `unmapped_rights_classes` turns the silence into a reportable fact.
UNMAPPED_CEILING = TIER_CARD


def unmapped_rights_classes() -> list[str]:
    """Use classes the corpus can emit and this module has no ceiling for."""
    try:
        import corpus as corpus_module
    except Exception:  # pragma: no cover - digest is usable without the corpus engine
        return []
    known = {
        row.get("use_class")
        for row in getattr(corpus_module, "RIGHTS_STATUS", {}).values()
        if row.get("use_class")
    }
    return sorted(known - set(RIGHTS_CEILING))


DEFAULT_DIGEST_POLICY: dict[str, Any] = {
    # A modern context window is the real ceiling, not a number chosen to feel careful.
    # 60k leaves a long-context model most of its window for the reasoning it was given
    # the material for. Lower it when the packet feeds something smaller.
    "budget_tokens": 60000,
    # Reading locally, not publishing. Set `redistribution` when the digest is going
    # somewhere the licence terms actually apply.
    "rights_mode": "personal",
    "confidence_floor": 0.6,
    # An excerpt used to be 1400 characters, which is under a third of one extracted page
    # and reads as a teaser rather than evidence. Roughly five pages is a passage someone
    # could actually adjudicate a contradiction with.
    "excerpt_chars": 20000,
    # A trigger raises the floor for one anchor; it never lowers it and never lifts the
    # rights ceiling. Weight is added to the anchor's value so the knapsack prefers to
    # spend on anchors that actually need the text.
    "triggers": {
        "contested": {"floor": TIER_EXCERPT, "weight": 0.9},
        "unread_anchor": {"floor": TIER_EXCERPT, "weight": 0.8},
        "low_confidence": {"floor": TIER_EXCERPT, "weight": 0.5},
        "lexical_miss": {"floor": TIER_EXCERPT, "weight": 0.6},
        "load_bearing": {"floor": TIER_EXCERPT, "weight": 0.4},
    },
}


def wants_full_text(entry: dict[str, Any] | None, requested: set[str]) -> bool:
    """Whether this source is one we have said should come in whole.

    A trigger can never reach the source tier on its own. Escalation answers "the card is
    not enough here"; it has no opinion on whether a 200,000-token course should be paged
    in. That is an operator decision, so it has to be stated: `--full <id>` on the command,
    `--full-all` for everything the licences allow, or `digest_full_text: true` on the
    bibliography entry for a source that should always arrive complete.
    """
    if not entry:
        return False
    if entry.get("id") in requested or "*" in requested:
        return True
    flag = entry.get("digest_full_text")
    if flag is None:
        flag = (entry.get("digest") or {}).get("full_text")
    return bool(flag)


def estimate_tokens(text: str) -> int:
    """Four characters to a token is close enough to allocate against and cheap to run."""
    return max(1, math.ceil(len(text or "") / 4))


# --------------------------------------------------------------------------------------
# Passage store
# --------------------------------------------------------------------------------------


def passages_path(corpus_dir: Path) -> Path:
    return corpus_dir / "passages" / "passages.jsonl"


def load_passages(corpus_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Extracted page text, grouped by entry. Absent is normal: a lab may hold no PDFs."""
    path = passages_path(corpus_dir)
    if not path.exists():
        return {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_id = row.get("entry_id")
            if entry_id and row.get("text"):
                grouped.setdefault(entry_id, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: r.get("page") or 0)
    return grouped


PAGE_RANGE = re.compile(r"pp?\.\s*(\d+)\s*(?:-|–|—|to)\s*(\d+)", re.IGNORECASE)
PAGE_SINGLE = re.compile(r"pp?\.\s*(\d+)", re.IGNORECASE)


def locator_pages(locator: str | None) -> tuple[int, int] | None:
    """`section 1, pp. 1-2` -> (1, 2). Returns None when the locator names no pages."""
    if not locator:
        return None
    ranged = PAGE_RANGE.search(locator)
    if ranged:
        low, high = int(ranged.group(1)), int(ranged.group(2))
        return (low, high) if low <= high else (high, low)
    single = PAGE_SINGLE.search(locator)
    if single:
        page = int(single.group(1))
        return (page, page)
    return None


def unit_passages(
    entry_id: str,
    unit: dict[str, Any] | None,
    passages: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """The extracted pages a unit covers. With no page locator, the whole entry is fair game."""
    rows = passages.get(entry_id) or []
    if not rows:
        return []
    span = locator_pages((unit or {}).get("locator"))
    if not span:
        return rows
    low, high = span
    hit = [row for row in rows if low <= (row.get("page") or 0) <= high]
    return hit or rows


# --------------------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------------------


def entry_passages(
    entry_id: str, passages: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Every extracted page of an entry, whatever any unit says."""
    return passages.get(entry_id) or []


def rights_ceiling(
    entry: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    mode: str = "personal",
) -> tuple[int, str]:
    """The tier this anchor may not exceed, and the class that set it.

    Under `redistribution`, two records disagree in practice -- the bibliography's derived
    rights and the class stamped on each extracted page -- and the stricter wins, because
    the reason they disagree is usually that one has not been re-checked. Under
    `personal` the only thing that caps anything is material we should not be holding.
    """
    table = RIGHTS_MODES.get(mode, PERSONAL_CEILING)
    unmapped = UNMAPPED_CEILING if mode == "redistribution" else TIER_SOURCE
    derived = ((entry or {}).get("derived_rights") or {}).get("use_class") or "unknown"
    ceiling = table.get(derived, unmapped)
    binding = derived
    for row in rows:
        row_class = row.get("use_class") or "unknown"
        row_ceiling = table.get(row_class, unmapped)
        if row_ceiling < ceiling:
            ceiling, binding = row_ceiling, row_class
    return ceiling, binding


def fire_triggers(
    card: dict[str, Any],
    anchor_key: str,
    unit: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    packet: dict[str, Any],
    query_terms: set[str],
    anchor_card_count: dict[str, int],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Every reason this anchor needs more than the card, each one named and evidenced."""
    fired: list[dict[str, Any]] = []
    config = policy["triggers"]
    packet_ids = {row["concept_id"] for row in packet.get("cards") or []}

    def add(name: str, why: str) -> None:
        spec = config.get(name) or {}
        fired.append({
            "trigger": name,
            "why": why,
            "raises_floor_to": TIER_NAMES[spec.get("floor", TIER_CARD)],
            "weight": spec.get("weight", 0.0),
        })

    contested = sorted(set(card.get("contradicting_concept_ids") or []) & packet_ids)
    if contested:
        add("contested", f"contradicted inside this packet by {', '.join(contested)}; "
                         "the cards state both positions and settle neither")

    if unit is None or unit.get("read_status") not in {"read", "compiled"}:
        add("unread_anchor", "nobody opened this unit, so the card is a claim about a "
                             "source rather than a reading of one")

    confidence = card.get("confidence")
    floor = policy["confidence_floor"]
    if confidence is not None and float(confidence) < float(floor):
        add("low_confidence", f"confidence {float(confidence):.2f} is below the {floor} bar")

    if query_terms and rows:
        card_terms = set(re.findall(r"[a-z0-9]+", json.dumps(card).lower()))
        missing = query_terms - card_terms
        if missing:
            body = " ".join((row.get("text") or "") for row in rows[:12]).lower()
            found = sorted(term for term in missing if term in body)
            if found:
                add("lexical_miss", f"the context asks about {', '.join(found[:5])}, which "
                                    "appears in the source and not in the card")

    if anchor_card_count.get(anchor_key, 0) >= 2:
        add("load_bearing", f"{anchor_card_count[anchor_key]} cards in this packet rest on "
                            "this one anchor, so an error here is not contained")

    return fired


def build_candidates(
    packet: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    passages: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
    policy: dict[str, Any],
    full_requests: set[str] | None = None,
) -> list[dict[str, Any]]:
    """One candidate per (card, anchor), carrying every tier it could legally be served at."""
    cards = packet.get("cards") or []
    query_terms = {
        term
        for term in re.findall(r"[a-z0-9]+", json.dumps(context).lower())
        if len(term) > 3
    }

    anchor_card_count: dict[str, int] = {}
    for card in cards:
        for raw in card.get("source_passage_ids") or []:
            ref = _ref(raw)
            anchor_card_count[_key(ref)] = anchor_card_count.get(_key(ref), 0) + 1

    candidates: list[dict[str, Any]] = []
    for card in cards:
        for raw in card.get("source_passage_ids") or []:
            ref = _ref(raw)
            source_id, anchor = ref["source_id"], ref["anchor"]
            entry = sources.get(source_id)
            unit = None
            for row in (entry or {}).get("units") or []:
                if row.get("unit_id") == anchor:
                    unit = row
                    break

            all_rows = entry_passages(source_id, passages)
            rows = unit_passages(source_id, unit, passages)
            # A locator that names no pages falls back to the whole entry. That is often
            # the only sensible read, but it means the "unit" tier is not really a unit,
            # and three units of one paper can each claim the same pages.
            locator_unresolved = bool(rows) and locator_pages((unit or {}).get("locator")) is None
            full_text = wants_full_text(entry, full_requests or set())
            ceiling, binding_class = rights_ceiling(
                entry, all_rows or rows, policy.get("rights_mode", "personal")
            )
            triggers = fire_triggers(
                card, _key(ref), unit, rows, packet, query_terms, anchor_card_count, policy
            )

            options = _tier_options(
                card, unit, rows, all_rows, ceiling, policy, full_text,
                locator_resolved=not locator_unresolved,
            )
            floor = TIER_CARD
            for trigger in triggers:
                want = policy["triggers"].get(trigger["trigger"], {}).get("floor", TIER_CARD)
                floor = max(floor, want)

            best_available = max(option["tier"] for option in options)
            wanted = min(floor, ceiling)

            candidates.append({
                "concept_id": card["concept_id"],
                "concept_name": card.get("canonical_name"),
                "source_id": source_id,
                "anchor": anchor,
                "anchor_key": _key(ref),
                "title": (entry or {}).get("title"),
                "read": bool(unit and unit.get("read_status") in {"read", "compiled"}),
                "rights_class": binding_class,
                "rights_ceiling": TIER_NAMES[ceiling],
                "requested_floor": TIER_NAMES[floor],
                "effective_floor": TIER_NAMES[min(floor, ceiling)],
                "floor_refused_by_rights": floor > ceiling,
                # The licence allows the text, a trigger asked for it, and the lab does
                # not hold it. That is a fetch instruction, not a policy decision.
                "starved": wanted > best_available and floor <= ceiling,
                "best_available": TIER_NAMES[best_available],
                "locator_unresolved": locator_unresolved,
                "full_text_requested": full_text,
                # Anchors resolving to the same pages are the same tokens. Buying them
                # twice is the most expensive mistake this allocator could make.
                "text_key": f"{source_id}:{','.join(str(r.get('page')) for r in rows)}",
                "base_value": float(card.get("score") or 0.0) + 0.1,
                "trigger_weight": sum(t["weight"] for t in triggers),
                "triggers": triggers,
                "options": options,
                "pages_available": len(rows),
            })

    return _dedupe_shared_text(candidates)


def _dedupe_shared_text(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stop the allocator paying twice for one passage.

    Ninety-four of this corpus's hundred-and-five units carry a locator with no page
    numbers, and every anchor on an entry served whole offers that entire entry. Either
    way two anchors can hold byte-identical text, and nothing in a knapsack stops it
    buying both. Keying on the text rather than on the unit catches it at every tier: the
    anchor with the most at stake carries the passage, the others drop that option and
    record who is carrying it for them. Text they do not share, such as their own reading
    note, they keep.
    """
    holders: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        for option in candidate["options"]:
            if option.get("text"):
                holders.setdefault(option["text"], []).append(candidate)

    carrier = {
        text: max(group, key=lambda c: c["base_value"] + c["trigger_weight"])
        for text, group in holders.items()
        if len(group) > 1
    }

    for candidate in candidates:
        kept = []
        for option in candidate["options"]:
            owner = carrier.get(option.get("text") or "")
            if owner is not None and owner is not candidate:
                candidate["shares_text_with"] = owner["concept_id"]
                continue
            kept.append(option)
        candidate["options"] = kept
        candidate["best_available"] = TIER_NAMES[max(o["tier"] for o in kept)]
    return candidates


def _ref(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        source_id, _, anchor = raw.partition("#")
        return {"source_id": source_id.strip(), "anchor": anchor.strip() or None}
    raw = dict(raw or {})
    return {"source_id": (raw.get("source_id") or "").strip(), "anchor": raw.get("anchor")}


def _key(ref: dict[str, Any]) -> str:
    return f"{ref['source_id']}#{ref['anchor']}" if ref.get("anchor") else ref["source_id"]


def _tier_options(
    card: dict[str, Any],
    unit: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    ceiling: int,
    policy: dict[str, Any],
    full_text: bool,
    locator_resolved: bool = True,
) -> list[dict[str, Any]]:
    """Every tier this anchor can actually be served at, with its real token cost.

    A tier the material cannot support is dropped rather than costed at zero: an unread
    unit has no note, and an entry with no extracted pages has no excerpt. Offering them
    would let the knapsack buy emptiness cheaply.
    """
    options = [{"tier": TIER_CARD, "text": None, "tokens": 0}]

    note = (unit or {}).get("notes")
    if note and ceiling >= TIER_NOTE:
        options.append({"tier": TIER_NOTE, "text": note.strip(), "tokens": estimate_tokens(note)})

    if rows and ceiling >= TIER_EXCERPT:
        cap = int(policy["excerpt_chars"])
        joined = "\n\n".join((row.get("text") or "").strip() for row in rows)
        excerpt = joined[:cap].rsplit(" ", 1)[0] if len(joined) > cap else joined
        if excerpt:
            options.append({
                "tier": TIER_EXCERPT,
                "text": excerpt,
                "tokens": estimate_tokens(excerpt),
                "pages": [row.get("page") for row in rows[:3]],
            })
        # `unit` means the pages this unit names. When the locator names none -- and
        # ninety-four of this corpus's hundred-and-five units name none -- the span behind
        # it is the whole entry, and serving that as a "unit" is how a card claiming to
        # rest on one empirical section quietly arrives carrying fifty-four pages. The
        # excerpt still gives a usable read of it; the whole thing needs asking for.
        if ceiling >= TIER_UNIT and locator_resolved and len(joined) > len(excerpt):
            options.append({
                "tier": TIER_UNIT,
                "text": joined,
                "tokens": estimate_tokens(joined),
                "pages": [row.get("page") for row in rows],
            })

    # The whole source, only when someone asked for it by name and the licence allows it.
    if full_text and ceiling >= TIER_SOURCE and all_rows:
        whole = "\n\n".join((row.get("text") or "").strip() for row in all_rows)
        biggest = max((o["tokens"] for o in options), default=0)
        if estimate_tokens(whole) > biggest:
            options.append({
                "tier": TIER_SOURCE,
                "text": whole,
                "tokens": estimate_tokens(whole),
                "pages": [row.get("page") for row in all_rows],
            })
    return options


# --------------------------------------------------------------------------------------
# Allocation
# --------------------------------------------------------------------------------------


def option_value(candidate: dict[str, Any], option: dict[str, Any]) -> float:
    """What one tier of one anchor is worth to the packet.

    Trigger weight only pays out above the tier that satisfies it. Escalating an anchor
    nobody opened to `note` earns nothing, because there is no note to read.
    """
    tier = option["tier"]
    value = candidate["base_value"] * TIER_GAIN[tier]
    floor_name = candidate["effective_floor"]
    floor = next(k for k, v in TIER_NAMES.items() if v == floor_name)
    if tier >= floor:
        value += candidate["trigger_weight"]
    return value


def allocate(candidates: list[dict[str, Any]], budget_tokens: int) -> dict[str, Any]:
    """Multiple-choice knapsack: at most one tier per anchor, maximise value under budget.

    Costs are bucketed into 50-token cells to keep the table small. The rounding is
    upward, so a plan that fits the table always fits the real budget.
    """
    cell = 50
    # Floor division, with no minimum. Rounding this up to one cell hands out 50 free
    # tokens, which is invisible at a 6000-token budget and the whole budget at zero.
    cells = max(0, budget_tokens // cell)

    # best[c] = value of the best plan using exactly the first n anchors and c cells
    best: list[float] = [0.0] * (cells + 1)
    choice: list[list[int]] = []

    for candidate in candidates:
        options = candidate["options"]
        nxt = [-1.0] * (cells + 1)
        picks = [-1] * (cells + 1)
        for c in range(cells + 1):
            if best[c] < 0:
                continue
            for index, option in enumerate(options):
                cost = math.ceil(option["tokens"] / cell)
                if c + cost > cells:
                    continue
                value = best[c] + option_value(candidate, option)
                if value > nxt[c + cost]:
                    nxt[c + cost] = value
                    picks[c + cost] = index
        best = [v if v >= 0 else -1.0 for v in nxt]
        choice.append(picks)

    # Walk the table back from the best reachable cell.
    end = max((c for c in range(cells + 1) if best[c] >= 0), key=lambda c: best[c], default=0)
    selection: list[int] = [0] * len(candidates)
    cursor = end
    for depth in range(len(candidates) - 1, -1, -1):
        index = choice[depth][cursor] if cursor <= cells else -1
        if index < 0:
            index = 0
        selection[depth] = index
        cursor -= math.ceil(candidates[depth]["options"][index]["tokens"] / cell)
        cursor = max(cursor, 0)
    return {"selection": selection, "value": best[end] if best else 0.0}


def fixed_arm(candidates: list[dict[str, Any]], mode: str) -> list[int]:
    """The control arms. `never` takes the card every time; `always` takes the ceiling."""
    picks = []
    for candidate in candidates:
        if mode == "never":
            picks.append(0)
        else:
            picks.append(len(candidate["options"]) - 1)
    return picks


# --------------------------------------------------------------------------------------
# Digest
# --------------------------------------------------------------------------------------


def digest(
    packet: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    passages: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
    policy: dict[str, Any],
    arm: str = "policy",
    full_requests: set[str] | None = None,
) -> dict[str, Any]:
    candidates = build_candidates(packet, sources, passages, context, policy, full_requests)
    budget = int(policy["budget_tokens"])

    if arm == "policy":
        picks = allocate(candidates, budget)["selection"]
    else:
        picks = fixed_arm(candidates, arm)

    included: list[dict[str, Any]] = []
    by_tier: dict[str, int] = {name: 0 for name in TIER_NAMES.values()}
    used = 0
    for candidate, index in zip(candidates, picks):
        option = candidate["options"][index]
        used += option["tokens"]
        by_tier[TIER_NAMES[option["tier"]]] += 1
        included.append({
            "concept_id": candidate["concept_id"],
            "concept_name": candidate["concept_name"],
            "source_id": candidate["source_id"],
            "anchor": candidate["anchor"],
            "title": candidate["title"],
            "tier": TIER_NAMES[option["tier"]],
            "tokens": option["tokens"],
            "pages": option.get("pages"),
            "read": candidate["read"],
            "rights_class": candidate["rights_class"],
            "rights_ceiling": candidate["rights_ceiling"],
            "served_because": [t["trigger"] for t in candidate["triggers"]]
            if option["tier"] > TIER_CARD
            else [],
            "locator_unresolved": candidate["locator_unresolved"],
            "shares_text_with": candidate.get("shares_text_with"),
            "refused_by_rights": candidate["floor_refused_by_rights"],
            "text": option.get("text"),
        })

    starved = [
        {
            "anchor": f"{c['source_id']}#{c['anchor']}" if c["anchor"] else c["source_id"],
            "concept_id": c["concept_id"],
            "wanted": c["requested_floor"],
            "best_available": c["best_available"],
            "read": c["read"],
            "triggers": [t["trigger"] for t in c["triggers"]],
        }
        for c in candidates
        if c["starved"]
    ]

    refused = [
        {
            "anchor": f"{c['source_id']}#{c['anchor']}" if c["anchor"] else c["source_id"],
            "wanted": c["requested_floor"],
            "ceiling": c["rights_ceiling"],
            "rights_class": c["rights_class"],
            # Whether lifting the licence would actually buy anything, or whether the
            # lab does not hold the text either way.
            "material_held": c["best_available"] != "card",
            "triggers": [t["trigger"] for t in c["triggers"]],
        }
        for c in candidates
        if c["floor_refused_by_rights"]
    ]

    return {
        "generated_at": packet.get("generated_at"),
        "context_id": packet.get("context_id"),
        "policy": packet.get("policy"),
        "arm": arm,
        "budget_tokens": budget,
        "tokens_used": used,
        "over_budget": used > budget,
        "anchors_considered": len(candidates),
        "by_tier": by_tier,
        "triggers_fired": sorted(
            {t["trigger"] for c in candidates for t in c["triggers"]}
        ),
        "trigger_log": [
            {
                "anchor": f"{c['source_id']}#{c['anchor']}" if c["anchor"] else c["source_id"],
                "concept_id": c["concept_id"],
                **trigger,
            }
            for c in candidates
            for trigger in c["triggers"]
        ],
        "refused_by_rights": refused,
        "starved": starved,
        "full_text_served": sorted(
            {row["source_id"] for row in included if row["tier"] == "source"}
        ),
        # Units whose locator names no pages fall back to the whole entry. Worth knowing:
        # it is the difference between a chosen span and an accident.
        "locators_unresolved": sum(1 for c in candidates if c["locator_unresolved"]),
        "passages": included,
    }


def compare_arms(
    packet: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    passages: dict[str, list[dict[str, Any]]],
    context: dict[str, Any],
    policy: dict[str, Any],
    full_requests: set[str] | None = None,
) -> dict[str, Any]:
    """Run all three arms so the policy has to show it is worth the tokens it spends."""
    runs = {
        arm: digest(packet, sources, passages, context, policy, arm=arm,
                    full_requests=full_requests)
        for arm in ("never", "policy", "always")
    }

    def tiers(run: dict[str, Any]) -> dict[str, str]:
        return {
            f"{row['source_id']}#{row['anchor']}": row["tier"] for row in run["passages"]
        }

    policy_tiers, always_tiers = tiers(runs["policy"]), tiers(runs["always"])
    agree = sum(1 for key, tier in policy_tiers.items() if always_tiers.get(key) == tier)
    total = max(len(policy_tiers), 1)

    always_cost = max(runs["always"]["tokens_used"], 1)
    return {
        "arms": {
            arm: {
                "tokens_used": run["tokens_used"],
                "by_tier": run["by_tier"],
                "over_budget": run["over_budget"],
            }
            for arm, run in runs.items()
        },
        "policy_matches_always": round(agree / total, 4),
        "policy_cost_share": round(runs["policy"]["tokens_used"] / always_cost, 4),
        "verdict": _verdict(
            agree / total,
            runs["policy"]["tokens_used"] / always_cost,
            ceiling_bound=all(
                row["tier"] == row["rights_ceiling"] for row in runs["always"]["passages"]
            )
            and agree == total,
        ),
        "downgraded": [
            {"anchor": key, "policy": tier, "always": always_tiers.get(key)}
            for key, tier in policy_tiers.items()
            if always_tiers.get(key) != tier
        ],
    }


def _verdict(match: float, cost_share: float, ceiling_bound: bool = False) -> str:
    if ceiling_bound:
        return ("Both arms landed in the same place because the rights ceilings bind before the "
                "triggers do. This comparison says nothing about the policy; it says the licences "
                "are what is limiting this packet.")
    if cost_share >= 0.9:
        return ("The policy is spending almost everything the unbounded arm does. Either the "
                "budget is too loose or the triggers fire on nearly every anchor.")
    if match >= 0.6 and cost_share <= 0.5:
        return (f"The policy reaches the same tier on {match:.0%} of anchors for {cost_share:.0%} "
                "of the tokens. The triggers are earning their place.")
    if match < 0.35:
        return (f"The policy agrees with the unbounded arm on only {match:.0%} of anchors. Cheap, "
                "but it is worth checking the disagreements are the ones you would make.")
    return (f"{match:.0%} tier agreement at {cost_share:.0%} of the cost. Reasonable, without "
            "being a clear win either way.")


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def render_digest(result: dict[str, Any]) -> str:
    lines = ["# Source digest", ""]
    lines.append(
        f"Context `{result.get('context_id')}` · arm `{result['arm']}` · "
        f"{result['tokens_used']} of {result['budget_tokens']} tokens · "
        f"{result['anchors_considered']} anchors"
    )
    lines.append("")

    tiers = result["by_tier"]
    lines.append(
        "Tiers served: "
        + ", ".join(f"{count} {name}" for name, count in tiers.items() if count)
    )
    lines.append("")

    if result["refused_by_rights"]:
        lines.append("## Refused by rights")
        lines.append("")
        lines.append("These anchors fired a trigger asking for source text and the licence does not allow it.")
        lines.append("")
        for row in result["refused_by_rights"]:
            held = "text held" if row["material_held"] else "text not held either"
            lines.append(
                f"- `{row['anchor']}` wanted **{row['wanted']}**, capped at **{row['ceiling']}** "
                f"by `{row['rights_class']}` ({', '.join(row['triggers'])}; {held})"
            )
        lines.append("")

    if result.get("starved"):
        lines.append("## Asked for, and not held")
        lines.append("")
        lines.append(
            "A trigger asked for source text on these, the licence allows it, and the lab has "
            "neither a reading note nor extracted pages. Nothing is wrong with the packet; the "
            "material is simply missing, and this is the list to go and fetch."
        )
        lines.append("")
        for row in result["starved"]:
            lines.append(
                f"- `{row['anchor']}` wanted **{row['wanted']}**, best available is "
                f"**{row['best_available']}** ({', '.join(row['triggers'])})"
            )
        lines.append("")

    served = [row for row in result["passages"] if row["tier"] != "card"]
    if served:
        lines.append("## Source material")
        lines.append("")
        for row in served:
            anchor = f"{row['source_id']}#{row['anchor']}" if row["anchor"] else row["source_id"]
            lines.append(f"### `{anchor}` — {row['tier']} ({row['tokens']} tokens)")
            lines.append("")
            lines.append(
                f"Supports `{row['concept_id']}` · {row['title'] or 'untitled'} · "
                f"{'read' if row['read'] else 'never opened'} · rights `{row['rights_class']}`"
            )
            lines.append("")
            if row["served_because"]:
                lines.append(f"Escalated because: {', '.join(row['served_because'])}.")
                lines.append("")
            if row.get("pages"):
                pages = row["pages"]
                shown = f"pp. {pages[0]}–{pages[-1]}" if len(pages) > 1 else f"p. {pages[0]}"
                lines.append(f"_{shown}_")
                lines.append("")
            lines.append("> " + (row["text"] or "").replace("\n", "\n> "))
            lines.append("")

    card_only = [row for row in result["passages"] if row["tier"] == "card"]
    if card_only:
        lines.append("## Served from the card alone")
        lines.append("")
        for row in card_only:
            anchor = f"{row['source_id']}#{row['anchor']}" if row["anchor"] else row["source_id"]
            lines.append(f"- `{row['concept_id']}` via `{anchor}`")
        lines.append("")
        lines.append("No trigger fired on these, so the card is the whole of what was needed.")
        lines.append("")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def _candidate(**over: Any) -> dict[str, Any]:
    base = {
        "concept_id": "KC-X",
        "concept_name": "x",
        "source_id": "src",
        "anchor": "ch1",
        "anchor_key": "src#ch1",
        "title": "t",
        "read": True,
        "rights_class": "ingest_full",
        "rights_ceiling": "unit",
        "requested_floor": "card",
        "effective_floor": "card",
        "floor_refused_by_rights": False,
        "starved": False,
        "best_available": "unit",
        "locator_unresolved": False,
        "full_text_requested": False,
        "text_key": "src:1,2,3",
        "base_value": 1.0,
        "trigger_weight": 0.0,
        "triggers": [],
        "options": [
            {"tier": TIER_CARD, "text": None, "tokens": 0},
            {"tier": TIER_NOTE, "text": "n", "tokens": 100},
            {"tier": TIER_EXCERPT, "text": "e", "tokens": 400},
        ],
        "pages_available": 3,
    }
    base.update(over)
    return base


def self_test() -> dict[str, Any]:
    checks: list[str] = []

    # The rights vocabulary lives in corpus.py. If it grows a class this module has never
    # heard of, that must be a test failure and not a silent drop to card tier.
    unmapped = unmapped_rights_classes()
    assert not unmapped, f"use classes with no tier ceiling: {unmapped}"
    checks.append("rights: every use class the corpus can emit has a ceiling")

    # Reading a paper you hold is not redistributing it, so personal mode does not cap on
    # a licence that only restricts redistribution.
    restricted = {"derived_rights": {"use_class": "reference_only"}}
    assert rights_ceiling(restricted, [], "personal")[0] == TIER_SOURCE
    assert rights_ceiling(restricted, [], "redistribution")[0] == TIER_NOTE
    checks.append("rights: a redistribution licence caps publishing, not local reading")

    # Material we should not hold at all stays out either way. That objection was never
    # about redistribution.
    confidential = {"derived_rights": {"use_class": "excluded"}}
    assert rights_ceiling(confidential, [], "personal")[0] == TIER_CARD
    assert rights_ceiling(confidential, [], "redistribution")[0] == TIER_CARD
    checks.append("rights: confidential material is refused in both modes")

    # Under redistribution the stricter of the two records wins: disagreement means one
    # of them has not been re-checked.
    mixed = rights_ceiling(
        {"derived_rights": {"use_class": "ingest_full"}},
        [{"use_class": "ingest_full"}, {"use_class": "reference_only"}],
        "redistribution",
    )
    assert mixed == (TIER_NOTE, "reference_only"), mixed
    checks.append("rights: publishing takes the stricter of the entry and the page")

    # The allocator spends a tight budget on the anchor that needs it, not the first one.
    cheap = _candidate(concept_id="KC-CHEAP", anchor="a", base_value=1.0, trigger_weight=0.0)
    urgent = _candidate(
        concept_id="KC-URGENT",
        anchor="b",
        base_value=1.0,
        trigger_weight=2.0,
        requested_floor="excerpt",
        effective_floor="excerpt",
        triggers=[{"trigger": "contested", "why": "", "raises_floor_to": "excerpt", "weight": 2.0}],
    )
    plan = allocate([cheap, urgent], 400)
    picked = [c["options"][i]["tier"] for c, i in zip([cheap, urgent], plan["selection"])]
    assert picked[1] == TIER_EXCERPT, picked
    assert picked[0] == TIER_CARD, picked
    checks.append("budget: a tight budget buys the escalated anchor and drops the quiet one")

    # Two notes beat one excerpt when the budget cannot hold both and neither escalated.
    a, b = _candidate(anchor="a"), _candidate(anchor="b")
    plan = allocate([a, b], 250)
    tiers = sorted(c["options"][i]["tier"] for c, i in zip([a, b], plan["selection"]))
    assert tiers == [TIER_NOTE, TIER_NOTE], tiers
    checks.append("budget: breadth is preferred to depth when nothing asked for depth")

    # The plan must fit. A knapsack that overspends is worse than useless.
    for budget in (0, 50, 137, 999):
        plan = allocate([a, b, urgent], budget)
        spend = sum(
            c["options"][i]["tokens"] for c, i in zip([a, b, urgent], plan["selection"])
        )
        assert spend <= budget, f"budget {budget} overspent by {spend - budget}"
    checks.append("budget: the chosen plan never exceeds the ceiling, including at zero")

    # Trigger weight must not pay out below the tier that satisfies it.
    below = option_value(urgent, {"tier": TIER_NOTE, "tokens": 100})
    at = option_value(urgent, {"tier": TIER_EXCERPT, "tokens": 400})
    assert at - below > urgent["trigger_weight"] * 0.9, (below, at)
    checks.append("value: escalation pays only at the tier the trigger asked for")

    # Page locators must resolve, including the dash characters real bibliographies use.
    assert locator_pages("section 1, pp. 1-2") == (1, 2)
    assert locator_pages("pp. 30\u201345") == (30, 45)
    assert locator_pages("p. 7") == (7, 7)
    assert locator_pages("chapter 4") is None
    assert locator_pages(None) is None
    checks.append("locators: page ranges parse, and a locator without pages says so")

    # A tier with no material behind it must not be offered, or the knapsack buys nothing
    # cheaply and reports it as coverage.
    options = _tier_options({}, None, [], [], TIER_UNIT, DEFAULT_DIGEST_POLICY, False)
    assert [o["tier"] for o in options] == [TIER_CARD], options
    checks.append("tiers: an unread anchor with no extracted text offers only the card")

    # The whole source is an operator decision, never a trigger's. A ceiling that allows
    # it still must not produce it unasked.
    rows = [{"page": n, "text": "x" * 800, "use_class": "ingest_full"} for n in range(1, 9)]
    unasked = _tier_options({}, {"notes": "n", "locator": "pp. 1-2"}, rows[:2], rows,
                            TIER_SOURCE, {**DEFAULT_DIGEST_POLICY, "excerpt_chars": 500}, False)
    assert max(o["tier"] for o in unasked) < TIER_SOURCE, unasked
    asked = _tier_options({}, {"notes": "n", "locator": "pp. 1-2"}, rows[:2], rows,
                          TIER_SOURCE, {**DEFAULT_DIGEST_POLICY, "excerpt_chars": 500}, True)
    assert max(o["tier"] for o in asked) == TIER_SOURCE, asked
    source_option = [o for o in asked if o["tier"] == TIER_SOURCE][0]
    assert len(source_option["pages"]) == 8, source_option["pages"]
    checks.append("source: the whole entry arrives only when it was asked for by name")

    # A unit whose locator names no pages is not a unit. Serving the entry under that
    # name is how "the empirical section" turns into fifty-four pages nobody asked for.
    vague = _tier_options({}, {"notes": "n", "locator": "empirical section"}, rows, rows,
                          TIER_SOURCE, {**DEFAULT_DIGEST_POLICY, "excerpt_chars": 500},
                          False, locator_resolved=False)
    assert max(o["tier"] for o in vague) == TIER_EXCERPT, vague
    tight = {**DEFAULT_DIGEST_POLICY, "excerpt_chars": 500}
    precise = _tier_options({}, {"notes": "n", "locator": "pp. 1-8"}, rows, rows,
                            TIER_SOURCE, tight, False, locator_resolved=True)
    assert max(o["tier"] for o in precise) == TIER_UNIT, precise
    checks.append("units: a unit with no page range cannot serve the entry as its unit tier")

    # And a licence still outranks the request.
    refused = _tier_options({}, {"notes": "n", "locator": "pp. 1-2"}, rows[:2], rows,
                            TIER_NOTE, {**DEFAULT_DIGEST_POLICY, "excerpt_chars": 500}, True)
    assert max(o["tier"] for o in refused) == TIER_NOTE, refused
    checks.append("source: asking for the whole entry does not defeat the rights ceiling")

    # Opt-in is read from the entry as well as the command line.
    assert wants_full_text({"id": "a", "digest_full_text": True}, set())
    assert wants_full_text({"id": "a", "digest": {"full_text": True}}, set())
    assert wants_full_text({"id": "a"}, {"a"})
    assert not wants_full_text({"id": "a"}, {"b"})
    assert not wants_full_text(None, {"a"})
    checks.append("source: the opt-in reads the bibliography flag and the command line")

    # Two anchors holding identical text must not both be paid for, at any tier.
    def _with(text_by_tier: dict[int, str], **over: Any) -> dict[str, Any]:
        return _candidate(
            options=[{"tier": TIER_CARD, "text": None, "tokens": 0}]
            + [
                {"tier": tier, "text": body, "tokens": estimate_tokens(body)}
                for tier, body in sorted(text_by_tier.items())
            ],
            **over,
        )

    whole = "the entire paper" * 400
    shared = [
        _with({TIER_NOTE: "note a", TIER_SOURCE: whole}, concept_id="KC-A", anchor="a", base_value=2.0),
        _with({TIER_NOTE: "note b", TIER_SOURCE: whole}, concept_id="KC-B", anchor="b", base_value=0.5),
    ]
    deduped = _dedupe_shared_text(shared)
    keeper = [c for c in deduped if c["concept_id"] == "KC-A"][0]
    shadow = [c for c in deduped if c["concept_id"] == "KC-B"][0]
    assert max(o["tier"] for o in keeper["options"]) == TIER_SOURCE, keeper["options"]
    assert max(o["tier"] for o in shadow["options"]) == TIER_NOTE, shadow["options"]
    assert shadow["shares_text_with"] == "KC-A"
    # The shadow keeps its own note: that text is not shared, only the source was.
    assert any(o.get("text") == "note b" for o in shadow["options"]), shadow["options"]
    checks.append("dedupe: identical text is bought once at any tier, distinct notes survive")

    return {"ok": True, "checks": checks}
