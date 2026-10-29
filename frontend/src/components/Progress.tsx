import { CircleCheck, Circle, LoaderCircle } from "lucide-react";
import type { Progress as P } from "../api";
import { AgentPanel } from "./Sidebar";

const STEPS: [string, string][] = [
  ["intake", "Reading your request"], ["budget", "Checking budget"], ["transport", "Finding ways to get there"],
  ["accommodation", "Finding stays"], ["activity", "Finding places and weather"],
  ["planner", "Building the day plan"], ["critic", "Reviewing the plan"],
];

export function ProgressCard({ progress }: { progress: P }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section className="rounded-card bg-surface p-7 animate-fade-in" aria-live="polite">
        <h2 className="t-h2 mb-3">{progress.title}</h2>
        <ol>
          {STEPS.map(([key, label]) => {
            const s = progress.statuses[key];
            const done = s === "Done" || s === "Passed" || s === "Replanned";
            return (
              <li key={key} className={`flex items-center gap-3 py-2.5 text-base animate-fade-in ${!s ? "text-ink-muted opacity-60" : ""}`}>
                {done ? <CircleCheck size={20} className="text-success" aria-hidden />
                  : s === "Working" ? <LoaderCircle size={20} className="animate-spin" aria-hidden />
                  : <Circle size={10} className="mx-[5px]" fill="currentColor" aria-hidden />}
                {s === "Working" ? `${label}…` : label}
              </li>
            );
          })}
        </ol>
        {progress.notes.map((n, i) => (
          <p key={i} className="ml-8 mt-1 text-sm text-warning animate-fade-in">{n}</p>
        ))}
      </section>
      <div className="lg:hidden"><AgentPanel statuses={progress.statuses} /></div>
    </div>
  );
}
