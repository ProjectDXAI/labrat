"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";
import { Bundle } from "@/lib/types";
import { Tag } from "./ui";

import type { SimulationNodeDatum } from "d3-force";

type Sim = SimulationNodeDatum & {
  id: string;
  bucket: string;
  r: number;
  held: boolean;
  degree: number;
  title: string;
};
type Link = { source: string | Sim; target: string | Sim; cross?: boolean };

/* Bucket hues are a categorical encoding, not decoration: the graph's whole job is
   showing where an edge crosses from one field into another. */
function hueFor(bucket: string, buckets: string[]) {
  const i = Math.max(0, buckets.indexOf(bucket));
  return (i * 360) / Math.max(buckets.length, 1);
}

export function Graph({ data }: { data: Bundle }) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [bucketFilter, setBucketFilter] = useState("all");
  const [hideIsolated, setHideIsolated] = useState(true);
  const [clustered, setClustered] = useState(true);
  const [crossOnly, setCrossOnly] = useState(false);
  // Positions live in state as a fresh array per frame. d3 mutates the node objects
  // in place, and React 19 memoises on identity, so a mutated-object render is
  // silently dropped -- 401 circles with no cx at all. Copying out is the fix.
  const [frameNodes, setFrameNodes] = useState<Sim[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });

  const buckets = useMemo(() => Object.keys(data.buckets).sort(), [data.buckets]);

  const { nodes, links } = useMemo(() => {
    const keep = new Set(
      data.graph.nodes
        .filter((n) => (bucketFilter === "all" ? true : n.bucket === bucketFilter))
        .filter((n) => (hideIsolated ? n.degree > 0 : true))
        .map((n) => n.id),
    );
    const nodes: Sim[] = data.graph.nodes
      .filter((n) => keep.has(n.id))
      .map((n) => ({
        id: n.id,
        bucket: n.bucket,
        held: n.held,
        degree: n.degree,
        title: n.title,
        r: 2.5 + Math.sqrt(n.degree) * 1.7,
      }));
    const bucketOf = new Map(data.graph.nodes.map((n) => [n.id, n.bucket]));
    const links: Link[] = data.graph.edges
      .filter((e) => keep.has(e.source) && keep.has(e.target))
      .filter((e) => (crossOnly ? bucketOf.get(e.source) !== bucketOf.get(e.target) : true))
      .map((e) => ({
        source: e.source,
        target: e.target,
        cross: bucketOf.get(e.source) !== bucketOf.get(e.target),
      }));
    return { nodes, links };
  }, [data.graph, bucketFilter, hideIsolated, crossOnly]);

  // The container is flex-sized, so it can measure zero on first paint. A ResizeObserver
  // catches the real value whenever it arrives, and the zero guard stops the simulation
  // laying every node out around a point at the origin.
  const boxRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 40 && height > 40) setSize({ w: Math.round(width), h: Math.round(height) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (size.w < 40 || size.h < 40) return;
    // Anchor each field to its own point on a ring. A hairball hides the one thing
    // this graph is for: an edge that leaves its field. Clustered, those become the
    // long chords across the middle and you can see them without hovering.
    const radius = Math.min(size.w, size.h) * 0.33;
    const anchor = (bucket: string) => {
      const i = Math.max(0, buckets.indexOf(bucket));
      const a = (i / Math.max(buckets.length, 1)) * Math.PI * 2 - Math.PI / 2;
      return { x: size.w / 2 + Math.cos(a) * radius, y: size.h / 2 + Math.sin(a) * radius };
    };

    const sim = forceSimulation<Sim>(nodes)
      .force(
        "link",
        forceLink<Sim, Link>(links)
          .id((d) => d.id)
          .distance(46)
          .strength(0.14),
      )
      .force("charge", forceManyBody<Sim>().strength(-26))
      .force("collide", forceCollide<Sim>().radius((d) => d.r + 1.6))
      .force("x", forceX<Sim>((d) => (clustered ? anchor(d.bucket).x : size.w / 2)).strength(clustered ? 0.34 : 0.04))
      .force("y", forceY<Sim>((d) => (clustered ? anchor(d.bucket).y : size.h / 2)).strength(clustered ? 0.34 : 0.04));

    const publish = () => setFrameNodes(nodes.map((n) => ({ ...n })));
    let frame = 0;
    sim.on("tick", () => {
      frame += 1;
      if (frame % 2 === 0) publish();
    });
    sim.on("end", publish);
    publish();
    return () => {
      sim.stop();
    };
  }, [nodes, links, size.w, size.h, buckets, clustered]);

  const positions = useMemo(() => new Map(frameNodes.map((n) => [n.id, n])), [frameNodes]);
  const hovered = hover ? positions.get(hover) ?? null : null;
  const neighbours = useMemo(() => {
    if (!hover) return new Set<string>();
    const set = new Set<string>([hover]);
    for (const l of data.graph.edges) {
      if (l.source === hover) set.add(l.target);
      if (l.target === hover) set.add(l.source);
    }
    return set;
  }, [hover, data.graph.edges]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line px-6 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={bucketFilter}
            onChange={(e) => setBucketFilter(e.target.value)}
            aria-label="Filter graph by bucket"
            className="rounded border border-line bg-surface px-2 py-1.5 text-sm text-ink-2 focus:border-accent focus:outline-none"
          >
            <option value="all">all buckets</option>
            {buckets.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          {(
            [
              ["cluster by field", clustered, setClustered],
              ["cross-field only", crossOnly, setCrossOnly],
              ["hide unconnected", hideIsolated, setHideIsolated],
            ] as const
          ).map(([label, value, set]) => (
            <label key={label} className="flex items-center gap-1.5 text-xs text-muted">
              <input
                type="checkbox"
                checked={value}
                onChange={(e) => set(e.target.checked)}
                className="accent-[oklch(0.795_0.135_78)]"
              />
              {label}
            </label>
          ))}
          <span className="tabular ml-auto text-xs text-muted">
            {nodes.length} nodes · {links.length} edges · {data.graph.components} components
          </span>
        </div>
      </div>

      <div ref={boxRef} className="relative min-h-0 flex-1">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${size.w || 1} ${size.h || 1}`}
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Bibliography network, clustered by field"
        >
          <g>
            {links.map((l, i) => {
              const sid = typeof l.source === "string" ? l.source : l.source.id;
              const tid = typeof l.target === "string" ? l.target : l.target.id;
              const s = positions.get(sid);
              const t = positions.get(tid);
              if (!s || !t || s.x == null || t.x == null) return null;
              const lit = hover ? sid === hover || tid === hover : false;
              return (
                <line
                  key={i}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={
                    lit
                      ? "oklch(0.795 0.135 78)"
                      : l.cross
                        ? "oklch(0.64 0.045 255)"
                        : "oklch(0.44 0.012 255)"
                  }
                  strokeWidth={lit ? 1.6 : l.cross ? 0.8 : 0.5}
                  opacity={hover ? (lit ? 1 : 0.1) : l.cross ? 0.55 : 0.22}
                />
              );
            })}
          </g>
          {frameNodes.map((n) => {
            const dim = hover ? !neighbours.has(n.id) : false;
            return (
              <circle
                key={n.id}
                cx={n.x}
                cy={n.y}
                r={n.r}
                fill={`oklch(0.68 0.11 ${hueFor(n.bucket, buckets)})`}
                stroke={n.held ? "oklch(0.945 0.004 255)" : "transparent"}
                strokeWidth={n.held ? 1 : 0}
                opacity={dim ? 0.15 : 0.92}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                style={{ cursor: "pointer" }}
              >
                <title>{n.title}</title>
              </circle>
            );
          })}
        </svg>

        {hovered ? (
          <div className="pointer-events-none absolute top-4 left-4 max-w-[34rem] rounded border border-line bg-surface/95 px-3 py-2 shadow-lg backdrop-blur-sm">
            <p className="text-sm leading-snug text-ink">{hovered.title}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-2xs text-muted">{hovered.id}</span>
              <Tag>{hovered.bucket}</Tag>
              <Tag>{hovered.degree} edges</Tag>
              {hovered.held ? <Tag tone="ok">on disk</Tag> : null}
            </div>
          </div>
        ) : null}

        <div className="pointer-events-none absolute right-4 bottom-4 max-w-[16rem] rounded border border-line bg-surface/95 px-3 py-2">
          <p className="text-2xs leading-relaxed text-muted">
            Colour is the field, size is citation degree, a white ring means we hold the full text.
            The pale chords crossing the middle are edges that leave their field: those are the
            transfers this corpus exists to find.
          </p>
        </div>
      </div>
    </div>
  );
}
