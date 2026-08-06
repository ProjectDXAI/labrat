"use client";

import { useEffect, useState } from "react";
import { Bundle } from "@/lib/types";
import { Overview } from "@/components/Overview";
import { Concepts } from "@/components/Concepts";
import { Sources } from "@/components/Sources";
import { Graph } from "@/components/Graph";

type View = "overview" | "concepts" | "sources" | "graph";

const VIEWS: { id: View; label: string; hint: string }[] = [
  { id: "overview", label: "Assessment", hint: "the store read as a whole" },
  { id: "concepts", label: "Concepts", hint: "what we claim, and on what" },
  { id: "sources", label: "Sources", hint: "457 catalogued, 65 held" },
  { id: "graph", label: "Network", hint: "who cites whom, across fields" },
];

export default function Page() {
  const [data, setData] = useState<Bundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<View>("overview");
  const [concept, setConcept] = useState<string | null>(null);

  useEffect(() => {
    fetch("/corpus.json")
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} loading /corpus.json`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  const openConcept = (id: string | null) => {
    setConcept(id);
    if (id) setView("concepts");
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-6 border-b border-line px-6 py-2.5">
        <div className="flex items-baseline gap-2.5">
          <span className="text-sm font-semibold tracking-[-0.01em]">Corpus explorer</span>
          <span className="font-mono text-2xs text-muted">quant-finance-corpus + dxap-knowledge</span>
        </div>
        <nav className="flex gap-1" aria-label="Views">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              title={v.hint}
              aria-current={view === v.id ? "page" : undefined}
              className={`rounded px-2.5 py-1 text-sm transition-colors duration-150 ${
                view === v.id
                  ? "bg-surface-2 text-ink"
                  : "text-muted hover:bg-surface hover:text-ink-2"
              }`}
            >
              {v.label}
            </button>
          ))}
        </nav>
        {data ? (
          <span className="tabular ml-auto text-2xs text-muted">
            {data.counts.entries} sources · {data.counts.concepts} concepts ·{" "}
            {data.counts.units_read}/{data.counts.units} units read
          </span>
        ) : null}
      </header>

      <main className="min-h-0 flex-1 overflow-hidden">
        {error ? (
          <div className="flex h-full items-center justify-center px-8">
            <div className="max-w-[52ch] text-center">
              <p className="text-sm text-bad">{error}</p>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                The bundle is generated, not committed. Run{" "}
                <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs text-ink-2">
                  make web-data
                </code>{" "}
                from the repository root, then reload.
              </p>
            </div>
          </div>
        ) : !data ? (
          <div className="space-y-3 px-8 py-8">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="h-11 animate-pulse rounded bg-surface"
                style={{ animationDelay: `${i * 60}ms` }}
              />
            ))}
          </div>
        ) : view === "overview" ? (
          <div className="h-full overflow-y-auto">
            <Overview data={data} onConcept={openConcept} />
          </div>
        ) : view === "concepts" ? (
          <Concepts data={data} selected={concept} onSelect={setConcept} />
        ) : view === "sources" ? (
          <Sources data={data} />
        ) : (
          <Graph data={data} />
        )}
      </main>
    </div>
  );
}
