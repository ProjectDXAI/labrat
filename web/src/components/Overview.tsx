"use client";

import { Bundle } from "@/lib/types";
import { Bar, Empty, Mono, Section, Stat, Tag } from "./ui";

export function Overview({ data, onConcept }: { data: Bundle; onConcept: (id: string) => void }) {
  const a = data.assessment;
  const c = data.counts;
  const byId = new Map(data.concepts.map((x) => [x.id, x]));
  const dead = a.chains.filter((r) => r.complete_chains.length === 0 && r.concepts > 0);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-8">
      <header className="mb-9">
        <h1 className="text-2xl font-semibold tracking-[-0.02em]">
          What the corpus claims, and where it argues with itself
        </h1>
        <p className="mt-2 max-w-[72ch] text-sm leading-relaxed text-muted">
          Every number here is computed by <Mono>knowledge.py assess</Mono> and{" "}
          <Mono>corpus.py</Mono>, so nothing on screen can drift from the command line.
        </p>
      </header>

      <div className="mb-10 grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
        <Stat value={c.entries} label="sources catalogued" />
        <Stat value={c.concepts} label="concepts" />
        <Stat value={`${c.units_read}/${c.units}`} label="units read" />
        <Stat value={c.held} label="held on disk" />
        <Stat value={`${Math.round(a.grounded_share * 100)}%`} label="on read anchors" tone="accent" />
        <Stat value={dead.length} label="problems with no chain" tone={dead.length ? "bad" : undefined} />
      </div>

      <Section
        title="Chains that reach a decision"
        hint="A problem is served only when one concept covering it has a bound method, a hypothesis with a cost model, and a decision card. Anything less is a claim the agent cannot act on."
      >
        <div className="overflow-hidden rounded border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface text-2xs tracking-wide text-muted uppercase">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Problem</th>
                <th className="px-3 py-2 text-right font-medium">Concepts</th>
                <th className="px-3 py-2 text-right font-medium">+method</th>
                <th className="px-3 py-2 text-right font-medium">+hypothesis</th>
                <th className="px-3 py-2 text-right font-medium">+decision</th>
                <th className="px-3 py-2 text-right font-medium">Complete</th>
              </tr>
            </thead>
            <tbody>
              {a.chains.map((row) => {
                const broken = row.complete_chains.length === 0;
                return (
                  <tr
                    key={row.problem_id}
                    className={`border-t border-line-soft ${broken ? "bg-bad/[0.06]" : ""}`}
                  >
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs">{row.problem_id}</span>
                      {row.workstream ? (
                        <span className="ml-2 text-2xs text-muted">{row.workstream}</span>
                      ) : null}
                    </td>
                    <td className="tabular px-3 py-2 text-right text-ink-2">{row.concepts}</td>
                    <td className="tabular px-3 py-2 text-right text-ink-2">{row.with_method}</td>
                    <td className="tabular px-3 py-2 text-right text-ink-2">{row.with_hypothesis}</td>
                    <td className="tabular px-3 py-2 text-right text-ink-2">{row.with_decision_card}</td>
                    <td
                      className={`tabular px-3 py-2 text-right font-semibold ${
                        broken ? "text-bad" : "text-ok"
                      }`}
                    >
                      {row.complete_chains.length}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {dead.length > 0 ? (
          <p className="mt-3 max-w-[72ch] text-sm leading-relaxed text-ink-2">
            <span className="text-bad">
              {dead.map((d) => d.problem_id).join(" and ")}
            </span>{" "}
            {dead.length === 1 ? "has" : "have"} concepts, hypotheses and decision cards, and no single
            concept carrying all three together. They look healthy by every count in this table and
            neither can be acted on.
          </p>
        ) : null}
      </Section>

      <Section
        title="Where the corpus argues with itself"
        hint={`${a.contradiction.pairs.length} contradiction pairs across ${a.contradiction.concepts_in_a_contradiction} concepts, in ${a.contradiction.clusters.length} clusters. A cluster is a question with two defensible answers, not a defect.`}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {a.contradiction.clusters.map((cluster) => (
            <div key={cluster.join()} className="rounded border border-line bg-surface p-3">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                {cluster.map((id, i) => (
                  <span key={id} className="flex items-center gap-2">
                    {i > 0 ? <span className="text-bad">&harr;</span> : null}
                    <button
                      onClick={() => onConcept(id)}
                      className="rounded font-mono text-xs text-ink-2 underline decoration-line underline-offset-2 hover:text-accent"
                    >
                      {id}
                    </button>
                  </span>
                ))}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                {cluster
                  .map((id) => byId.get(id)?.name)
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Confidence that has not been earned"
        hint="Confidence at or above 0.6 with no anchor anyone opened. Not evidence they are wrong; evidence the confidence is a memory of the literature rather than a reading of it."
      >
        {a.high_confidence_on_unread.length === 0 ? (
          <Empty>Every confident card rests on something someone opened.</Empty>
        ) : (
          <ul className="divide-y divide-line-soft rounded border border-line">
            {a.high_confidence_on_unread.map((row) => (
              <li key={row.concept_id} className="flex items-center gap-3 px-3 py-2">
                <span className="tabular w-9 shrink-0 text-sm font-semibold text-warn">
                  {row.confidence.toFixed(2)}
                </span>
                <button
                  onClick={() => onConcept(row.concept_id)}
                  className="shrink-0 rounded font-mono text-xs text-ink-2 hover:text-accent"
                >
                  {row.concept_id}
                </button>
                <span className="truncate text-sm text-muted">{row.name}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Structural integrity" hint="The four ways a store like this rots quietly.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Unread anchors carrying 2+ cards", a.unread_single_points.length],
            ["Methods bound to nothing", a.orphan_methods.length],
            ["Concepts outside the problem map", a.concepts_without_problem.length],
            ["Cards with no counterweight", a.contradiction.uncountered_concepts.length],
          ].map(([label, n]) => (
            <div key={label as string} className="rounded border border-line bg-surface px-3 py-3">
              <div className="flex items-baseline justify-between">
                <span className={`tabular text-xl font-semibold ${n ? "text-bad" : "text-ok"}`}>
                  {n as number}
                </span>
                <Tag tone={n ? "bad" : "ok"}>{n ? "attention" : "clear"}</Tag>
              </div>
              <div className="mt-1 text-xs leading-snug text-muted">{label as string}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Coverage against target" hint="Pages mapped against the page budget set per bucket in the taxonomy.">
        <div className="space-y-2.5">
          {Object.entries(data.buckets)
            .sort((a, b) => b[1].pages_mapped / (b[1].target_pages || 1) - a[1].pages_mapped / (a[1].target_pages || 1))
            .map(([name, row]) => (
              <div key={name} className="grid grid-cols-[minmax(0,15rem)_1fr_auto] items-center gap-3">
                <span className="truncate text-sm text-ink-2">{name}</span>
                <Bar value={row.pages_mapped} max={row.target_pages || 1} />
                <span className="tabular w-28 text-right text-xs text-muted">
                  {row.pages_mapped.toLocaleString()} / {(row.target_pages || 0).toLocaleString()}
                </span>
              </div>
            ))}
        </div>
      </Section>
    </div>
  );
}
