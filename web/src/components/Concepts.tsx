"use client";

import { useMemo, useState } from "react";
import { Bundle, Concept } from "@/lib/types";
import { Bullets, Empty, Field, Mono, Tag } from "./ui";

function statusTone(status: string) {
  return status === "implemented" || status === "validated" ? "ok" : "neutral";
}

export function Concepts({
  data,
  selected,
  onSelect,
}: {
  data: Bundle;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [workstream, setWorkstream] = useState("all");
  const [only, setOnly] = useState<"all" | "grounded" | "ungrounded" | "contested">("all");

  const byId = useMemo(() => new Map(data.concepts.map((c) => [c.id, c])), [data.concepts]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.concepts
      .filter((c) => (workstream === "all" ? true : c.workstream === workstream))
      .filter((c) =>
        only === "all"
          ? true
          : only === "grounded"
            ? c.grounded
            : only === "ungrounded"
              ? !c.grounded
              : c.contradicts.length > 0,
      )
      .filter((c) =>
        !q
          ? true
          : [c.id, c.name, c.plain, c.mechanism, c.tags.join(" "), c.problems.join(" ")]
              .join(" ")
              .toLowerCase()
              .includes(q),
      )
      .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
  }, [data.concepts, query, workstream, only]);

  const active = selected ? byId.get(selected) ?? null : null;
  const workstreams = ["all", ...Object.keys(data.assessment.by_workstream)];

  return (
    <div className="flex h-full min-h-0">
      <div className="flex min-h-0 w-[26rem] shrink-0 flex-col border-r border-line">
        <div className="border-b border-line px-4 py-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search mechanism, assumption, tag&hellip;"
            aria-label="Search concepts"
            className="w-full rounded border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <div className="mt-2 flex flex-wrap gap-1">
            {(["all", "grounded", "ungrounded", "contested"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setOnly(k)}
                className={`rounded border px-2 py-0.5 text-2xs transition-colors duration-150 ${
                  only === k
                    ? "border-accent bg-accent text-accent-ink"
                    : "border-line text-muted hover:border-line-soft hover:text-ink-2"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {workstreams.map((w) => (
              <button
                key={w}
                onClick={() => setWorkstream(w)}
                className={`rounded border px-2 py-0.5 text-2xs transition-colors duration-150 ${
                  workstream === w
                    ? "border-ink-2 text-ink"
                    : "border-line text-muted hover:text-ink-2"
                }`}
              >
                {w}
              </button>
            ))}
          </div>
          <p className="tabular mt-2 text-2xs text-muted">{rows.length} of {data.concepts.length}</p>
        </div>

        <ul className="min-h-0 flex-1 divide-y divide-line-soft overflow-y-auto">
          {rows.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => onSelect(c.id === selected ? null : c.id)}
                className={`w-full px-4 py-2.5 text-left transition-colors duration-150 ${
                  c.id === selected ? "bg-surface-2" : "hover:bg-surface"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm leading-snug font-medium text-ink">{c.name}</span>
                  <span
                    className={`tabular shrink-0 text-xs ${c.grounded ? "text-ok" : "text-muted"}`}
                    title={c.grounded ? "rests on a unit someone opened" : "rests on unread anchors"}
                  >
                    {c.confidence?.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1.5">
                  <Mono>{c.id}</Mono>
                  {c.contradicts.length > 0 ? <Tag tone="bad">contested</Tag> : null}
                </div>
              </button>
            </li>
          ))}
          {rows.length === 0 ? (
            <li className="p-4">
              <Empty>Nothing matches that.</Empty>
            </li>
          ) : null}
        </ul>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!active ? (
          <div className="flex h-full items-center justify-center px-8">
            <p className="max-w-[46ch] text-center text-sm leading-relaxed text-muted">
              Pick a concept. Each one carries the mechanism it claims, the assumptions it needs, what
              would falsify it, and whether anyone opened the source it rests on.
            </p>
          </div>
        ) : (
          <ConceptDetail concept={active} data={data} onSelect={onSelect} />
        )}
      </div>
    </div>
  );
}

function ConceptDetail({
  concept,
  data,
  onSelect,
}: {
  concept: Concept;
  data: Bundle;
  onSelect: (id: string) => void;
}) {
  const entries = useMemo(() => new Map(data.entries.map((e) => [e.id, e])), [data.entries]);
  const hypotheses = data.hypotheses.filter((h) => h.concept_id === concept.id);
  const decisions = data.decisions.filter((d) => d.concept_id === concept.id);

  return (
    <article className="mx-auto max-w-[76ch] px-8 py-7">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <Mono>{concept.id}</Mono>
        <Tag tone={statusTone(concept.status)}>{concept.status}</Tag>
        <Tag tone={concept.grounded ? "ok" : "warn"}>
          {concept.grounded ? "on a read unit" : "unread anchors"}
        </Tag>
        {concept.workstream !== "cross_cutting" ? <Tag tone="info">{concept.workstream}</Tag> : null}
      </div>
      <h2 className="text-xl font-semibold tracking-[-0.015em] text-balance">{concept.name}</h2>
      <p className="mt-3 text-sm leading-relaxed text-ink-2 text-pretty">{concept.plain}</p>

      <div className="mt-6 rounded border border-line bg-surface p-4">
        <Field label="Mechanism">
          <span className="leading-relaxed">{concept.mechanism}</span>
        </Field>
        {concept.equations ? (
          <Field label="Formally">
            <code className="block rounded bg-bg px-2.5 py-2 font-mono text-xs leading-relaxed text-ink-2">
              {concept.equations}
            </code>
          </Field>
        ) : null}
        {concept.signature ? (
          <Field label="What we would see if it holds">
            <span className="leading-relaxed">{concept.signature}</span>
          </Field>
        ) : null}
      </div>

      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">Holds only if</h3>
          <Bullets items={concept.assumptions} tone="warn" />
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold text-ink">What would break it</h3>
          <Bullets items={concept.failure_modes} tone="bad" />
        </div>
      </div>

      {concept.alternatives.length > 0 ? (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-ink">Competing explanations</h3>
          <Bullets items={concept.alternatives} />
        </div>
      ) : null}

      {concept.contradicts.length > 0 ? (
        <div className="mt-6 rounded border border-bad/35 bg-bad/[0.06] p-3">
          <h3 className="mb-2 text-sm font-semibold text-bad">Contradicted by</h3>
          <div className="flex flex-wrap gap-2">
            {concept.contradicts.map((id) => (
              <button
                key={id}
                onClick={() => onSelect(id)}
                className="rounded border border-bad/40 px-2 py-0.5 font-mono text-xs text-ink-2 transition-colors duration-150 hover:text-bad"
              >
                {id}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-6 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <Field label="Markets">{concept.markets.join(", ")}</Field>
        <Field label="Horizons">{concept.horizons.join(", ")}</Field>
        <Field label="Needs observables">{concept.observables.join(", ")}</Field>
        <Field label="Problems">{concept.problems.join(", ")}</Field>
        <Field label="Methods">
          {concept.methods.length ? (
            <span className="font-mono text-xs">{concept.methods.join(", ")}</span>
          ) : (
            <span className="text-muted">none bound</span>
          )}
        </Field>
        <Field label="Tested by">
          {hypotheses.length ? (
            <span className="font-mono text-xs">
              {hypotheses.map((h) => h.hypothesis_id).join(", ")}
            </span>
          ) : (
            <span className="text-muted">no hypothesis</span>
          )}
        </Field>
      </div>

      <div className="mt-6">
        <h3 className="mb-2 text-sm font-semibold text-ink">Anchored to</h3>
        <ul className="space-y-1.5">
          {concept.anchors.map((a) => {
            const entry = entries.get(a.source_id);
            return (
              <li key={a.key} className="flex items-start gap-2 text-sm">
                <span
                  className={`mt-[0.45em] h-1.5 w-1.5 shrink-0 rounded-full ${a.read ? "bg-ok" : "bg-line"}`}
                  title={a.read ? "read" : "not opened"}
                />
                <span className="min-w-0">
                  <span className="font-mono text-xs text-ink-2">{a.key}</span>
                  {entry ? (
                    <span className="ml-2 text-muted">
                      {entry.title}
                      {entry.held ? <span className="ml-1.5 text-ok">· on disk</span> : null}
                    </span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {decisions.length > 0 ? (
        <div className="mt-6">
          <h3 className="mb-2 text-sm font-semibold text-ink">Bears on</h3>
          <div className="flex flex-wrap gap-1.5">
            {decisions.map((d) => (
              <Tag key={d.decision_relevance_id} tone="accent">
                {d.decision_type}
              </Tag>
            ))}
          </div>
        </div>
      ) : null}
    </article>
  );
}
