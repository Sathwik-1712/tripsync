// "Under the hood": every agent step in order, with the real services it called, what it decided and why, and
// what the AI suggested and whether the code accepted it. Built from backend/tripsync/trace.py.
import {
  BedDouble, CalendarDays, ChevronDown, CornerDownLeft, Database, Flag, ListChecks, MapPin, MessageSquare, Plane, Ruler,
  ShieldCheck, Sparkles, UserRound, Wallet, type LucideIcon,
} from "lucide-react";
import type { TraceCall, TraceStep } from "../api";

const AGENT: Record<string, [string, LucideIcon, string]> = {
  intake: ["Intake agent", MessageSquare, "Reads your request"],
  clarify: ["Intake agent", MessageSquare, "Asks for what's missing"],
  budget: ["Budget agent", Wallet, "Sets a limit for each category"],
  transport: ["Transport agent", Plane, "Finds ways to get there"],
  accommodation: ["Accommodation agent", BedDouble, "Finds stays"],
  activity: ["Activity agent", MapPin, "Finds places and weather"],
  review: ["You", ListChecks, "Choose places, stay and transport"],
  planner: ["Planner agent", CalendarDays, "Builds the days"],
  critic: ["Critic agent", ShieldCheck, "Checks the plan"],
  ask_user: ["You", UserRound, "Decide after 3 rounds"],
  finalize: ["Final step", Flag, "Puts the plan together"],
  refine: ["Refine agent", MessageSquare, "Understands your change"],
};
const NICE: Record<string, string> = {
  accommodation: "Accommodation", transport: "Transport", activity: "Activity", planner: "Planner",
  budget: "Budget", ask_user: "you", finalize: "final",
};

function badge(c: TraceCall): [string, string] {
  if (!c.ok) return ["Failed", "bg-danger-bg text-danger"];
  if (c.kind === "ai") return ["AI", "bg-lime-soft text-ink"];
  if (c.kind === "estimate") return ["Estimate", "bg-warning-bg text-warning"];
  if (c.cached || c.kind === "db") return ["Saved", "bg-info-bg text-info"];
  return ["Live", "bg-success-bg text-success"];
}

function CallRow({ c }: { c: TraceCall }) {
  const [label, cls] = badge(c);
  const Icon = c.kind === "ai" ? Sparkles : c.kind === "db" ? Database : c.kind === "estimate" ? Ruler : null;
  return (
    <li className="grid grid-cols-[auto_1fr_auto] items-start gap-2 py-1 text-[13px]">
      <span className={`mt-0.5 rounded-full px-2 py-px text-[11px] font-semibold ${cls}`}>{label}</span>
      <span className="min-w-0">
        <b className="font-medium">{Icon && <Icon size={12} className="mr-1 inline" aria-hidden />}{c.service}</b>
        <span className="block break-words text-ink-muted">{c.what}{c.error ? ` · ${c.error}` : ""}</span>
      </span>
      <span className="num text-ink-muted">{c.ms ? `${c.ms} ms` : ""}</span>
    </li>
  );
}

function Step({ s, live }: { s: TraceStep; live: boolean }) {
  const [name, Icon, role] = AGENT[s.agent] ?? [s.agent, ShieldCheck, ""];
  const shown = s.calls.slice(0, 6);
  return (
    <li className={`relative grid grid-cols-[36px_1fr] gap-3 ${live ? "animate-fade-in" : ""}`}>
      <span className="grid size-9 place-items-center rounded-full bg-lime-soft"><Icon size={17} aria-hidden /></span>
      <div className="min-w-0 rounded-nested border border-line bg-surface p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3">
          <h3 className="text-[15px] font-semibold">{name} <span className="t-small font-normal">· {role}</span></h3>
          <span className="t-small num">{s.at}{s.ms >= 50 ? ` · ${(s.ms / 1000).toFixed(1)} s` : ""}</span>
        </div>
        {s.inputs.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="t-label self-center">Given</span>
            {s.inputs.map((x, i) => <span key={i} className="rounded-full bg-paper px-2 py-0.5 text-[12px]">{x}</span>)}
          </div>
        )}
        <p className="mt-2 text-sm font-medium">{s.decided}</p>
        {s.why && <p className="t-small mt-1"><b className="font-semibold text-ink">Why: </b>{s.why}</p>}
        {s.ai.map((a, i) => (
          <div key={i} className="mt-2.5 rounded-input bg-lime-soft/60 px-3 py-2 text-[13px]">
            <p className="flex items-center gap-1.5 font-semibold"><Sparkles size={13} aria-hidden />AI: {a.purpose}</p>
            <p className="mt-0.5"><span className="text-ink-muted">Suggested: </span>{a.suggested}</p>
            <p className="mt-0.5">
              <span className={`mr-1.5 rounded-full px-2 py-px text-[11px] font-semibold ${a.accepted ? "bg-success-bg text-success" : "bg-warning-bg text-warning"}`}>
                {a.accepted ? "Checked: used" : "Checked: not used"}
              </span>
              {a.verdict}
            </p>
          </div>
        ))}
        {s.calls.length > 0 ? (
          <details className="mt-2.5 group" open={live}>
            <summary className="t-small cursor-pointer list-none font-medium text-ink">
              {s.calls.length} call{s.calls.length > 1 ? "s" : ""} to real services ▾
            </summary>
            <ul className="mt-1 divide-y divide-line">
              {shown.map((c, i) => <CallRow key={i} c={c} />)}
            </ul>
            {s.calls.length > shown.length && <p className="t-small mt-1">…and {s.calls.length - shown.length} more</p>}
          </details>
        ) : <p className="t-small mt-2">No outside calls: worked from data already found.</p>}
      </div>
      {s.sent_to && !["finalize"].includes(s.sent_to) && (
        <p className="col-start-2 flex items-center gap-1.5 text-[13px] font-medium text-warning">
          <CornerDownLeft size={14} aria-hidden />Critic sent this back to the {NICE[s.sent_to] ?? s.sent_to} agent
        </p>
      )}
    </li>
  );
}

export function UnderTheHood({ steps, live = false }: { steps: TraceStep[]; live?: boolean }) {
  const calls = steps.flatMap((s) => s.calls);
  const api = calls.filter((c) => c.kind === "api");
  const aiCalls = calls.filter((c) => c.kind === "ai" && c.ok).length;
  const decisions = steps.flatMap((s) => s.ai);
  const sendBacks = steps.filter((s) => s.sent_to && s.sent_to !== "finalize").length;
  if (!steps.length) return <p className="t-small">Agent steps appear here as they run.</p>;
  return (
    <div className="grid gap-3">
      <p className="t-small">
        {steps.length} agent steps · {api.length} calls to real services ({api.filter((c) => c.ok && !c.cached).length} live,{" "}
        {api.filter((c) => c.cached).length} reused from cache, {api.filter((c) => !c.ok).length} failed) · {aiCalls} AI
        calls, {decisions.filter((d) => d.accepted).length} of {decisions.length} AI suggestions used after checking
        {sendBacks ? ` · the Critic sent work back ${sendBacks} time${sendBacks > 1 ? "s" : ""}` : ""}
      </p>
      <ol className="grid gap-3">
        {steps.map((s, i) => <Step key={i} s={s} live={live && i === steps.length - 1} />)}
      </ol>
    </div>
  );
}

// The collapsible section used on the selection and plan pages; the raw text log stays available inside it.
export function HoodCard({ steps, log }: { steps: TraceStep[]; log?: string[] }) {
  return (
    <details className="group rounded-card bg-surface animate-fade-in">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-6 py-4">
        <ChevronDown size={18} className="transition group-open:rotate-180" aria-hidden />
        <span className="t-h3">Under the hood</span>
        <span className="t-small">what each agent did, which real services it used, and where AI helped</span>
      </summary>
      <div className="grid gap-4 px-6 pb-6">
        <UnderTheHood steps={steps} />
        {log && log.length > 0 && (
          <details>
            <summary className="t-small cursor-pointer font-medium text-ink">Raw log</summary>
            <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded-input bg-paper p-3 text-xs leading-5">{log.join("\n")}</pre>
          </details>
        )}
      </div>
    </details>
  );
}
