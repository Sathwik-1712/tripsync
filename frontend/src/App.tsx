import { useCallback, useEffect, useState } from "react";
import { getMeta, getTrip, newTrip, sendMessage, type Meta, type Progress, type SelectionAnswer, type View } from "./api";
import { ProgressCard } from "./components/Progress";
import { PlanView } from "./components/PlanView";
import { QuestionCard } from "./components/QuestionCard";
import { SelectView } from "./components/SelectView";
import { Sidebar, TopBar } from "./components/Sidebar";
import { TripForm } from "./components/TripForm";
import { Notice } from "./components/ui";

const KEY = "tripsync.thread";

export default function App() {
  const [meta, setMeta] = useState<Meta>({ cities: [], interests: [], llm: [] });
  const [threadId, setThreadId] = useState<string | null>(null);
  const [view, setView] = useState<View | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startNew = useCallback(async () => {
    const { thread_id } = await newTrip();
    localStorage.setItem(KEY, thread_id);
    setThreadId(thread_id);
    setView({ status: "empty", statuses: {}, notice: null });
    setError(null);
  }, []);

  // Restore the last trip on reload; otherwise start a fresh one.
  useEffect(() => {
    getMeta().then(setMeta).catch(() => setError("Can't reach the TripSync server. Is the backend running on port 8000?"));
    let saved: string | null = null;
    try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
    if (saved) {
      setThreadId(saved);
      getTrip(saved).then(setView).catch(() => startNew());
    } else {
      startNew().catch(() => setError("Can't reach the TripSync server. Is the backend running on port 8000?"));
    }
  }, [startNew]);

  async function send(text: string, selection?: SelectionAnswer) {
    if (!threadId || progress) return;
    setError(null);
    setProgress({ statuses: {}, notes: [], title: "Starting…" });
    window.scrollTo({ top: 0, behavior: "smooth" });
    try {
      setView(await sendMessage(threadId, text, setProgress, selection));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setProgress(null);
    }
  }

  const statuses = progress?.statuses ?? view?.statuses ?? {};
  const busy = progress !== null;

  return (
    <div className="flex min-h-screen bg-paper">
      <Sidebar statuses={statuses} llm={meta.llm} onNewTrip={startNew} />
      <div className="min-w-0 flex-1">
        <TopBar onNewTrip={startNew} />
        <main className="mx-auto grid max-w-[1392px] gap-5 px-4 py-6 sm:px-6 lg:py-8">
          {error && <Notice tone="bad">{error}</Notice>}
          {view?.notice && !busy && <Notice>{view.notice}</Notice>}
          {progress ? <ProgressCard progress={progress} />
            : !view ? <p className="t-small">Loading…</p>
            : view.status === "plan" ? <PlanView key={threadId} plan={view} threadId={threadId!} busy={busy} onRefine={send} />
            : view.status === "question" ? <QuestionCard question={view.question} busy={busy} onAnswer={send} />
            : view.status === "select" ? <SelectView key={threadId} threadId={threadId!} question={view.question} sel={view.selection} busy={busy}
                onConfirm={(a) => send("", a)} />
            : <TripForm cities={meta.cities} interests={meta.interests} busy={busy} onSubmit={send} />}
        </main>
      </div>
    </div>
  );
}
