import { useState } from "react";
import type { Question } from "../api";
import { inr } from "../format";
import { AgentMessage } from "./AgentMessage";
import { Button } from "./ui";
import { HowItWorks } from "./HowItWorks";
import { PRIORITIES, PRIORITY_LABEL, PRIORITY_PHRASE } from "../priority";

export function QuestionCard({ question, busy, onAnswer }: { question: Question; busy: boolean; onAnswer: (t: string) => void }) {
  const [text, setText] = useState("");
  const labels: Record<string, string> = {
    raise: `Raise budget by ${inr(question.raise_by ?? 0)}`, cut: "Cut a day", accept: "Keep it as is",
  };
  return (
    <div className="animate-fade-in">
      <p className="t-label">New trip</p>
      <h1 className="t-display mt-1">Almost there</h1>
      <div className="mt-6 grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="grid gap-4 content-start">
          {question.type === "retry_cap" ? (
            <>
              <AgentMessage headline="The plan doesn't fit yet">{question.question}</AgentMessage>
              <div className="flex flex-wrap gap-3">
                {(question.options ?? []).map((o) => (
                  <Button key={o} kind={o === "raise" ? "primary" : "soft"} disabled={busy} onClick={() => onAnswer(o)}
                    className={o === "raise" ? "px-7" : "h-14"}>{labels[o]}</Button>
                ))}
              </div>
            </>
          ) : (
            <>
              <AgentMessage headline="One quick question">{question.question}</AgentMessage>
              {question.missing?.includes("priority") && question.missing.length === 1 && (
                <div className="flex flex-wrap gap-2" role="group" aria-label="Spend more on">
                  {PRIORITIES.map((p) => (
                    <Button key={p} kind={p === "balanced" ? "dark" : "soft"} disabled={busy} className="h-12"
                      onClick={() => onAnswer(PRIORITY_PHRASE[p])}>{PRIORITY_LABEL[p]}</Button>
                  ))}
                </div>
              )}
              <form className="rounded-card bg-surface-raised p-6" onSubmit={(e) => { e.preventDefault(); if (text.trim()) onAnswer(text.trim()); }}>
                <label><span className="field-label">Your answer</span>
                  <input className="field" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
                </label>
                <Button kind="dark" type="submit" className="mt-3" disabled={busy || !text.trim()}>Send answer</Button>
              </form>
            </>
          )}
        </div>
        <HowItWorks />
      </div>
    </div>
  );
}
