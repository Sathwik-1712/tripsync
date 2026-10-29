import { useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { Button, PillGroup } from "./ui";
import { HowItWorks } from "./HowItWorks";
import type { Priority } from "../api";
import { PRIORITIES, PRIORITY_LABEL, PRIORITY_PHRASE } from "../priority";

const PACES = ["relaxed", "moderate", "packed"] as const;
const MODES = ["any", "train", "bus", "flight"] as const;
const TIERS = ["budget", "mid", "premium"] as const;

function isoInDays(n: number) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function TripForm({ cities, interests, busy, onSubmit }: {
  cities: string[]; interests: string[]; busy: boolean; onSubmit: (text: string) => void;
}) {
  const [from, setFrom] = useState("Bengaluru");
  const [to, setTo] = useState("Goa");
  const [start, setStart] = useState(isoInDays(21));
  const [days, setDays] = useState(4);
  const [people, setPeople] = useState(2);
  const [budget, setBudget] = useState(30000);
  const [picked, setPicked] = useState<string[]>(["history", "food"]);
  const [pace, setPace] = useState<(typeof PACES)[number]>("moderate");
  const [mode, setMode] = useState<(typeof MODES)[number]>("any");
  const [tier, setTier] = useState<(typeof TIERS)[number]>("mid");
  const [priority, setPriority] = useState<Priority>("balanced");
  const [free, setFree] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    const date = new Date(start + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const parts = [`${days} days from ${from} to ${to} on ${date} for ${people} people`, `budget ₹${budget}`];
    if (picked.length) parts.push(`interested in ${picked.join(" ")}`);
    if (pace !== "moderate") parts.push(pace);
    if (mode !== "any") parts.push(`by ${mode}`);
    if (tier !== "mid") parts.push(`${tier} hotel`);
    parts.push(PRIORITY_PHRASE[priority]);
    onSubmit(parts.join(", "));
  }

  return (
    <div className="animate-fade-in">
      <p className="t-label">New trip</p>
      <h1 className="t-display mt-1">Where to next?</h1>
      <p className="t-small mt-2 max-w-xl">Tell us the basics. The agents check budget, weather and travel time before you see a plan.</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[2fr_1fr]">
        <form onSubmit={submit} className="rounded-card bg-surface p-6 sm:p-7 grid gap-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label><span className="field-label">From</span>
              <select className="field" value={from} onChange={(e) => setFrom(e.target.value)}>
                {cities.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label><span className="field-label">To</span>
              <select className="field" value={to} onChange={(e) => setTo(e.target.value)}>
                {cities.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
          </div>
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-3">
            <label className="col-span-2 sm:col-span-1"><span className="field-label">Start date</span>
              <input type="date" className="field" value={start} min={isoInDays(1)} onChange={(e) => setStart(e.target.value)} required />
            </label>
            <label><span className="field-label">Days</span>
              <input type="number" className="field num" min={1} max={14} value={days} onChange={(e) => setDays(+e.target.value)} required />
            </label>
            <label><span className="field-label">Travellers</span>
              <input type="number" className="field num" min={1} max={20} value={people} onChange={(e) => setPeople(+e.target.value)} required />
            </label>
          </div>
          <label><span className="field-label">Total budget for the group</span>
            <div className="relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-muted" aria-hidden>₹</span>
              <input type="number" className="field num pl-8" min={1000} step={500} value={budget}
                onChange={(e) => setBudget(+e.target.value)} required />
            </div>
          </label>
          <div><span className="field-label">Interests</span>
            <PillGroup label="Interests" options={interests} value={picked} onChange={setPicked} multi />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div><span className="field-label">Pace</span>
              <PillGroup label="Pace" options={PACES} value={pace} onChange={setPace} /></div>
            <div><span className="field-label">Stay</span>
              <PillGroup label="Stay" options={TIERS} value={tier} onChange={setTier} /></div>
          </div>
          <div><span className="field-label">Spend more on</span>
            <PillGroup label="Spend more on" options={PRIORITIES} value={priority} onChange={setPriority}
              renderLabel={(o) => PRIORITY_LABEL[o]} />
            <p className="t-small mt-2">That part of the budget gets a bigger share; the rest is scaled to fit.</p>
          </div>
          <div><span className="field-label">Getting there</span>
            <PillGroup label="Getting there" options={MODES} value={mode} onChange={setMode} /></div>
          <Button kind="primary" type="submit" disabled={busy || from === to} className="w-full mt-1">
            {from === to ? "Pick two different cities" : "Plan my trip"}
          </Button>
        </form>

        <div className="grid gap-6 content-start">
          <HowItWorks />
          <form className="rounded-card bg-surface p-6" onSubmit={(e) => { e.preventDefault(); if (free.trim()) onSubmit(free.trim()); }}>
            <label><span className="field-label">Or describe it in your own words</span>
              <textarea className="field h-24 py-3 resize-none" value={free} onChange={(e) => setFree(e.target.value)}
                placeholder="4 days from Delhi to Jaipur in December, 2 of us, ₹30k, love forts" />
            </label>
            <Button type="submit" className="mt-3 w-full" disabled={busy || !free.trim()}>Plan from text <ArrowRight size={18} aria-hidden /></Button>
          </form>
        </div>
      </div>
    </div>
  );
}
