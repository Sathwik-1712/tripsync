// Transport and stay options with full details, shared by the "choose your trip" step and the plan page.
import { ArrowRight, BedDouble, Bus, Check, ExternalLink, Plane, Star, TrainFront, type LucideIcon } from "lucide-react";
import type { FlightLeg, SearchLinks, Stay, TransportOption, TripRequest } from "../api";
import { capitalize, haversineKm, hhmm, hm, inr, plural } from "../format";
import { Notice, Tag } from "./ui";

const MODE_ICON: Record<string, LucideIcon> = { train: TrainFront, bus: Bus, flight: Plane };

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold underline">
      {children}<ExternalLink size={13} aria-hidden />
    </a>
  );
}

function ChooseButton({ on, disabled, onClick, label }: { on: boolean; disabled?: boolean; onClick: () => void; label: string }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled || on} aria-pressed={on} aria-label={label}
      className={`inline-flex h-10 items-center gap-1.5 rounded-full px-4 text-sm font-medium transition
        ${on ? "bg-lime text-ink" : "border border-line bg-surface hover:brightness-95 disabled:opacity-40"}`}>
      {on ? <><Check size={15} aria-hidden />Selected</> : "Choose"}
    </button>
  );
}

function legMinutes(leg: FlightLeg): number | null {
  if (leg.duration_min) return leg.duration_min;
  if (!leg.depart || !leg.arrive) return null;
  return Math.round((+new Date(leg.arrive) - +new Date(leg.depart)) / 60000);
}

function LegDetail({ title, leg }: { title: string; leg: FlightLeg }) {
  const mins = legMinutes(leg);
  return (
    <div className="rounded-input bg-paper px-4 py-3">
      <p className="t-label">{title}</p>
      <div className="mt-1 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div>
          <div className="num text-lg font-semibold">{hhmm(leg.depart) || "—"}</div>
          <div className="t-small">{leg.from_name ?? leg.from} ({leg.from})</div>
        </div>
        <div className="text-center text-xs text-ink-muted">
          <ArrowRight size={16} className="mx-auto" aria-hidden />
          {mins ? hm(mins) : ""}
        </div>
        <div className="text-right">
          <div className="num text-lg font-semibold">{hhmm(leg.arrive) || "—"}</div>
          <div className="t-small">{leg.to_name ?? leg.to} ({leg.to})</div>
        </div>
      </div>
      <p className="t-small mt-1.5">
        {leg.carrier}{leg.flights.length ? ` · ${leg.flights.join(" + ")}` : ""} ·{" "}
        {leg.stops ? `${plural(leg.stops, "stop")}${leg.via.length ? ` via ${leg.via.join(", ")}` : ""}` : "Non-stop"}
      </p>
    </div>
  );
}

function FlightCard({ o, req, codes, on, onChoose, busy }: {
  o: TransportOption; req: TripRequest; codes: { origin: string; destination: string };
  on: boolean; onChoose?: () => void; busy?: boolean;
}) {
  return (
    <li className={`grid gap-3 rounded-card border p-4 ${on ? "border-ink bg-surface-raised" : "border-line bg-surface"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="t-h3">{o.label}</h3>
          <p className="t-small">{plural(req.travellers, "seat")} · round trip · {o.source}</p>
        </div>
        <div className="text-right">
          <div className="t-price">{inr(o.total)}</div>
          <div className="t-small">total for everyone, both ways</div>
        </div>
      </div>
      {o.out && <LegDetail title={`Outbound · ${req.origin} (${codes.origin}) → ${req.destination} (${codes.destination})`} leg={o.out} />}
      {o.back ? <LegDetail title={`Return · ${req.destination} (${codes.destination}) → ${req.origin} (${codes.origin})`} leg={o.back} />
        : <p className="t-small">Return flight times weren't included in this result; check them before booking.</p>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {o.booking_url ? <ExtLink href={o.booking_url}>Book on {o.source.startsWith("Kiwi") ? "Kiwi.com" : "Google Flights"}</ExtLink> : <span />}
        {onChoose && <ChooseButton on={on} disabled={busy} onClick={onChoose} label={`Choose ${o.label}`} />}
      </div>
    </li>
  );
}

function GroundCard({ o, on, onChoose, busy, links }: {
  o: TransportOption; on: boolean; onChoose?: () => void; busy?: boolean; links: SearchLinks;
}) {
  const Icon = MODE_ICON[o.mode] ?? TrainFront;
  const where = o.mode === "train" ? { href: links.trains, name: "IRCTC" }
    : o.mode === "bus" ? { href: links.buses, name: "redBus" } : { href: links.google_flights, name: "Google Flights" };
  return (
    <li className={`flex flex-wrap items-center justify-between gap-3 rounded-card border p-4 ${on ? "border-ink bg-surface-raised" : "border-line bg-surface"}`}>
      <div className="flex items-start gap-3">
        <Icon size={20} className="mt-0.5 shrink-0" aria-hidden />
        <div>
          <h3 className="t-h3">{o.label}</h3>
          <p className="t-small">About {o.hours} h each way · typical fare from {o.source}; no live timetable</p>
          <ExtLink href={where.href}>Check times on {where.name}</ExtLink>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right"><div className="num font-semibold">{inr(o.total)}</div><div className="t-small">estimated, round trip</div></div>
        {onChoose && <ChooseButton on={on} disabled={busy} onClick={onChoose} label={`Choose ${o.label}`} />}
      </div>
    </li>
  );
}

export function TransportOptions({ options, chosen, onChoose, req, codes, links, busy }: {
  options: TransportOption[]; chosen: string; onChoose?: (id: string) => void; req: TripRequest;
  codes: { origin: string; destination: string }; links: SearchLinks; busy?: boolean;
}) {
  const flights = options.filter((o) => o.mode === "flight" && o.live);
  const ground = options.filter((o) => !(o.mode === "flight" && o.live));
  const wantsFlights = options.some((o) => o.mode === "flight");
  return (
    <div className="grid gap-4">
      <div>
        <h3 className="t-label mb-2">Flights · {req.origin} ({codes.origin}) → {req.destination} ({codes.destination})</h3>
        {flights.length ? (
          <ul className="grid gap-3">
            {flights.map((o) => <FlightCard key={o.id} o={o} req={req} codes={codes} on={o.id === chosen} busy={busy}
              onChoose={onChoose && (() => onChoose(o.id))} />)}
          </ul>
        ) : (
          <Notice tone="warn">
            {wantsFlights ? "Live flight data couldn't be retrieved right now, so no flight times or fares are shown. "
              : `No airport route was found between ${req.origin} and ${req.destination}. `}
            Search yourself: <a className="underline" href={links.google_flights} target="_blank" rel="noreferrer">Google Flights</a>
            {" · "}<a className="underline" href={links.kiwi} target="_blank" rel="noreferrer">Kiwi.com</a>
          </Notice>
        )}
      </div>
      {ground.length > 0 && (
        <div>
          <h3 className="t-label mb-2">{flights.length ? "Other ways to travel" : "Ways to travel (typical fares)"}</h3>
          <ul className="grid gap-3">
            {ground.map((o) => <GroundCard key={o.id} o={o} on={o.id === chosen} busy={busy} links={links}
              onChoose={onChoose && (() => onChoose(o.id))} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

const TIER_LABEL: Record<string, string> = { budget: "Budget", mid: "Mid-range", premium: "Premium" };

function StayRow({ s, on, onChoose, busy, sights }: {
  s: Stay; on: boolean; onChoose?: () => void; busy?: boolean; sights: { name: string; lat: number; lon: number }[];
}) {
  const near = s.lat != null && s.lon != null && sights.length
    ? sights.map((p) => ({ name: p.name, km: haversineKm([s.lat!, s.lon!], [p.lat, p.lon]) })).sort((a, b) => a.km - b.km)[0]
    : null;
  return (
    <li className={`grid gap-2 rounded-card border p-4 ${on ? "border-ink bg-surface-raised" : "border-line bg-surface"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="t-h3">{s.name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
            <Tag>{capitalize(s.kind)}</Tag>
            {s.stars ? <span className="inline-flex items-center gap-0.5">{s.stars}<Star size={13} aria-label="stars" /></span> : null}
            {s.rating ? <span>Rated {s.rating}/{s.rating_scale ?? 10}{s.reviews ? ` (${s.reviews.toLocaleString("en-IN")} reviews)` : ""}</span>
              : <span className="text-ink-muted">No rating available</span>}
          </div>
        </div>
        <div className="text-right">
          <div className="t-price">{inr(s.total)}</div>
          <div className="t-small">{inr(s.nightly)} / room / night · {plural(s.nights, "night")} × {plural(s.rooms, "room")}</div>
        </div>
      </div>
      <p className="t-small">
        {s.address ? `${s.address}. ` : ""}
        {near ? `${near.km.toFixed(1)} km from ${near.name} (straight line).` : ""}
      </p>
      {(s.amenities?.length || s.cancellation || s.board) ? (
        <p className="t-small">
          {[s.board, ...(s.amenities ?? [])].filter(Boolean).join(" · ")}
          {s.cancellation ? `${s.amenities?.length || s.board ? " · " : ""}${s.cancellation}` : ""}
        </p>
      ) : null}
      {s.estimate && <p className="t-small text-warning">{s.generic ? "Placeholder: no hotel data, price is a typical rate" : "Price is a typical rate for this tier, not a live quote"}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="t-small">{s.source}</span>
        <div className="flex items-center gap-3">
          {s.booking_url && <ExtLink href={s.booking_url}>Check prices & book</ExtLink>}
          {onChoose && <ChooseButton on={on} disabled={busy} onClick={onChoose} label={`Choose ${s.name}`} />}
        </div>
      </div>
    </li>
  );
}

export function StayOptions({ stays, chosen, onChoose, busy, live, sights }: {
  stays: Stay[]; chosen: string; onChoose?: (id: string) => void; busy?: boolean; live: boolean;
  sights: { name: string; lat: number; lon: number }[];
}) {
  return (
    <div className="grid gap-4">
      {!live && <Notice tone="warn">Live hotel data is unavailable right now. These are typical prices by tier; check real rates before booking.</Notice>}
      {(["budget", "mid", "premium"] as const).map((tier) => {
        const list = stays.filter((s) => s.tier === tier);
        if (!list.length) return null;
        return (
          <div key={tier}>
            <h3 className="t-label mb-2 flex items-center gap-1.5"><BedDouble size={15} aria-hidden />{TIER_LABEL[tier]}</h3>
            <ul className="grid gap-3">
              {list.map((s) => <StayRow key={s.id} s={s} on={s.id === chosen} busy={busy} sights={sights}
                onChoose={onChoose && (() => onChoose(s.id))} />)}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
