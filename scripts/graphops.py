#!/usr/bin/env python3
"""Deterministic graph operations for bibliography and concept graphs.

Pure Python, no external graph library. The graphs here are small (thousands of
nodes at most) and the whole point is reproducibility: every routine sorts its
inputs and iterates in a fixed order, so the same graph always produces the same
ranking. Nothing samples.

Used by the corpus reading-list ranker and by the knowledge compiler's retrieval
expansion. `python scripts/graphops.py self-test` checks the algorithms against
hand-computable graphs.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any, Callable, Iterable, Sequence


Edge = tuple[str, str]


# --------------------------------------------------------------------------------------
# Adjacency
# --------------------------------------------------------------------------------------


def normalize_edges(edges: Iterable[Any]) -> list[Edge]:
    """Accept (src, dst) pairs or {"source":…, "target":…} mappings."""
    out: list[Edge] = []
    for edge in edges:
        if isinstance(edge, dict):
            source, target = edge.get("source"), edge.get("target")
        else:
            source, target = edge[0], edge[1]
        if source and target:
            out.append((str(source), str(target)))
    return sorted(set(out))


def out_adjacency(nodes: Sequence[str], edges: Iterable[Any]) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    known = set(nodes)
    for source, target in normalize_edges(edges):
        if source in known and target in known:
            adjacency[source].append(target)
    return {node: sorted(set(targets)) for node, targets in adjacency.items()}


def undirected_adjacency(nodes: Sequence[str], edges: Iterable[Any]) -> dict[str, list[str]]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    known = set(nodes)
    for source, target in normalize_edges(edges):
        if source in known and target in known and source != target:
            adjacency[source].add(target)
            adjacency[target].add(source)
    return {node: sorted(targets) for node, targets in adjacency.items()}


# --------------------------------------------------------------------------------------
# Centrality
# --------------------------------------------------------------------------------------


def personalized_pagerank(
    nodes: Sequence[str],
    edges: Iterable[Any],
    seeds: dict[str, float] | None = None,
    damping: float = 0.85,
    iterations: int = 60,
    tolerance: float = 1e-10,
) -> dict[str, float]:
    """Personalized PageRank seeded on a preference vector.

    Seeding on diagnosed problem nodes is what makes this different from citation
    count: it ranks works by proximity to the problems we actually have, not by
    global prestige.
    """
    nodes = sorted(set(nodes))
    if not nodes:
        return {}
    adjacency = out_adjacency(nodes, edges)

    total_seed = sum(max(0.0, weight) for weight in (seeds or {}).values())
    if seeds and total_seed > 0:
        preference = {node: max(0.0, (seeds.get(node) or 0.0)) / total_seed for node in nodes}
    else:
        preference = {node: 1.0 / len(nodes) for node in nodes}

    rank = dict(preference)
    for _ in range(iterations):
        nxt = {node: (1.0 - damping) * preference[node] for node in nodes}
        dangling = 0.0
        for node in nodes:
            targets = adjacency[node]
            if not targets:
                dangling += rank[node]
                continue
            share = damping * rank[node] / len(targets)
            for target in targets:
                nxt[target] += share
        if dangling:
            for node in nodes:
                nxt[node] += damping * dangling * preference[node]
        delta = sum(abs(nxt[node] - rank[node]) for node in nodes)
        rank = nxt
        if delta < tolerance:
            break
    return rank


def betweenness(nodes: Sequence[str], edges: Iterable[Any]) -> dict[str, float]:
    """Brandes betweenness on the undirected projection.

    High betweenness with low degree is the structural-hole signature: a work that
    is the only path between two literatures. Those are the bridges worth reading.
    """
    nodes = sorted(set(nodes))
    adjacency = undirected_adjacency(nodes, edges)
    score = {node: 0.0 for node in nodes}

    for start in nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in nodes}
        sigma = {node: 0.0 for node in nodes}
        distance = {node: -1 for node in nodes}
        sigma[start] = 1.0
        distance[start] = 0
        queue = [start]
        head = 0
        while head < len(queue):
            node = queue[head]
            head += 1
            stack.append(node)
            for neighbour in adjacency[node]:
                if distance[neighbour] < 0:
                    distance[neighbour] = distance[node] + 1
                    queue.append(neighbour)
                if distance[neighbour] == distance[node] + 1:
                    sigma[neighbour] += sigma[node]
                    predecessors[neighbour].append(node)
        delta = {node: 0.0 for node in nodes}
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if sigma[node]:
                    delta[predecessor] += (sigma[predecessor] / sigma[node]) * (1.0 + delta[node])
            if node != start:
                score[node] += delta[node]

    # Undirected: every pair counted twice.
    return {node: value / 2.0 for node, value in score.items()}


# --------------------------------------------------------------------------------------
# Similarity
# --------------------------------------------------------------------------------------


def co_citation(edges: Iterable[Any], min_support: int = 2) -> list[dict[str, Any]]:
    """Works cited together by the same citing work. Similarity of *what is cited*."""
    cited_by: dict[str, set[str]] = defaultdict(set)
    for source, target in normalize_edges(edges):
        cited_by[target].add(source)

    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for citing_targets in _grouped_targets(edges).values():
        ordered = sorted(citing_targets)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                pairs[(left, right)] += 1

    rows = [
        {"a": left, "b": right, "support": count}
        for (left, right), count in pairs.items()
        if count >= min_support
    ]
    rows.sort(key=lambda row: (-row["support"], row["a"], row["b"]))
    return rows


def bibliographic_coupling(edges: Iterable[Any], min_shared: int = 2) -> list[dict[str, Any]]:
    """Works that cite the same things. Similarity of *what they build on*."""
    grouped = _grouped_targets(edges)
    citing = sorted(grouped)
    rows: list[dict[str, Any]] = []
    for i, left in enumerate(citing):
        for right in citing[i + 1 :]:
            shared = grouped[left] & grouped[right]
            if len(shared) >= min_shared:
                rows.append({"a": left, "b": right, "shared": len(shared), "via": sorted(shared)})
    rows.sort(key=lambda row: (-row["shared"], row["a"], row["b"]))
    return rows


def _grouped_targets(edges: Iterable[Any]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for source, target in normalize_edges(edges):
        grouped[source].add(target)
    return grouped


# --------------------------------------------------------------------------------------
# Communities
# --------------------------------------------------------------------------------------


def communities(nodes: Sequence[str], edges: Iterable[Any], iterations: int = 30) -> dict[str, int]:
    """Deterministic label propagation on the undirected projection.

    Label propagation is normally randomized; here nodes are visited in sorted
    order and ties break on the lowest label, so the partition is reproducible.
    Good enough for "which literatures clump together"; not a Leiden replacement.
    """
    nodes = sorted(set(nodes))
    adjacency = undirected_adjacency(nodes, edges)
    label = {node: index for index, node in enumerate(nodes)}

    for _ in range(iterations):
        changed = False
        for node in nodes:
            neighbours = adjacency[node]
            if not neighbours:
                continue
            counts: dict[int, int] = defaultdict(int)
            for neighbour in neighbours:
                counts[label[neighbour]] += 1
            best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if best != label[node]:
                label[node] = best
                changed = True
        if not changed:
            break

    # Renumber densely, in order of first appearance, so ids are stable.
    remap: dict[int, int] = {}
    for node in nodes:
        remap.setdefault(label[node], len(remap))
    return {node: remap[label[node]] for node in nodes}


# --------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------


def maximal_marginal_relevance(
    candidates: Sequence[dict[str, Any]],
    similarity: Callable[[dict[str, Any], dict[str, Any]], float],
    k: int,
    lambda_: float = 0.7,
    score_key: str = "score",
    id_key: str = "id",
) -> list[dict[str, Any]]:
    """Pick k items trading relevance against redundancy.

    Without this a reading list becomes twenty books on the same chapter, and a
    retrieval packet becomes five restatements of one mechanism.
    """
    pool = sorted(candidates, key=lambda row: (-float(row.get(score_key) or 0.0), str(row.get(id_key))))
    selected: list[dict[str, Any]] = []
    while pool and len(selected) < k:
        best_row, best_value = None, None
        for row in pool:
            relevance = float(row.get(score_key) or 0.0)
            redundancy = max((similarity(row, chosen) for chosen in selected), default=0.0)
            value = lambda_ * relevance - (1.0 - lambda_) * redundancy
            if best_value is None or value > best_value + 1e-12:
                best_row, best_value = row, value
        selected.append({**best_row, "mmr_value": round(best_value, 6)})
        pool = [row for row in pool if row.get(id_key) != best_row.get(id_key)]
    return selected


def submodular_cover(
    items: Sequence[dict[str, Any]],
    coverage: dict[str, set[str]],
    targets: Iterable[str] | None = None,
    k: int | None = None,
    cost_key: str = "cost",
    id_key: str = "id",
) -> dict[str, Any]:
    """Greedy maximum coverage: the smallest reading list covering the concept space.

    Greedy is within (1 - 1/e) of optimal for monotone submodular coverage, which
    is the right trade when the alternative is ranking by citation count and
    reading five books that teach the same thing.
    """
    remaining = set(targets) if targets is not None else set().union(*coverage.values()) if coverage else set()
    chosen: list[dict[str, Any]] = []
    pool = {str(item[id_key]): item for item in items}

    while remaining and (k is None or len(chosen) < k):
        best_id, best_gain, best_ratio = None, 0, 0.0
        for item_id in sorted(pool):
            gain = len(coverage.get(item_id, set()) & remaining)
            if not gain:
                continue
            cost = float(pool[item_id].get(cost_key) or 1.0) or 1.0
            ratio = gain / cost
            if ratio > best_ratio + 1e-12:
                best_id, best_gain, best_ratio = item_id, gain, ratio
        if best_id is None:
            break
        covered = sorted(coverage.get(best_id, set()) & remaining)
        remaining -= set(covered)
        chosen.append({**pool.pop(best_id), "covers": covered, "gain": best_gain})

    return {
        "selected": chosen,
        "covered": sorted(set().union(*(set(row["covers"]) for row in chosen)) if chosen else set()),
        "uncovered": sorted(remaining),
    }


# --------------------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------------------


def self_test() -> dict[str, Any]:
    results: list[str] = []

    # A star: the hub must dominate an unseeded PageRank.
    nodes = ["hub", "a", "b", "c"]
    edges = [("a", "hub"), ("b", "hub"), ("c", "hub")]
    rank = personalized_pagerank(nodes, edges)
    assert max(rank, key=rank.get) == "hub", rank
    results.append("pagerank: hub dominates")

    # Seeding moves mass toward the seed's neighbourhood.
    seeded = personalized_pagerank(["x", "y", "z"], [("x", "y"), ("y", "z")], seeds={"x": 1.0})
    assert seeded["y"] > seeded["z"], seeded
    results.append("pagerank: seeding is local")

    # Path graph a-b-c: b is the only cut vertex, betweenness 1.
    between = betweenness(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert abs(between["b"] - 1.0) < 1e-9 and between["a"] == 0.0, between
    results.append("betweenness: path graph exact")

    # Two citing works both citing p and q.
    pairs = co_citation([("s1", "p"), ("s1", "q"), ("s2", "p"), ("s2", "q")], min_support=2)
    assert pairs and pairs[0]["support"] == 2 and {pairs[0]["a"], pairs[0]["b"]} == {"p", "q"}, pairs
    results.append("co-citation: shared citers")

    coupling = bibliographic_coupling([("s1", "p"), ("s1", "q"), ("s2", "p"), ("s2", "q")], min_shared=2)
    assert coupling and coupling[0]["shared"] == 2, coupling
    results.append("coupling: shared references")

    # Two disjoint triangles must land in two communities.
    triangle_nodes = ["a1", "a2", "a3", "b1", "b2", "b3"]
    triangle_edges = [("a1", "a2"), ("a2", "a3"), ("a3", "a1"), ("b1", "b2"), ("b2", "b3"), ("b3", "b1")]
    parts = communities(triangle_nodes, triangle_edges)
    assert len({parts[n] for n in ["a1", "a2", "a3"]}) == 1, parts
    assert parts["a1"] != parts["b1"], parts
    results.append("communities: disjoint triangles separate")

    # MMR must not return two identical high scorers back to back.
    candidates = [
        {"id": "one", "score": 1.0, "tags": {"impact"}},
        {"id": "one_copy", "score": 0.99, "tags": {"impact"}},
        {"id": "other", "score": 0.8, "tags": {"stopping"}},
    ]

    def jaccard(a: dict[str, Any], b: dict[str, Any]) -> float:
        left, right = a["tags"], b["tags"]
        return len(left & right) / len(left | right) if left | right else 0.0

    picked = [row["id"] for row in maximal_marginal_relevance(candidates, jaccard, k=2, lambda_=0.6)]
    assert picked == ["one", "other"], picked
    results.append("mmr: redundancy suppressed")

    cover = submodular_cover(
        [{"id": "book_a"}, {"id": "book_b"}, {"id": "book_c"}],
        {"book_a": {"c1", "c2"}, "book_b": {"c2"}, "book_c": {"c3"}},
        targets={"c1", "c2", "c3"},
    )
    assert [row["id"] for row in cover["selected"]] == ["book_a", "book_c"], cover
    assert not cover["uncovered"], cover
    results.append("submodular: minimal cover")

    return {"ok": True, "checks": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic graph operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test", help="Check the algorithms against hand-computable graphs.")
    args = parser.parse_args(argv)

    if args.command == "self-test":
        result = self_test()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
