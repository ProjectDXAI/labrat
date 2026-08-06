"use client";

import { useMemo, useState } from "react";
import { Bundle, Entry } from "@/lib/types";
import { Empty, Mono, Tag, rightsTone } from "./ui";

type Filter = "all" | "held" | "read" | "unverified";

export function Sources({ data }: { data: Bundle }) {
  const [query, setQuery] = useState("");
  const [bucket, setBucket] = useState("all");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  const buckets = useMemo(
    () => ["all", ...Object.keys(data.buckets).sort()],
    [data.buckets],
  );

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.entries
      .filter((e) => (bucket === "all" ? true : e.bucket === bucket))
      .filter((e) => {
        if (filter === "held") return e.held;
        if (filter === "read") return e.units.some((u) => u.read_status === "read" || u.read_status === "compiled");
        if (filter === "unverified") return e.rights.confidence !== "confirmed";
        return true;
      })
      .filter((e) =>
        !q
          ? true
          : [e.id, e.title, e.authors.join(" "), e.tags.join(" "), e.venue ?? ""]
              .join(" ")
              .toLowerCase()
              .includes(q),
      )
      .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0) || a.title.localeCompare(b.title));
  }, [data.entries, query, bucket, filter]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line px-6 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title, author, tag&hellip;"
            aria-label="Search sources"
            className="w-72 rounded border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <select
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
            aria-label="Filter by bucket"
            className="rounded border border-line bg-surface px-2 py-1.5 text-sm text-ink-2 focus:border-accent focus:outline-none"
          >
            {buckets.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <div className="flex gap-1">
            {(["all", "held", "read", "unverified"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setFilter(k)}
                className={`rounded border px-2 py-1 text-2xs transition-colors duration-150 ${
                  filter === k
                    ? "border-accent bg-accent text-accent-ink"
                    : "border-line text-muted hover:text-ink-2"
                }`}
              >
                {k}
              </button>
            ))}
          </div>
          <span className="tabular ml-auto text-xs text-muted">
            {rows.length} of {data.entries.length}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <div className="p-8">
            <Empty>No source matches those filters.</Empty>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-20 bg-surface text-2xs tracking-wide text-muted uppercase">
              <tr className="border-b border-line">
                <th className="px-6 py-2 text-left font-medium">Source</th>
                <th className="px-3 py-2 text-left font-medium">Bucket</th>
                <th className="px-3 py-2 text-left font-medium">Rights</th>
                <th className="px-3 py-2 text-right font-medium">Pages</th>
                <th className="px-3 py-2 text-right font-medium">Units</th>
                <th className="px-6 py-2 text-right font-medium">Pri</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <SourceRow key={e.id} entry={e} open={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function SourceRow({ entry, open, onToggle }: { entry: Entry; open: boolean; onToggle: () => void }) {
  const read = entry.units.filter((u) => u.read_status === "read" || u.read_status === "compiled").length;
  return (
    <>
      <tr
        onClick={onToggle}
        className={`cursor-pointer border-b border-line-soft transition-colors duration-150 ${
          open ? "bg-surface-2" : "hover:bg-surface"
        }`}
      >
        <td className="px-6 py-2">
          <div className="flex items-center gap-2">
            <span className="leading-snug text-ink">{entry.title}</span>
            {entry.held ? <Tag tone="ok">on disk</Tag> : null}
          </div>
          <div className="mt-0.5 text-xs text-muted">
            {entry.authors.slice(0, 3).join(", ")}
            {entry.authors.length > 3 ? " et al." : ""} {entry.year ? `· ${entry.year}` : ""}
            {entry.venue ? ` · ${entry.venue}` : ""}
          </div>
        </td>
        <td className="px-3 py-2 text-xs text-muted">{entry.bucket}</td>
        <td className="px-3 py-2">
          <Tag tone={rightsTone(entry.rights.use_class)} title={entry.rights.status}>
            {entry.rights.use_class}
          </Tag>
          {entry.rights.confidence !== "confirmed" ? (
            <span className="ml-1.5 text-2xs text-muted">{entry.rights.confidence}</span>
          ) : null}
        </td>
        <td className="tabular px-3 py-2 text-right text-muted">{entry.pages ?? "—"}</td>
        <td className="tabular px-3 py-2 text-right text-muted">
          {entry.units.length ? (
            <span className={read ? "text-ok" : undefined}>
              {read}/{entry.units.length}
            </span>
          ) : (
            "—"
          )}
        </td>
        <td className="tabular px-6 py-2 text-right text-muted">{entry.priority ?? "—"}</td>
      </tr>
      {open ? (
        <tr className="border-b border-line bg-bg">
          <td colSpan={6} className="px-6 py-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Mono>{entry.id}</Mono>
              <Tag>{entry.form}</Tag>
              {entry.doi ? (
                <a
                  href={`https://doi.org/${entry.doi}`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded font-mono text-xs text-accent underline decoration-accent-dim underline-offset-2"
                >
                  {entry.doi}
                </a>
              ) : null}
              {entry.tags.slice(0, 8).map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </div>
            {entry.notes ? (
              <p className="mb-4 max-w-[80ch] text-sm leading-relaxed text-ink-2">{entry.notes}</p>
            ) : null}
            {entry.units.length ? (
              <div>
                <h4 className="mb-2 text-2xs font-medium tracking-wide text-muted uppercase">
                  Reading units
                </h4>
                <ul className="space-y-2">
                  {entry.units.map((u) => (
                    <li key={u.unit_id} className="flex gap-2.5">
                      <span
                        className={`mt-[0.45em] h-1.5 w-1.5 shrink-0 rounded-full ${
                          u.read_status === "read" || u.read_status === "compiled" ? "bg-ok" : "bg-line"
                        }`}
                      />
                      <div className="min-w-0">
                        <div className="text-sm text-ink-2">
                          <span className="font-mono text-xs">{u.unit_id}</span>
                          {u.locator ? <span className="ml-2 text-muted">{u.locator}</span> : null}
                        </div>
                        <div className="text-sm text-muted">{u.topic}</div>
                        {u.notes ? (
                          <p className="mt-1 max-w-[80ch] text-xs leading-relaxed text-ink-2">{u.notes}</p>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-sm text-muted">
                Not decomposed into units yet — the whole source is one unread target.
              </p>
            )}
          </td>
        </tr>
      ) : null}
    </>
  );
}
