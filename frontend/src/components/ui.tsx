// Small shared pieces from design.md section 6: buttons, chips, tags, status, notices, cards.
import type { ComponentProps, ReactNode } from "react";
import { CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";

type ButtonKind = "primary" | "dark" | "soft";
const BUTTON: Record<ButtonKind, string> = {
  primary: "h-14 bg-lime text-ink font-semibold text-base",
  dark: "h-11 bg-ink text-surface font-medium",
  soft: "h-11 bg-surface text-ink font-medium border border-line",
};

export function Button({ kind = "soft", className = "", ...props }: ComponentProps<"button"> & { kind?: ButtonKind }) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-full px-5 transition duration-150 ease-out
        hover:brightness-95 disabled:opacity-40 disabled:pointer-events-none ${BUTTON[kind]} ${className}`}
    />
  );
}

export function Card({ children, className = "", as: Tag = "section" }: { children: ReactNode; className?: string; as?: "section" | "div" }) {
  return <Tag className={`rounded-card bg-surface p-6 animate-fade-in ${className}`}>{children}</Tag>;
}

export function Chip({ icon: Icon, children, className = "" }: { icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-sm whitespace-nowrap ${className}`}>
      {Icon && <Icon size={16} strokeWidth={2} aria-hidden />}
      {children}
    </span>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return <span className="inline-block rounded-full bg-lime-soft px-2.5 py-0.5 text-[13px] font-medium whitespace-nowrap">{children}</span>;
}

type Tone = "ok" | "warn" | "bad";
const TONE: Record<Tone, string> = {
  ok: "text-success bg-success-bg",
  warn: "text-warning bg-warning-bg",
  bad: "text-danger bg-danger-bg",
};

export function Status({ tone, children }: { tone: Tone; children: ReactNode }) {
  const Icon = tone === "ok" ? CircleCheck : TriangleAlert;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[13px] font-medium ${TONE[tone]}`}>
      <Icon size={14} aria-hidden />
      {children}
    </span>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "bad"; children: ReactNode }) {
  const cls = { info: "bg-info-bg text-info", warn: "bg-warning-bg text-warning", bad: "bg-danger-bg text-danger" }[tone];
  const Icon = tone === "info" ? Info : TriangleAlert;
  return (
    <div role="status" className={`flex items-start gap-2.5 rounded-input px-4 py-3 text-sm ${cls}`}>
      <Icon size={18} className="mt-px shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

/** Pill toggles for single or multiple choice (filter chips: selected = ink). */
export function PillGroup<T extends string>({
  label, options, value, onChange, multi = false, accent = false, renderLabel,
}: {
  label: string; options: readonly T[]; value: T | T[]; onChange: (v: any) => void;
  multi?: boolean; accent?: boolean; renderLabel?: (o: T) => ReactNode;
}) {
  const selected = (o: T) => (multi ? (value as T[]).includes(o) : value === o);
  const toggle = (o: T) =>
    multi ? onChange(selected(o) ? (value as T[]).filter((x) => x !== o) : [...(value as T[]), o]) : onChange(o);
  const on = accent ? "bg-lime text-ink border-lime" : "bg-ink text-surface border-ink";
  return (
    <div role="group" aria-label={label} className="flex gap-2 flex-wrap">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          aria-pressed={selected(o)}
          onClick={() => toggle(o)}
          className={`min-h-10 rounded-full border px-4 text-sm font-medium transition duration-150 ease-out
            ${selected(o) ? on : "bg-surface-raised text-ink border-line hover:brightness-95"}`}
        >
          {renderLabel ? renderLabel(o) : capitalizeFirst(o)}
        </button>
      ))}
    </div>
  );
}

function capitalizeFirst(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
