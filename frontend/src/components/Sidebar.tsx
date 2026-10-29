import { CircleCheck, Circle, Compass, LoaderCircle, Plus, TriangleAlert } from "lucide-react";
import type { AgentStatus, Statuses } from "../api";
import { Button } from "./ui";

const AGENTS: [string, string][] = [
  ["budget", "Budget"], ["transport", "Transport"], ["accommodation", "Stay"],
  ["activity", "Activity"], ["planner", "Planner"], ["critic", "Critic"],
];

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-9 place-items-center rounded-full bg-ink text-lime">
        <Compass size={20} aria-hidden />
      </span>
      <div>
        <div className="text-[22px] font-semibold leading-6">TripSync</div>
        <div className="text-xs text-ink-muted">Budget-first trip planner</div>
      </div>
    </div>
  );
}

function StatusLabel({ status }: { status: AgentStatus }) {
  if (status === "Working")
    return <span className="inline-flex items-center gap-1 text-[13px] font-medium"><LoaderCircle size={14} className="animate-spin" aria-hidden />Working</span>;
  if (status === "Done" || status === "Passed")
    return <span className="inline-flex items-center gap-1 text-[13px] text-success"><CircleCheck size={14} aria-hidden />{status}</span>;
  if (status === "Replanned" || status === "Needs you")
    return <span className="inline-flex items-center gap-1 text-[13px] text-warning"><TriangleAlert size={14} aria-hidden />{status}</span>;
  return <span className="inline-flex items-center gap-1 text-[13px] text-ink-muted"><Circle size={8} fill="currentColor" aria-hidden />Waiting</span>;
}

export function AgentPanel({ statuses }: { statuses: Statuses }) {
  return (
    <div className="rounded-nested bg-lime-soft p-4" aria-live="polite">
      <div className="t-label mb-1.5">Agents</div>
      <ul>
        {AGENTS.map(([key, label]) => (
          <li key={key} className="flex items-center justify-between border-b border-ink/10 py-2 last:border-0 text-[15px]">
            <span>{label}</span>
            <StatusLabel status={statuses[key] ?? "Waiting"} />
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Sidebar({ statuses, llm, onNewTrip }: { statuses: Statuses; llm: string[]; onNewTrip: () => void }) {
  return (
    <aside className="hidden lg:flex w-[232px] shrink-0 flex-col gap-5 border-r border-line bg-surface px-4 py-6 sticky top-0 h-screen">
      <Brand />
      <Button onClick={onNewTrip} className="w-full"><Plus size={18} aria-hidden />New trip</Button>
      <AgentPanel statuses={statuses} />
      <p className="t-small mt-auto">
        Language model: {llm.length ? llm.join(" → ") : "off (rule-based mode)"}
      </p>
    </aside>
  );
}

/** Below 1024px the sidebar becomes a compact top bar. */
export function TopBar({ onNewTrip }: { onNewTrip: () => void }) {
  return (
    <header className="lg:hidden flex items-center justify-between border-b border-line bg-surface px-4 py-3 sticky top-0 z-[1000]">
      <Brand />
      <button onClick={onNewTrip} aria-label="New trip" className="grid size-12 place-items-center rounded-full bg-paper hover:brightness-95">
        <Plus size={20} aria-hidden />
      </button>
    </header>
  );
}
