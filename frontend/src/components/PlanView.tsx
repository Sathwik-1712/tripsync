import { useState } from "react";
import {
  ArrowRight, BedDouble, Bus, Calendar, Car, ChevronDown, CloudRain, Download, ExternalLink, Footprints, ListChecks,
  LogOut, Map as MapIcon, MapPin, Navigation, Plane, Send, Sun, TrainFront, Users, UtensilsCrossed, Wallet,
  type LucideIcon,
} from "lucide-react";
import {
  exportUrl, type Arrival, type Category, type Change, type Day, type Departure, type FlightLeg, type Original,
  type PlanView as Plan, type Replan, type RouteLeg, type TripRequest,
} from "../api";
import { PRIORITY_LABEL } from "../priority";
import { capitalize, fmtDay, hhmm, inr, kindLabel, plural, weekday } from "../format";
import { AgentMessage } from "./AgentMessage";
import { StayOptions, TransportOptions } from "./Options";
import { Hills } from "./Hills";
import { TripMap } from "./TripMap";
import { Button, Card, Chip, Notice, PillGroup, Status, Tag } from "./ui";

const MODE_ICON: Record<string, LucideIcon> = { train: TrainFront, bus: Bus, flight: Plane };
const SUGGESTIONS = ["Make day 2 lighter", "Cheaper stay", "Go by train", "More indoor", "Add museums"];

// ---------- header ----------

function Header({ req, view, setView }: { req: TripRequest; view: "Plan" | "Map"; setView: (v: "Plan" | "Map") => void }) {
  const days = Math.round((+new Date(req.end_date) - +new Date(req.start_date)) / 86400000) + 1;
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="t-label">Your plan</p>
        <h1 className="t-display mt-1">{req.destination}, {plural(days, "day")}</h1>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip icon={Calendar}>{fmtDay(req.start_date)} – {fmtDay(req.end_date)}</Chip>
          <Chip icon={Users}>{plural(req.travellers, "traveller")}</Chip>
          <Chip icon={MapPin}>From {req.origin}</Chip>
          <Chip icon={Wallet}>Budget {inr(req.budget_inr)}</Chip>
        </div>
      </div>
      <PillGroup label="View" options={["Plan", "Map"] as const} value={view} onChange={setView} />
    </header>
  );
}

// ---------- feature card: stay ----------

function StayCard({ plan }: { plan: Plan }) {
  const [broken, setBroken] = useState(false);
  const { stay, destination: dest, request } = plan;
  const img = dest.image && !broken;
  return (
    <section className="overflow-hidden rounded-card bg-sage animate-fade-in" aria-label="Your stay">
      <div className="relative h-[200px] sm:h-[260px]">
        {img ? <img src={dest.image!} alt={`${dest.city}`} onError={() => setBroken(true)} className="size-full object-cover" />
          : <Hills className="size-full" />}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent from-45% to-black/60" />
        {img && <span className="absolute right-3.5 top-3 rounded-full bg-black/35 px-2 py-0.5 text-[11px] text-white/90">Photo: Wikimedia Commons</span>}
        <div className="absolute inset-x-6 bottom-5 text-white">
          <p className="text-sm text-white/90">Your base · {capitalize(stay.tier)} stay</p>
          <h2 className="t-h2">{stay.name}</h2>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 px-7 pb-6 pt-5">
        <div className="flex flex-wrap gap-2">
          <Chip icon={Calendar}>{plural(stay.nights, "night")}</Chip>
          <Chip icon={BedDouble}>{plural(stay.rooms, "room")}</Chip>
          <Chip icon={Users}>{plural(request.travellers, "guest")}</Chip>
        </div>
        <div className="text-right">
          <div className="t-price">{inr(stay.total)}</div>
          <div className="t-small">Estimated, {inr(stay.nightly)} / room / night</div>
        </div>
      </div>
    </section>
  );
}

// ---------- day picker + timeline ----------

function DayPicker({ days, selected, onSelect }: { days: Day[]; selected: number; onSelect: (d: number) => void }) {
  return (
    <div role="tablist" aria-label="Days" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
      {days.map((d) => {
        const on = d.day === selected;
        return (
          <button key={d.day} role="tab" aria-selected={on} onClick={() => onSelect(d.day)}
            className={`shrink-0 rounded-full px-5 py-2 text-left leading-tight transition duration-150 ease-out
              ${on ? "bg-lime text-ink" : "bg-surface text-ink hover:brightness-95"}`}>
            <span className={`block text-xs ${on ? "text-ink" : "text-ink-muted"}`}>{weekday(d.date)}</span>
            <span className="block font-semibold">Day {d.day}</span>
          </button>
        );
      })}
    </div>
  );
}

function Row({ time, icon: Icon, title, sub, tag, muted = false }: {
  time: string; icon?: LucideIcon; title: string; sub?: string; tag?: string; muted?: boolean;
}) {
  return (
    <div className={`grid grid-cols-[56px_1fr_auto] items-start gap-4 border-t border-line py-4 ${muted ? "text-ink-muted" : ""}`}>
      <span className="num font-semibold text-ink">{time}</span>
      <div className="min-w-0">
        <h3 className="t-h3 flex items-center gap-2">{Icon && <Icon size={18} className="shrink-0" aria-hidden />}{title}</h3>
        {sub && <p className="t-small">{sub}</p>}
      </div>
      {tag && <Tag>{tag}</Tag>}
    </div>
  );
}

function Leg({ children }: { children: React.ReactNode }) {
  return <p className="flex items-center gap-1.5 py-1.5 pl-20 text-[13px] text-ink-muted"><Car size={14} aria-hidden />{children}</p>;
}

const assumedNote = "typical time, check the schedule";

function ArrivalRows({ a, mode }: { a: Arrival; mode: string }) {
  const Icon = MODE_ICON[mode] ?? TrainFront;
  const what = a.flight ? `Flight ${a.flight} lands at ${a.place}` : `Arrive at ${a.place}`;
  const from = a.depart_time && a.depart_from ? `Departs ${a.depart_from} at ${a.depart_time}` : undefined;
  return (
    <>
      <Row time={a.time} icon={Icon} title={what} sub={a.assumed ? `Arrival is a ${assumedNote}` : from} tag="Arrive" />
      <Leg>{a.transfer.minutes} min cab to {a.transfer.to} · ~{inr(a.transfer.fare)}{a.transfer.cabs > 1 ? ` for ${a.transfer.cabs} cabs` : ""}</Leg>
      <Row time={a.ready} icon={BedDouble} title="Check in and drop your bags" muted />
    </>
  );
}

function DepartureRows({ d, mode }: { d: Departure; mode: string }) {
  const Icon = MODE_ICON[mode] ?? TrainFront;
  const what = d.flight ? `Flight ${d.flight} departs ${d.place}` : `Depart from ${d.place}`;
  const sub = d.assumed ? `Departure is a ${assumedNote}`
    : d.arrive_time ? `Lands at ${d.arrive_at ?? "home"} at ${d.arrive_time}` : undefined;
  return (
    <>
      <Row time={d.leave_stay} icon={LogOut} title={`Leave for ${d.place}`}
        sub={`Be there ${mode === "flight" ? "2 h" : "45 min"} early`} muted />
      <Leg>{d.transfer.minutes} min cab · ~{inr(d.transfer.fare)}{d.transfer.cabs > 1 ? ` for ${d.transfer.cabs} cabs` : ""}</Leg>
      <Row time={d.time} icon={Icon} title={what} sub={sub} tag="Depart" />
    </>
  );
}

const LEG_MODE: Record<RouteLeg["mode"], { icon: LucideIcon; label: string }> = {
  walk: { icon: Footprints, label: "Walk" }, auto: { icon: Car, label: "Auto-rickshaw" }, cab: { icon: Car, label: "Taxi / app cab" },
};

/** Directions for one hop: where from and to, distance, time, how, cost, and a Google Maps link. */
function Directions({ leg }: { leg: RouteLeg }) {
  const m = LEG_MODE[leg.mode];
  return (
    <div className="my-1 ml-[72px] rounded-input bg-paper px-4 py-2.5 text-[13px]">
      <p className="font-medium"><span className="text-ink-muted">Route:</span> {leg.from} → {leg.to}</p>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-ink-muted">
        <span><span className="text-ink">{leg.km} km</span>{leg.source === "OSRM" ? " by road" : " (estimated)"}</span>
        <span><span className="text-ink">~{leg.minutes} min</span></span>
        <span className="inline-flex items-center gap-1"><m.icon size={13} aria-hidden /><span className="text-ink">{m.label}</span>
          {leg.fare ? ` · ~${inr(leg.fare)}` : " · free"}</span>
        <a href={leg.maps_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-ink underline">
          <Navigation size={13} aria-hidden />Google Maps directions</a>
      </p>
    </div>
  );
}

function DayTimeline({ day, mode }: { day: Day; mode: string }) {
  const w = day.weather;
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="t-label">{fmtDay(day.date)}</p>
          <h2 className="t-h2">Day {day.day} · {day.title}</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {w && <Chip icon={day.rainy ? CloudRain : Sun} className="bg-paper">{Math.round(w.tmin)}–{Math.round(w.tmax)}°C</Chip>}
          {day.rainy && <Status tone="warn">Rain likely</Status>}
          <Chip icon={Car} className="bg-paper">{day.travel_min} min on the road</Chip>
        </div>
      </div>
      <ol>
        {day.arrival && <li><ArrivalRows a={day.arrival} mode={mode} /></li>}
        {day.timeline.map((x, i) => x.type === "meal" ? (
          <li key={`${x.meal}-${i}`} className="animate-fade-in">
            <Row time={x.arrive} icon={UtensilsCrossed} title={x.name}
              sub={x.spot ? `${x.spot.price ? x.spot.price + " · " : ""}from Wikivoyage` : "No restaurant listing nearby; eat near your last stop"} muted />
            {x.spot?.maps_url && <p className="-mt-2 pb-2 pl-[72px] text-[13px]"><a className="underline" href={x.spot.maps_url}
              target="_blank" rel="noreferrer">Map</a></p>}
          </li>
        ) : (
          <li key={x.id} className="animate-fade-in">
            {x.leg ? <Directions leg={x.leg} />
              : x.leg_min > 0 && <Leg>{x.leg_min} min {day.stops[0]?.id === x.id ? "from your stay" : "drive"}</Leg>}
            <Row time={x.arrive} title={x.name} tag={kindLabel(x.kind, x.name)}
              sub={`About ${x.minutes} min · ${x.indoor ? "Indoor" : "Outdoor"} · ${x.fee ? `${inr(x.fee)} per person, estimated` : "Free entry"}${x.wait_min ? ` · opens ${x.wait_min} min after you arrive` : ""}`} />
          </li>
        ))}
        {day.return_leg && <li><Directions leg={day.return_leg} /></li>}
        {day.stops.length === 0 && !day.arrival && !day.departure && (
          <li><p className="t-small py-4">No stops planned. Time to rest or wander.</p></li>
        )}
        {day.departure && <li><DepartureRows d={day.departure} mode={mode} /></li>}
      </ol>
    </Card>
  );
}

function About({ plan }: { plan: Plan }) {
  let text = (plan.destination.summary || "").split("\n")[0];
  if (!text) return null;
  if (text.length > 420) text = text.slice(0, text.lastIndexOf(". ", 420) + 1) || text.slice(0, 420) + "…";
  return (
    <Card>
      <h2 className="t-label">About {plan.destination.city}</h2>
      <p className="mt-2">{text}</p>
      <p className="t-small mt-1">From Wikivoyage (CC BY-SA)</p>
    </Card>
  );
}

// ---------- side column ----------


function LegLine({ label, leg }: { label: string; leg: FlightLeg }) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm">
      <span className="t-label w-14 shrink-0">{label}</span>
      <span className="num font-semibold">{hhmm(leg.depart)} {leg.from}</span>
      <ArrowRight size={14} className="shrink-0 text-ink-muted" aria-hidden />
      <span className="num font-semibold">{hhmm(leg.arrive)} {leg.to}</span>
      <span className="t-small ml-auto text-right">{leg.flights.join(" + ") || leg.carrier}{leg.stops ? ` · ${plural(leg.stops, "stop")}` : " · non-stop"}</span>
    </div>
  );
}

function Ticket({ plan }: { plan: Plan }) {
  const t = plan.transport, req = plan.request;
  const Icon = MODE_ICON[t.mode] ?? TrainFront;
  const exact = Boolean(t.out?.depart);
  const where = t.mode === "train" ? "IRCTC" : t.mode === "bus" ? "redBus" : "the airline";
  return (
    <section className="flex overflow-hidden rounded-card bg-surface-raised animate-fade-in" aria-label="Transport">
      <div className="flex w-[52px] flex-col items-center justify-center gap-2.5 bg-sage py-4">
        <Icon size={20} aria-hidden />
        <span className="rotate-180 text-xs font-semibold tracking-[2px] [writing-mode:vertical-rl]">{t.mode.toUpperCase()}</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 px-5 pb-2.5 pt-5">
          <div><div className="text-[30px] font-semibold leading-9">{plan.codes.origin}</div><div className="t-small">{req.origin}</div></div>
          <ArrowRight size={22} className="text-ink-muted" aria-hidden />
          <div className="text-right"><div className="text-[30px] font-semibold leading-9">{plan.codes.destination}</div><div className="t-small">{req.destination}</div></div>
        </div>
        <div className="flex justify-between gap-2 px-5 pb-4 text-sm">
          <div><div className="t-label">Out</div>{fmtDay(req.start_date)}</div>
          <div className="text-center"><div className="t-label">Journey</div>~{t.hours} h</div>
          <div className="text-right"><div className="t-label">Return</div>{fmtDay(req.end_date)}</div>
        </div>
        {t.out && <LegLine label="Out" leg={t.out} />}
        {t.back && <LegLine label="Return" leg={t.back} />}
        {!exact && <p className="t-small border-t border-line px-5 py-3">Exact times vary; check {where} before booking.</p>}
        {exact && !t.back && <p className="t-small border-t border-line px-5 py-3">Return flight times weren't returned; check {where}.</p>}
        <div className="flex flex-wrap items-center justify-between gap-2 bg-butter px-5 py-3 text-[13px]">
          <span>{t.label} · {plural(req.travellers, "seat")} · {t.source}</span>
          <span><b className="num">{inr(t.total)}</b> {exact ? "fare" : "estimated fare"}, round trip</span>
          {t.booking_url && <a href={t.booking_url} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1 font-semibold underline">See on Kiwi.com<ExternalLink size={13} aria-hidden /></a>}
        </div>
      </div>
    </section>
  );
}

const CATS: [Category, string][] = [["transport", "Transport"], ["stay", "Stay"], ["activities", "Activities"], ["food", "Food"]];

function Budget({ plan }: { plan: Plan }) {
  const { costs, allocations: alloc, request } = plan;
  const budget = request.budget_inr;
  const overall = costs.total > budget ? <Status tone="bad">Over budget</Status>
    : costs.total > budget * 0.9 ? <Status tone="warn">Close to limit</Status> : <Status tone="ok">Within budget</Status>;
  return (
    <Card>
      <div className="flex items-center justify-between"><h2 className="t-label">Budget</h2>{overall}</div>
      <p className="mt-2"><span className="t-price">{inr(costs.total)}</span> <span className="t-small">of {inr(budget)}</span></p>
      {CATS.map(([key, label]) => {
        const pct = costs[key] / Math.max(1, alloc[key]);
        const bar = pct > 1 ? "bg-danger" : pct > 0.9 ? "bg-warning" : "bg-ink";
        return (
          <div key={key} className="mt-3.5">
            <div className="mb-1.5 flex justify-between text-sm">
              <span>{label}</span>
              <span className="num">{inr(costs[key])} / {inr(alloc[key])}{pct > 1 ? " · over" : pct > 0.9 ? " · close" : ""}</span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-label={label}
              aria-valuenow={Math.min(100, Math.round(pct * 100))} aria-valuemin={0} aria-valuemax={100}>
              <div className={`h-full rounded-full ${bar}`} style={{ width: `${Math.min(100, pct * 100)}%` }} />
            </div>
          </div>
        );
      })}
      <p className="t-small mt-3.5">{inr(alloc.buffer)} kept aside as a buffer. Prices are typical estimates.
        {costs.transfers > 0 && ` Transport includes ${inr(costs.transfers)} of airport/station cabs.`}</p>
      {plan.budget_basis.length > 0 && (
        <details className="group mt-4 rounded-nested bg-paper">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-medium">
            <span>How we split it · <span className="text-ink-muted">{PRIORITY_LABEL[plan.priority]}</span></span>
            <ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden />
          </summary>
          <ul className="grid gap-2 px-4 pb-4 text-sm">
            {plan.budget_basis.map((b) => <li key={b}>{b}</li>)}
          </ul>
        </details>
      )}
    </Card>
  );
}

const FIX: Record<string, string> = {
  transport: "the Transport Agent found a cheaper way to get there",
  accommodation: "the Accommodation Agent picked a cheaper stay",
  budget: "the Budget Agent moved money between categories",
  planner: "the Planner rebuilt the days",
  ask_user: "we asked you to decide",
  finalize: "we kept the plan with a note",
  rain_outdoor: "the Activity Agent swapped in indoor stops",
  overpacked_day: "the Activity Agent lightened that day",
  activities_over: "the Activity Agent dropped pricier tickets",
};

function CriticNote({ replans, warnings }: { replans: Replan[]; warnings: string[] }) {
  if (warnings.length) return <AgentMessage headline="Critic flagged something">{warnings[0]}.</AgentMessage>;
  if (!replans.length)
    return <AgentMessage headline="Critic passed the plan first time">Every cost is within its limit and no rain clashes with outdoor plans.</AgentMessage>;
  const first = replans[0];
  const fix = first.target === "activity" ? FIX[first.type] : FIX[first.target];
  const n = replans.length;
  return (
    <AgentMessage headline={`Critic replanned ${n === 1 ? "once" : `${n} times`}`}>
      {first.problem.replace(" is ", " was ")}, so {fix ?? "it was fixed"}.
      {n > 1 && ` ${n - 1} more fix${n > 2 ? "es" : ""} after that.`}
    </AgentMessage>
  );
}

const AREA: Record<Change["area"], string> = {
  transport: "Transport", stay: "Stay", places: "Places", schedule: "Schedule", budget: "Budget",
};

function WhatChanged({ changes, original, plan, busy, onRefine }: {
  changes: Change[]; original: Original | null; plan: Plan; busy: boolean; onRefine: (t: string) => void;
}) {
  const stayChanged = changes.some((c) => c.area === "stay");
  const transportChanged = changes.some((c) => c.area === "transport");
  // Offer a way back only when an agent replaced what you picked, not when you changed it yourself.
  const origStay = original && plan.stay_options.find((s) => original.stay.startsWith(s.name) && s.id !== plan.stay.id);
  const origTransport = original && plan.transport_options.find((o) =>
    original.transport.startsWith(o.label) && o.id !== plan.transport.id);
  return (
    <Card>
      <h2 className="t-h2">What changed and why</h2>
      {!original ? null : changes.length === 0 ? (
        <p className="mt-2">Nothing. The plan uses the stay, transport and places you chose.</p>
      ) : (
        <>
          <p className="t-small mt-1">Your choices first, then what the agents changed and why.</p>
          <ol className="mt-3 grid gap-3">
            {changes.map((c, i) => (
              <li key={i} className="rounded-input bg-paper px-4 py-3 text-sm">
                <Tag>{AREA[c.area]}</Tag>
                <div className="mt-2 grid gap-1 sm:grid-cols-[auto_1fr]">
                  <span className="text-ink-muted">Original</span><span>{c.before ?? "—"}</span>
                  <span className="text-ink-muted">Replanned</span><span className="font-medium">{c.after ?? "—"}</span>
                  <span className="text-ink-muted">Why</span><span>{c.reason}.</span>
                </div>
              </li>
            ))}
          </ol>
          {(stayChanged && origStay) || (transportChanged && origTransport) ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {stayChanged && origStay && <Button kind="soft" disabled={busy} onClick={() => onRefine(`use stay: ${origStay.id}`)}>
                Keep my original stay</Button>}
              {transportChanged && origTransport && <Button kind="soft" disabled={busy}
                onClick={() => onRefine(`use transport: ${origTransport.id}`)}>Keep my original transport</Button>}
            </div>
          ) : null}
        </>
      )}
      {original && (
        <details className="group mt-4 rounded-nested bg-paper">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-medium">
            Your original choices<ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden />
          </summary>
          <dl className="grid gap-1.5 px-4 pb-4 text-sm sm:grid-cols-[auto_1fr] sm:gap-x-4">
            <dt className="text-ink-muted">Transport</dt><dd>{original.transport}</dd>
            <dt className="text-ink-muted">Stay</dt><dd>{original.stay}</dd>
            <dt className="text-ink-muted">Must visit</dt><dd>{original.must.join(", ") || "—"}</dd>
            <dt className="text-ink-muted">Added</dt><dd>{original.add.join(", ") || "—"}</dd>
            <dt className="text-ink-muted">Optional</dt><dd>{original.optional.join(", ") || "—"}</dd>
            <dt className="text-ink-muted">Skipped</dt><dd>{original.skip.join(", ") || "—"}</dd>
          </dl>
        </details>
      )}
    </Card>
  );
}

function ChangeOptions({ plan, busy, onRefine }: { plan: Plan; busy: boolean; onRefine: (t: string) => void }) {
  const sights = plan.days.flatMap((d) => d.stops);
  return (
    <Card>
      <h2 className="t-h2">Compare and switch</h2>
      <p className="t-small mt-1">Choosing another option replans the trip around it and keeps it, even if it costs more than
        its share.</p>
      <details className="group mt-4 rounded-nested border border-line">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 font-medium">
          Flights and other transport ({plan.transport_options.length})
          <ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden />
        </summary>
        <div className="px-4 pb-4">
          <TransportOptions options={plan.transport_options} chosen={plan.transport.id} busy={busy} req={plan.request}
            codes={plan.codes} links={plan.transport_links} onChoose={(id) => onRefine(`use transport: ${id}`)} />
        </div>
      </details>
      <details className="group mt-3 rounded-nested border border-line">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 font-medium">
          Places to stay ({plan.stay_options.length})
          <ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden />
        </summary>
        <div className="px-4 pb-4">
          <StayOptions stays={plan.stay_options} chosen={plan.stay.id} busy={busy} sights={sights}
            live={plan.stay_options.some((s) => !s.estimate)} onChoose={(id) => onRefine(`use stay: ${id}`)} />
        </div>
      </details>
      <Button kind="dark" className="mt-4" disabled={busy} onClick={() => onRefine("edit places")}>
        <ListChecks size={16} aria-hidden />Edit places
      </Button>
    </Card>
  );
}

function Details({ log }: { log: string[] }) {
  return (
    <details className="group rounded-nested border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3 text-sm font-medium">
        <ChevronDown size={16} className="transition group-open:rotate-180" aria-hidden />Details
      </summary>
      <div className="px-5 pb-4">
        <p className="t-small mb-2">Every agent decision, oldest first.</p>
        <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-input bg-paper p-3 text-xs leading-5">{log.join("\n")}</pre>
      </div>
    </details>
  );
}

function Refine({ busy, onSend }: { busy: boolean; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  return (
    <section className="rounded-card bg-surface-raised p-6">
      <h2 className="t-label mb-3">Ask for a change</h2>
      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} disabled={busy} onClick={() => onSend(s)}
            className="min-h-10 rounded-full border border-line bg-surface px-4 text-sm font-medium transition hover:brightness-95 disabled:opacity-40">
            {s}
          </button>
        ))}
      </div>
      <form className="mt-4" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { onSend(text.trim()); setText(""); } }}>
        <label><span className="field-label">Your change</span>
          <div className="flex gap-2">
            <input className="field" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. swap day 1 and 3" />
            <button type="submit" aria-label="Send change" disabled={busy || !text.trim()}
              className="grid size-12 shrink-0 place-items-center rounded-full bg-ink text-surface transition hover:brightness-110 disabled:opacity-40">
              <Send size={18} aria-hidden />
            </button>
          </div>
        </label>
      </form>
    </section>
  );
}

// ---------- page ----------

export function PlanView({ plan, threadId, busy, onRefine }: { plan: Plan; threadId: string; busy: boolean; onRefine: (t: string) => void }) {
  const [view, setView] = useState<"Plan" | "Map">("Plan");
  const [selected, setSelected] = useState(1);
  const day = plan.days.find((d) => d.day === selected) ?? plan.days[0];
  return (
    <div className="grid gap-6">
      <Header req={plan.request} view={view} setView={setView} />
      {plan.warnings.map((w) => <Notice key={w} tone="warn">{w}.</Notice>)}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="grid min-w-0 content-start gap-5">
          {view === "Plan" ? <StayCard plan={plan} /> : (
            <section className="overflow-hidden rounded-card bg-surface animate-fade-in">
              <TripMap plan={plan} selectedDay={day.day} />
              <p className="t-small flex items-center gap-1.5 px-6 py-3"><MapIcon size={16} aria-hidden />
                Pins are numbered day.stop; H is your stay. Travel times via {plan.routing}.</p>
            </section>
          )}
          <DayPicker days={plan.days} selected={day.day} onSelect={setSelected} />
          <DayTimeline day={day} mode={plan.transport.mode} />
          <WhatChanged changes={plan.changes} original={plan.original} plan={plan} busy={busy} onRefine={onRefine} />
          <ChangeOptions plan={plan} busy={busy} onRefine={onRefine} />
          {view === "Plan" && <About plan={plan} />}
        </div>
        <aside className="grid content-start gap-5">
          <Ticket plan={plan} />
          <Budget plan={plan} />
          <CriticNote replans={plan.replans} warnings={plan.warnings} />
          <Details log={plan.log} />
          <a href={exportUrl(threadId)} download
            className="inline-flex h-14 items-center justify-center gap-2 rounded-full bg-lime text-base font-semibold text-ink transition hover:brightness-95">
            <Download size={18} aria-hidden />Export itinerary
          </a>
          <Refine busy={busy} onSend={onRefine} />
        </aside>
      </div>
    </div>
  );
}
