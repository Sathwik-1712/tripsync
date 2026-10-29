// Typed client for the FastAPI backend (backend/tripsync/api.py).

export type AgentStatus = "Waiting" | "Working" | "Done" | "Passed" | "Replanned" | "Needs you";
export type Statuses = Record<string, AgentStatus>;

export interface RouteLeg {
  from: string; to: string; km: number; minutes: number; mode: "walk" | "auto" | "cab"; fare: number;
  maps_url: string; source: string;
}
export interface Stop {
  type: "stop"; id: string; name: string; kind: string; lat: number; lon: number;
  indoor: boolean; fee: number; minutes: number; arrive: string; leg_min: number; wait_min: number;
  leg: RouteLeg | null;
}
export interface FoodSpot {
  name: string; lat: number; lon: number; price?: string | null; description?: string | null; source: string;
  maps_url?: string;
}
export interface Meal {
  type: "meal"; meal: "lunch" | "dinner"; name: string; spot: FoodSpot | null; arrive: string; minutes: number;
}
export type TimelineItem = Stop | Meal;
export interface Transfer { from: string; to: string; minutes: number; km: number; cabs: number; fare: number }
export interface Arrival {
  time: string; assumed: boolean; place: string; ready: string; flight: string | null;
  depart_time: string | null; depart_from: string | null; transfer: Transfer;
}
export interface Departure {
  time: string; assumed: boolean; place: string; leave_stay: string; flight: string | null;
  arrive_time: string | null; arrive_at: string | null; transfer: Transfer;
}
export interface Weather { date: string; tmax: number; tmin: number; precip_mm: number; source: string }
export interface Day {
  day: number; date: string; title: string; indoor_only: boolean; rainy: boolean;
  stops: Stop[]; timeline: TimelineItem[]; travel_min: number; visit_min: number; weather: Weather | null;
  return_leg: RouteLeg | null;
  arrival?: Arrival; departure?: Departure;
}
export interface FlightLeg {
  from: string; to: string; from_name: string | null; to_name: string | null; depart: string | null;
  arrive: string | null; flights: string[]; carrier: string | null; stops: number; via: string[];
  duration_min?: number | null;
}
export interface TransportOption {
  id: string; mode: string; label: string; price_pp: number; hours: number; total: number; source: string;
  live: boolean; out?: FlightLeg | null; back?: FlightLeg | null; booking_url?: string | null;
  window?: [number, number];
}
export interface SearchLinks { google_flights: string; kiwi: string; trains: string; buses: string }
export type Priority = "balanced" | "stay" | "travel" | "food" | "experiences";
export interface Stay {
  id: string; name: string; tier: string; nightly: number; nights: number; rooms: number; total: number;
  lat: number | null; lon: number | null; rating: number | null; rating_scale?: number; reviews?: number | null;
  stars?: number | null; address?: string | null; kind: string; amenities?: string[]; cancellation?: string | null;
  room?: string | null; board?: string | null; booking_url?: string | null; estimate: boolean; generic?: boolean;
  source: string;
}
export type Mark = "must" | "add" | "optional" | "skip";
export interface Place {
  id: string; name: string; kind: string; group: string; lat: number; lon: number; description: string | null;
  minutes: number; fee: number; fee_known: boolean; hours: string | null; indoor: boolean; source: string;
  price?: string | null; meal?: boolean; score: number;
  picks: { must: number; add: number; skip: number } | null;
}
export interface NearbyPlace { km: number; minutes: number; mode: RouteLeg["mode"]; fare: number; maps_url: string; far: boolean }
export interface Nearby {
  stay_id: string; reference: "hotel" | "city centre" | "none"; name?: string; source: string;
  places: Record<string, NearbyPlace>; far_km: number; far_min: number;
}
export interface Selection {
  request: TripRequest; codes: { origin: string; destination: string };
  groups: { key: string; title: string }[]; places: Place[]; places_source: string;
  stays: Stay[]; stay_id: string; stays_live: boolean;
  transport: { options: TransportOption[]; choice_id: string; links: SearchLinks; flights_live: boolean };
  home: { lat: number | null; lon: number | null };
  estimates: {
    food_by_tier: Record<string, number>; transfers: number; local_per_place: number; travel_per_place_min: number;
    lunch_min: number; day_start: number; day_end: number;
  };
  days: number; budget: number; nearby: Nearby;
}
export interface SelectionAnswer { places: Record<string, Mark>; stay: string; transport: string }
export interface Change { area: "transport" | "stay" | "places" | "schedule" | "budget"; before: string | null; after: string | null; reason: string }
export interface Original { transport: string; stay: string; must: string[]; add: string[]; optional: string[]; skip: string[] }
export interface TripRequest {
  origin: string; destination: string; start_date: string; end_date: string;
  travellers: number; budget_inr: number;
}
export type Category = "transport" | "stay" | "activities" | "food";
export interface Replan { problem: string; type: string; target: string }
export interface Question {
  type: "clarify" | "retry_cap" | "select"; question: string; raise_by?: number; options?: string[];
  missing?: string[]; defaults?: Record<string, Mark>;
}

interface Base { statuses: Statuses; notice: string | null }
export type View =
  | (Base & { status: "empty" })
  | (Base & { status: "question"; question: Question })
  | (Base & { status: "select"; question: Question; selection: Selection })
  | (Base & {
      status: "plan";
      request: TripRequest;
      codes: { origin: string; destination: string };
      transport: TransportOption;
      transport_options: TransportOption[];
      transport_links: SearchLinks;
      stay: Stay;
      stay_options: Stay[];
      destination: { city: string; lat: number; lon: number; summary: string; image: string | null };
      places_source: string;
      days: Day[];
      home: { name: string; lat: number; lon: number };
      routing: string;
      costs: Record<Category | "total" | "budget" | "entry_fees" | "local_travel" | "transfers", number>;
      transfers: { in: Transfer; out: Transfer } | null;
      budget_basis: string[];
      priority: Priority;
      allocations: Record<Category | "buffer", number>;
      replans: Replan[];
      changes: Change[];
      original: Original | null;
      warnings: string[];
      log: string[];
    });
export type PlanView = Extract<View, { status: "plan" }>;

export interface Progress { statuses: Statuses; notes: string[]; title: string }
export interface Meta { cities: string[]; interests: string[]; llm: string[] }

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json() as Promise<T>;
}

export const getMeta = () => fetch("/api/meta").then((r) => json<Meta>(r));
export const newTrip = () =>
  fetch("/api/trips", { method: "POST" }).then((r) => json<{ thread_id: string }>(r));
export const getTrip = (id: string) => fetch(`/api/trips/${id}`).then((r) => json<View>(r));
export const getNearby = (id: string, stay: string) =>
  fetch(`/api/trips/${id}/nearby?stay=${encodeURIComponent(stay)}`).then((r) => json<Nearby>(r));
export const exportUrl = (id: string) => `/api/trips/${id}/export.md`;

/** Send a message and read the Server-Sent Events stream until the final view arrives. */
export async function sendMessage(
  id: string, text: string, onProgress: (p: Progress) => void, selection?: SelectionAnswer,
): Promise<View> {
  const res = await fetch(`/api/trips/${id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(selection ? { text, selection } : { text }),
  });
  if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? "{}");
      if (event === "progress") onProgress(data as Progress);
      else if (event === "error") throw new Error(data.message);
      else if (event === "done") return data as View;
    }
  }
  throw new Error("The connection closed before the plan was ready.");
}
