const STEPS = [
  ["Budget first", "Your budget is split into limits for travel, stay, activities and food before anything is chosen."],
  ["Three agents search", "Transport, stays and places are found at the same time, each within its limit."],
  ["A critic checks", "Costs, rain and travel time are checked. Problems go back to the agent that can fix them."],
  ["You fine-tune", "Ask for changes like a lighter day or a cheaper stay. Only the affected agents rerun."],
];

export function HowItWorks() {
  return (
    <section className="rounded-card bg-surface p-6">
      <h2 className="t-label mb-3">How it works</h2>
      <ol className="grid gap-3.5">
        {STEPS.map(([title, text], i) => (
          <li key={title} className="flex gap-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-lime-soft text-[13px] font-semibold">{i + 1}</span>
            <span className="t-small"><b className="block text-[15px] font-semibold text-ink">{title}</b>{text}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
