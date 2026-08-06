"use client";

import { ReactNode } from "react";

/* Shared vocabulary. Every screen uses these, so a badge or a label never looks
   different in two places. */

export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-xs text-ink-2 ${className}`}>{children}</span>;
}

const TONE: Record<string, string> = {
  neutral: "border-line text-muted",
  ok: "border-ok/40 text-ok",
  warn: "border-warn/40 text-warn",
  bad: "border-bad/40 text-bad",
  info: "border-info/40 text-info",
  accent: "border-accent/45 text-accent",
};

export function Tag({
  children,
  tone = "neutral",
  title,
}: {
  children: ReactNode;
  tone?: keyof typeof TONE;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex shrink-0 items-center rounded border px-1.5 py-px text-2xs whitespace-nowrap ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

export function rightsTone(useClass: string): keyof typeof TONE {
  if (useClass.startsWith("ingest")) return "ok";
  if (useClass === "needs_review") return "warn";
  if (useClass === "excluded") return "bad";
  return "neutral";
}

export function Section({
  title,
  hint,
  children,
  right,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  right?: ReactNode;
}) {
  return (
    <section className="mb-9">
      <div className="mb-3 flex items-baseline justify-between gap-4 border-b border-line-soft pb-2">
        <div>
          <h2 className="text-lg font-semibold tracking-[-0.01em]">{title}</h2>
          {hint ? <p className="mt-0.5 max-w-[70ch] text-sm text-muted">{hint}</p> : null}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Stat({ value, label, tone }: { value: ReactNode; label: string; tone?: "accent" | "bad" }) {
  return (
    <div className="border-l border-line pl-3">
      <div
        className={`tabular text-xl font-semibold ${
          tone === "accent" ? "text-accent" : tone === "bad" ? "text-bad" : "text-ink"
        }`}
      >
        {value}
      </div>
      <div className="mt-0.5 text-xs text-muted">{label}</div>
    </div>
  );
}

export function Bar({ value, max, tone = "accent" }: { value: number; max: number; tone?: "accent" | "ok" }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2" role="presentation">
      <div
        className={`h-full rounded-full ${tone === "ok" ? "bg-ok" : "bg-accent"}`}
        style={{ width: `${pct}%`, transition: "width 220ms cubic-bezier(0.25,1,0.5,1)" }}
      />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-line px-4 py-8 text-center text-sm text-muted">
      {children}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  if (!children) return null;
  return (
    <div className="mb-3">
      <div className="mb-1 text-2xs font-medium tracking-wide text-muted uppercase">{label}</div>
      <div className="text-sm text-ink-2">{children}</div>
    </div>
  );
}

export function Bullets({ items, tone }: { items: string[]; tone?: "bad" | "warn" }) {
  if (!items?.length) return null;
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink-2">
          <span
            className={`mt-[0.55em] h-1 w-1 shrink-0 rounded-full ${
              tone === "bad" ? "bg-bad" : tone === "warn" ? "bg-warn" : "bg-muted"
            }`}
          />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}
