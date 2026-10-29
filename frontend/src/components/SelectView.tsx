// Step before the final plan: every place found, grouped, with must / add / optional / skip marks,
// plus the stay and transport choice and a live summary. Distances are by road from the chosen hotel and
// refresh when the hotel changes. Nothing is planned until "Generate".
import { useEffect, useMemo, useState } from "react";
import { Clock, MapPin, Navigation, Sparkles, Ticket as TicketIcon, TriangleAlert } from "lucide-react";
import { getNearby, type Mark, type Nearby, type NearbyPlace, type Place, type Question, type Selection, type SelectionAnswer } from "../api";
import { fmtDay, hm, inr, kindLabel, mapsSearch, plural } from "../format";
import { StayOptions, TransportOptions } from "./Options";
import { Button, Card, Chip, Notice, PillGroup, Status, Tag } from "./ui";

const MARKS: { key: Mark; label: string }[] = [
  { key: "must", label: "Must visit" }, { key: "add", label: "Add" }, { key: "optional", label: "Optional" },
  { key: "skip", label: "Skip" },
];
const ON: Record<Mark, string> = {
  must: "bg-ink text-surface border-ink", add: "bg-lime text-ink border-lime",
  optional: "bg-butter text-ink border-butter", skip: "bg-danger-bg text-danger border-danger-bg",
};
const RIDE: Record<NearbyPlace["mode"], string> = { walk: "walk", auto: "auto-rickshaw", cab: "cab" };
const kept = (m?: Mark) => m === "must" || m === "add" || m === "optional";

function feeText(p: Place): string {
  if (p.meal) return p.price ? `Price: ${p.price}` : "Meal (covered by the food budget)";
  if (p.fee_known) return p.fee ? `Entry ${inr(p.fee)} per person` : "Free entry";
  return p.fee ? `Entry about ${inr(p.fee)} per person (estimate, not verified)` : "Usually free (not verified)";
}

function FarWarning({ p, near, from, alternatives, onSwap, onKeep }: {
  p: Place; near: NearbyPlace; from: string; alternatives: { place: Place; near: NearbyPlace }[];
  onSwap: (alt: Place) => void; onKeep: () => void;
}) {
  return (
    <div role="alert" className="rounded-input bg-warning-bg px-3.5 py-3 text-sm text-warning">
      <p className="flex items-start gap-2 font-medium"><TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
        {p.name} is far from {from}</p>
      <p className="mt-1 text-ink">{near.km} km by road: about {hm(near.minutes * 2)} there and back plus {hm(p.minutes)} there,
        and roughly {inr(near.fare * 2)} for the cab. It will share a day only with places near it, which leaves less time for
        the rest.</p>
      {alternatives.length > 0 && (
        <div className="mt-2 text-ink">
          <p className="font-medium">Closer {alternatives.length === 1 ? "option" : "options"} like it:</p>
          <ul className="mt-1 grid gap-1.5">
            {alternatives.map(({ place, near: n }) => (
              <li key={place.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>{place.name} · {n.km} km, {hm(n.minutes)}</span>
                <button type="button" onClick={() => onSwap(place)}
                  className="min-h-8 rounded-full border border-line bg-surface px-3 text-[13px] font-medium hover:brightness-95">Swap</button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <button type="button" onClick={onKeep} className="mt-2 text-[13px] font-semibold text-ink underline">Keep it anyway</button>
    </div>
  );
}

function PlaceCard({ p, mark, near, from, onMark, warning }: {
  p: Place; mark?: Mark; near?: NearbyPlace; from: string; onMark: (m?: Mark) => void; warning?: React.ReactNode;
}) {
  const marks = p.meal ? MARKS.filter((m) => m.key === "add" || m.key === "skip") : MARKS;
  const popular = p.picks && p.picks.must + p.picks.add > 0 ? p.picks.must + p.picks.add : 0;
  return (
    <li className={`grid content-start gap-2 rounded-card border p-4 transition ${mark === "skip" ? "border-line bg-surface opacity-60"
      : mark ? "border-ink bg-surface-raised" : "border-line bg-surface"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="t-h3 min-w-0">{p.name}</h3>
        <div className="flex flex-wrap gap-1.5">
          {near?.far && <Status tone="warn">Far</Status>}
          <Tag>{p.meal ? "Restaurant" : kindLabel(p.kind, p.name)}</Tag>
        </div>
      </div>
      <p className="text-sm">{p.description ?? <span className="text-ink-muted">No description available from {p.source}.</span>}</p>
      <ul className="t-small grid gap-0.5">
        <li className="flex items-start gap-1.5"><MapPin size={13} className="mt-0.5 shrink-0" aria-hidden />
          {near ? <span>{near.km} km from {from} · ~{hm(near.minutes)} by {RIDE[near.mode]}
            {near.fare ? ` · ~${inr(near.fare)} one way` : ""}{" · "}
            <a className="font-semibold underline" href={near.maps_url} target="_blank" rel="noreferrer">
              <Navigation size={12} className="mb-0.5 inline" aria-hidden /> Directions</a></span>
            : <span>Distance from the hotel not available · <a className="underline" href={mapsSearch(p.lat, p.lon)}
              target="_blank" rel="noreferrer">Map</a></span>}</li>
        <li className="flex items-center gap-1.5"><Clock size={13} aria-hidden />
          About {hm(p.minutes)} there · {p.hours ? `Hours: ${p.hours}` : "Opening hours not verified"}</li>
        <li className="flex items-center gap-1.5"><TicketIcon size={13} aria-hidden />{feeText(p)} · from {p.source}</li>
        {popular > 0 && <li>Picked by {plural(popular, "earlier traveller")}</li>}
      </ul>
      <div role="group" aria-label={`Choice for ${p.name}`} className="flex flex-wrap gap-1.5">
        {marks.map((m) => (
          <button key={m.key} type="button" aria-pressed={mark === m.key} onClick={() => onMark(mark === m.key ? undefined : m.key)}
            className={`min-h-9 rounded-full border px-3 text-sm font-medium transition
              ${mark === m.key ? ON[m.key] : "border-line bg-surface hover:brightness-95"}`}>
            {m.label}
          </button>
        ))}
      </div>
      {warning}
    </li>
  );
}

function available(sel: Selection, window?: [number, number]): number {
  const { day_start: ds, day_end: de, lunch_min: lunch } = sel.estimates;
  const [start, end] = window ?? [ds, de];
  const span = (a: number, b: number) => Math.max(0, b - a - (b - a > 180 ? lunch : 0));
  if (sel.days === 1) return span(Math.max(ds, start), Math.min(de, end));
  return span(Math.max(ds, start), de) + span(ds, Math.min(de, end)) + (sel.days - 2) * span(ds, de);
}

export function SelectView({ threadId, question, sel, busy, onConfirm }: {
  threadId: string; question: Question; sel: Selection; busy: boolean; onConfirm: (a: SelectionAnswer) => void;
}) {
  const [marks, setMarks] = useState<Record<string, Mark>>(question.defaults ?? {});
  const [stayId, setStayId] = useState(sel.stay_id);
  const [transportId, setTransportId] = useState(sel.transport.choice_id);
  const [group, setGroup] = useState<string>("all");
  const [sort, setSort] = useState<"Nearest" | "Popular">("Nearest");
  const [nearby, setNearby] = useState<Nearby>(sel.nearby);
  const [nearbyError, setNearbyError] = useState(false);
  const [kept_far, setKeptFar] = useState<Set<string>>(new Set());
  const req = sel.request;
  const stay = sel.stays.find((s) => s.id === stayId) ?? sel.stays[0];
  const transport = sel.transport.options.find((o) => o.id === transportId) ?? sel.transport.options[0];

  // Distances are from the chosen hotel: fetch them again whenever it changes.
  useEffect(() => {
    if (nearby.stay_id === stayId) return;
    let live = true;
    setNearbyError(false);
    getNearby(threadId, stayId).then((n) => live && setNearby(n)).catch(() => live && setNearbyError(true));
    return () => { live = false; };
  }, [threadId, stayId, nearby.stay_id]);

  const fresh = nearby.stay_id === stayId;
  const from = nearby.reference === "hotel" ? nearby.name ?? "your hotel" : `${req.destination} centre`;
  const near = (id: string) => (fresh ? nearby.places[id] : undefined);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of sel.places) c[p.group] = (c[p.group] ?? 0) + 1;
    return c;
  }, [sel.places]);
  const order = (list: Place[]) => [...list].sort((a, b) => sort === "Popular" ? b.score - a.score
    : (near(a.id)?.minutes ?? 1e9) - (near(b.id)?.minutes ?? 1e9));

  const sights = sel.places.filter((p) => !p.meal);
  const picked = sights.filter((p) => kept(marks[p.id]));
  const far = picked.filter((p) => near(p.id)?.far);
  const n = (m: Mark) => sel.places.filter((p) => marks[p.id] === m).length;
  const fees = picked.reduce((t, p) => t + p.fee * req.travellers, 0);
  // Far places need the ride there and back; nearby ones are chained, so count a short hop each.
  const hop = (p: Place) => { const x = near(p.id); return x?.far ? 2 * x.minutes : Math.min(x?.minutes ?? 25, 30); };
  const ride = (p: Place) => { const x = near(p.id); return x?.far ? 2 * x.fare : Math.min(x?.fare ?? sel.estimates.local_per_place, sel.estimates.local_per_place); };
  const local = picked.reduce((t, p) => t + ride(p), 0);
  const needMin = picked.reduce((t, p) => t + p.minutes + hop(p), 0);
  const haveMin = available(sel, transport?.window);
  const food = sel.estimates.food_by_tier[stay?.tier ?? "mid"] ?? 0;
  const spent = (transport?.total ?? 0) + sel.estimates.transfers + (stay?.total ?? 0) + food + fees + local;
  const left = sel.budget - spent;
  const mark = (id: string, m?: Mark) => setMarks((cur) => {
    const next = { ...cur };
    if (m) next[id] = m; else delete next[id];
    return next;
  });
  const alternatives = (p: Place) => sights
    .filter((o) => o.id !== p.id && o.group === p.group && !kept(marks[o.id]) && marks[o.id] !== "skip"
      && near(o.id) && !near(o.id)!.far)
    .sort((a, b) => near(a.id)!.minutes - near(b.id)!.minutes).slice(0, 3)
    .map((o) => ({ place: o, near: near(o.id)! }));

  return (
    <div className="grid gap-6 animate-fade-in">
      <header>
        <p className="t-label">Step 2 of 2 · Choose your trip</p>
        <h1 className="t-display mt-1">{req.destination}: pick what you want</h1>
        <div className="mt-3 flex flex-wrap gap-2">
          <Chip>{fmtDay(req.start_date)} – {fmtDay(req.end_date)}</Chip>
          <Chip>{plural(req.travellers, "traveller")}</Chip>
          <Chip>From {req.origin}</Chip>
          <Chip>Budget {inr(req.budget_inr)}</Chip>
        </div>
        <p className="mt-3 max-w-3xl">We've suggested places that fit {plural(sel.days, "day")} at your pace. Mark anything as
          must visit, add, optional or skip, and choose where to stay and how to travel. Distances are by road from the hotel
          you choose. Nothing is planned until you press Generate.</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
        <div className="grid min-w-0 content-start gap-6">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="t-h2">Places to visit</h2>
              <PillGroup label="Sort" options={["Nearest", "Popular"] as const} value={sort} onChange={setSort} />
            </div>
            <div className="mt-3 grid gap-2">
              {nearby.reference === "city centre" && fresh && <Notice tone="warn">This stay has no exact location, so distances
                are measured from {req.destination} centre. Pick a hotel with a location for exact routes.</Notice>}
              {nearbyError && <Notice tone="warn">Couldn't load distances from this hotel. Try choosing it again.</Notice>}
              {!fresh && !nearbyError && <Notice>Working out road distances from the new hotel…</Notice>}
              {fresh && nearby.source === "estimate" && <Notice tone="warn">The routing service didn't answer, so distances and
                times are straight-line estimates.</Notice>}
              {/bundled/.test(sel.places_source) && <Notice tone="warn">Live place data (OpenStreetMap) is unavailable right
                now, so some places come from our bundled list ({sel.places_source}). Hours and fees for those aren't verified.</Notice>}
              {/saved/.test(sel.places_source) && <Notice>OpenStreetMap is unavailable right now, so places come from our
                saved copy ({sel.places_source}).</Notice>}
            </div>
            {sel.places.length === 0 ? (
              <div className="mt-3"><Notice tone="warn">No places were found for {req.destination} right now. You can still
                generate the plan: days will be left free.</Notice></div>
            ) : (
              <>
                <div role="tablist" aria-label="Categories" className="mt-4 flex flex-wrap gap-2">
                  {[{ key: "all", title: "All" }, ...sel.groups.filter((g) => counts[g.key])].map((g) => (
                    <button key={g.key} role="tab" aria-selected={group === g.key} onClick={() => setGroup(g.key)}
                      className={`min-h-9 rounded-full border px-3 text-sm font-medium transition
                        ${group === g.key ? "border-ink bg-ink text-surface" : "border-line bg-surface hover:brightness-95"}`}>
                      {g.title} <span className="num opacity-70">{g.key === "all" ? sel.places.length : counts[g.key]}</span>
                    </button>
                  ))}
                </div>
                {sel.groups.filter((g) => (group === "all" || group === g.key) && counts[g.key]).map((g) => (
                  <section key={g.key} className="mt-5">
                    <h3 className="t-label mb-2">{g.title}</h3>
                    <ul className="grid gap-3 md:grid-cols-2">
                      {order(sel.places.filter((p) => p.group === g.key)).map((p) => {
                        const x = near(p.id);
                        const warn = x?.far && kept(marks[p.id]) && !kept_far.has(p.id);
                        return (
                          <PlaceCard key={p.id} p={p} mark={marks[p.id]} near={x} from={from} onMark={(m) => mark(p.id, m)}
                            warning={warn && <FarWarning p={p} near={x!} from={from} alternatives={alternatives(p)}
                              onKeep={() => setKeptFar((s) => new Set(s).add(p.id))}
                              onSwap={(alt) => setMarks((cur) => ({ ...cur, [alt.id]: cur[p.id], [p.id]: "skip" }))} />} />
                        );
                      })}
                    </ul>
                  </section>
                ))}
              </>
            )}
          </Card>
          <Card>
            <h2 className="t-h2 mb-4">Where to stay</h2>
            <StayOptions stays={sel.stays} chosen={stayId} onChoose={setStayId} live={sel.stays_live}
              sights={picked.length ? picked : sights.slice(0, 10)} />
          </Card>
          <Card>
            <h2 className="t-h2 mb-4">How to get there</h2>
            <TransportOptions options={sel.transport.options} chosen={transportId} onChoose={setTransportId}
              req={req} codes={sel.codes} links={sel.transport.links} />
          </Card>
        </div>

        <aside className="lg:sticky lg:top-6 grid content-start gap-4 self-start">
          <Card>
            <h2 className="t-label">Your selection</h2>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
              <dt>Must visit</dt><dd className="num text-right">{n("must")}</dd>
              <dt>Added</dt><dd className="num text-right">{n("add")}</dd>
              <dt>Optional</dt><dd className="num text-right">{n("optional")}</dd>
              <dt>Skipped</dt><dd className="num text-right">{n("skip")}</dd>
              {far.length > 0 && <><dt className="text-warning">Far from the hotel</dt><dd className="num text-right text-warning">{far.length}</dd></>}
            </dl>
            <hr className="my-4 border-line" />
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-sm">
              <dt>Entry fees</dt><dd className="num text-right">{inr(fees)}</dd>
              <dt>Autos/cabs between places</dt><dd className="num text-right">~{inr(local)}</dd>
              <dt>Sightseeing time needed</dt><dd className="num text-right">~{hm(needMin)}</dd>
              <dt>Time available</dt><dd className="num text-right">~{hm(haveMin)}</dd>
              <dt>Getting there</dt><dd className="num text-right">{inr((transport?.total ?? 0) + sel.estimates.transfers)}</dd>
              <dt>Stay</dt><dd className="num text-right">{inr(stay?.total ?? 0)}</dd>
              <dt>Food</dt><dd className="num text-right">{inr(food)}</dd>
            </dl>
            <div className="mt-4 flex items-baseline justify-between">
              <span className="font-medium">Budget left</span>
              <span className={`t-price ${left < 0 ? "text-danger" : ""}`}>{inr(left)}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {left < 0 ? <Status tone="bad">Over budget by {inr(-left)}</Status> : <Status tone="ok">Fits your budget</Status>}
              {needMin > haveMin && <Status tone="warn">More than fits</Status>}
            </div>
            {needMin > haveMin && <p className="t-small mt-2">Optional places are dropped first, then whatever doesn't fit;
              the plan will list what was left out and why.</p>}
            {left < 0 && <p className="t-small mt-2">If it stays over budget, the agents will look for cheaper options and show
              you every change.</p>}
            <p className="t-small mt-2">Estimates. Exact routes and times are worked out when the days are planned.</p>
            <Button kind="primary" className="mt-4 w-full" disabled={busy}
              onClick={() => onConfirm({ places: marks, stay: stayId, transport: transportId })}>
              <Sparkles size={18} aria-hidden />Generate final itinerary
            </Button>
            {picked.length === 0 && sights.length > 0 && <p className="t-small mt-2">No places picked: we'll choose from all of them.</p>}
          </Card>
        </aside>
      </div>
    </div>
  );
}
