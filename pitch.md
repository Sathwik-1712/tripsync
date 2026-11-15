# TripSync — a budget-first AI trip planner for India

> Tell TripSync where you're going, how many of you and how much you can spend. A team of AI agents splits the
> budget, finds real flights, hotels and places, lets you choose what matters, builds the days around your hotel,
> checks its own work, and tells you exactly what it changed and why.

**Built entirely on free APIs. Runs for ₹0.**

---

## 1. The problem

Planning a trip in India today means juggling five tabs:

- **Booking sites** (MakeMyTrip, Goibibo, EaseMyTrip, Booking.com) sell flights and rooms one at a time. None of
  them tells you whether the whole trip fits your budget, or what to do once you arrive.
- **General AI chatbots** (ChatGPT, Gemini) write a nice-sounding itinerary in seconds, but:
  - they can invent places, opening hours, distances and prices;
  - they don't know your real budget split;
  - they don't check whether day 2 is physically possible.
- **AI trip-planner apps** generate day plans, but most are built for international travel. They usually ignore:
  - Indian price levels;
  - train and bus travel;
  - hill towns without an airport;
  - autos and cabs between sights.
- **Itinerary organisers** (Wanderlog, TripIt) are great notebooks, but you still do the planning yourself.

The result: plans that look good but blow the budget, put the hotel 30 km from everything, or send you to a museum
on the day it's closed.

## 2. The solution

TripSync is a **multi-agent planner that treats the budget as a hard constraint and real data as the only
source of truth**. Every number it shows comes from a live API, a stored observation or a clearly labelled
estimate.

### The traveller's journey

1. **Describe the trip.** In plain words or a form: "4 days from Bengaluru to Goa in November, 2 of us, ₹60k,
   beaches".
   - It asks only for what's missing, including what to spend more on: a nicer stay, faster travel, better food,
     more experiences, or balanced.
2. **Budget first.** Before anything is searched, the budget is split into hard limits: transport, stay,
   activities, food and a 10% buffer.
   - The split is weighted by typical costs for that city and boosted for your priority.
   - The plan shows how the split was worked out.
3. **Agents search in parallel.** Transport, Accommodation and Activity agents run at the same time, each inside
   its own limit.
4. **You choose.** Before any itinerary is built, you see:
   - **Every place found**, grouped into landmarks; nature and beaches; adventure; culture and history; food;
     shopping and nightlife; relaxation. Each shows a description, entry fee, opening hours and visit time, plus
     the **road distance, travel time, ride and fare from the hotel you pick**.
   - **Marks for each place:** **Must visit / Add / Optional / Skip**.
   - **Far-place warnings:** a place far from your hotel shows the real round-trip time and cab cost, with
     closer alternatives and a one-click **Swap**.
   - **Real hotel options** by tier: rating, reviews, amenities, cancellation policy, price per night and total.
   - **Real flights:** airline, flight number, airports, times and stops, outbound and return separately, with
     booking links. Trains and buses are listed separately.
   - **A live summary:** entry fees, time needed against time available, and budget left.
5. **Generate.** The Planner builds the days by the clock, grouped by area around your hotel, with directions for
   every hop.
6. **Self-check.** A Critic agent checks:
   - cost against every limit;
   - rain on outdoor days;
   - opening hours;
   - overpacked days;
   - places that didn't come from real data.

   Each problem goes back to the agent that can fix it.
7. **What changed and why.** Every change the agents made to your choices is listed as **original → replanned →
   reason**, and you can switch back with one click.
8. **Refine by chatting.** "Make day 2 lighter", "cheaper stay", "go by train", "swap day 1 and 3". Only the
   affected agents rerun.

---

## 3. What's new — the differentiators

| # | Idea | Why it matters |
|---|---|---|
| 1 | **Budget-first, not budget-after** | Hard per-category limits are set *before* searching. Agents must stay inside them, and a Critic enforces it. Most planners only total the cost at the end, if at all. |
| 2 | **Self-correcting agent loop** | The Critic routes each problem to the one agent that can fix it, up to 3 rounds. Then it rebalances or asks you. It never silently ships a broken plan. |
| 3 | **Can't hallucinate places** | The Planner may only use places the tools returned (OpenStreetMap, Wikivoyage, bundled list). The Critic rejects anything else. Evaluation: **0 invented places across 16 trips**. |
| 4 | **Human-in-the-loop before planning** | You pick must-visits and skips, the hotel and the flight *before* the itinerary exists. The AI plans around your choices instead of you editing its guesses. |
| 5 | **Hotel-centred geography** | Distances, times and fares are measured by road from *your* hotel. Days are grouped by area, far places get their own day, and each day's loop is untangled (2-opt). |
| 6 | **Radical transparency** | "What changed and why" lists every real change with a reason: budget moves, a cheaper stay, closed places, rain, places that didn't fit, effects of a hotel switch. It never claims a change that didn't happen. |
| 7 | **Honest data labels** | Every price, fee and opening time is either live, "seen on <date>", or "estimate, not verified". If live flights can't be fetched, it says so and links to search pages instead of inventing results. |
| 8 | **India-specific travel** | Trains and buses next to flights. Hill towns via the nearest airport (Darjeeling → Bagdogra, "then by road"). Autos vs cabs with Indian fares. Lunch and dinner at real local restaurants. ₹ formatting. |
| 9 | **It learns from every trip** | Its own SQLite travel database stores places, hotel prices, fares, routes and what travellers pick or skip. Later trips get better estimates, survive API outages, and rank popular places higher. |
| 10 | **Zero cost, graceful degradation** | Every data need has a chain of free sources, with a fallback at each step. It still works with **no API keys and no AI model**: rule-based parsing, Kiwi.com flights and bundled data. |

---

## 4. How it compares

> Based on how these products publicly worked as of October 2026. Features change often; check before quoting
> externally.

| | Booking sites (MakeMyTrip, Goibibo, Booking.com) | General chatbots (ChatGPT, Gemini) | AI trip-planner apps (e.g. Mindtrip, Layla, Wanderlog AI, buildai.space) | **TripSync** |
|---|---|---|---|---|
| Whole-trip budget as a hard limit | ✗ (per booking) | ✗ (on request, unchecked) | Partial (usually a budget label) | **✓ per-category limits + 10% buffer, enforced** |
| Real flights with numbers and times | ✓ | ✗ / sometimes via search | Varies | **✓ (Kiwi.com, Google Flights via SerpApi)** |
| Trains and buses | ✓ (separate flows) | ✗ | Rarely | **✓ in the same comparison** |
| Day-by-day itinerary | ✗ | ✓ (unverified) | ✓ | **✓ by the clock, from real places only** |
| Places guaranteed to exist | n/a | ✗ (can invent) | Mostly | **✓ enforced by a Critic** |
| Opening hours and rain checked | ✗ | ✗ | Rarely | **✓** |
| Pick must-visit / skip before planning | ✗ | Via chat | Partial | **✓ every place, with live budget and time summary** |
| Distances from *your* hotel, far warnings | ✗ | ✗ | Map view | **✓ road km, time, fare, directions, Swap** |
| Directions for every hop | ✗ | ✗ | Map only | **✓ mode, fare, Google Maps link per leg** |
| Explains every change it made | ✗ | ✗ | ✗ | **✓ "What changed and why"** |
| Learns prices and popularity over time | Internal | ✗ | Internal | **✓ own open database** |
| Cost to run | Free to browse | Subscription for best models | Freemium | **₹0 (free APIs only)** |

**In one line:** booking sites sell pieces, chatbots write stories, and planner apps draw maps. TripSync plans a
trip that fits your budget, from data it can verify, around choices you made, and shows its working.

---

## 5. Agentic flow

```
          ┌────────────┐   missing info?   ┌──────────┐
 You ───▶ │   Intake   │ ────────────────▶ │ Clarify  │ ◀── asks you (interrupt)
          └────────────┘                   └────┬─────┘
                                                ▼
                                          ┌──────────┐
                                          │  Budget  │  hard limits per category
                                          └────┬─────┘
                       ┌───────────────────────┼───────────────────────┐   parallel fan-out
                       ▼                       ▼                       ▼
                ┌────────────┐          ┌──────────────┐        ┌────────────┐
                │ Transport  │          │Accommodation │        │  Activity  │
                └─────┬──────┘          └──────┬───────┘        └─────┬──────┘
                      └────────────────────────┼──────────────────────┘
                                               ▼
                                       ┌───────────────┐
                                       │  You choose   │  places, stay, transport (interrupt, once)
                                       └───────┬───────┘
                                               ▼
                                         ┌──────────┐
                                         │ Planner  │  days by the clock, grouped around the hotel
                                         └────┬─────┘
                                              ▼
                                         ┌──────────┐  problem ──▶ routed to the agent that can fix it
                                         │  Critic  │  (max 3 rounds, then rebalance or ask you)
                                         └────┬─────┘
                                              ▼ pass
                                         ┌──────────┐
                                         │ Finalize │ ──▶ plan + "What changed and why"
                                         └────┬─────┘
                                              ▼
                                         ┌──────────┐
                                         │  Refine  │  chat edits rerun only the affected agents
                                         └──────────┘
```

### The agents

| Agent | Job | Key logic |
|---|---|---|
| **Intake + Clarify** | Turn free text into a validated trip request | Rules first (dates, ₹ amounts like "60k" / "1.5 lakh", "for 3"), AI fills gaps; geocode check; asks only for what's missing |
| **Budget** | Hard limits before anything is chosen | Weighted by typical costs for the city (or real median prices from the database); priority category gets 1.5×; reallocates or rebalances when the Critic asks |
| **Transport** | Pick a way there and back within its limit | Live flights first; schedules scored for convenience (no wasted first or last day); keeps your pick unless the trip is over budget, and logs why |
| **Accommodation** | Hotel options by tier | Live rates; cheaper in the same tier before dropping a tier; keeps your locked pick |
| **Activity** | Real places and weather | OpenStreetMap → saved copy → Wikivoyage → bundled list, deduplicated; popularity from past picks; indoor-only rainy days, fee caps, lighter days when asked |
| **You choose** | Human-in-the-loop checkpoint | LangGraph `interrupt()`; resumes with your marks, hotel and transport; asked once, then Critic loops pass straight through |
| **Planner** | Day-by-day schedule | Groups places by area around the hotel; far places get their own day; nearest-neighbour + 2-opt order; arrival/departure by the clock; meals; opening hours; road directions and fares for every hop |
| **Critic** | Code checks + short AI review | Over-limit categories, rain on outdoor stops, closed places, overpacked days, invented places; routes each to the right agent |
| **Finalize** | Wrap up | Overview text, warnings, "What changed and why" (including before/after a hotel change), saves the trip to the database |
| **Refine** | Chat edits | Maps a message to a targeted change; reruns only what's affected |

### How the Critic's problems get fixed

| Problem | Sent to | Fix |
|---|---|---|
| A category over its limit but the whole trip fits | Budget | Moves spare money in; nothing is downgraded |
| Transport / stay over and the trip doesn't fit | Transport / Accommodation | Cheaper option; a choice you asked for is dropped last |
| Rain on a day with outdoor stops | Activity | That day becomes indoor-only |
| Place closed at the planned time | Planner | Moves it to another day |
| Day too packed | Activity | Fewer stops that day |
| Still failing after 3 rounds | Budget or you | Rebalance if the total fits; otherwise raise budget / cut a day / accept |

---

## 6. Implementation highlights

- **LangGraph state machine.** A typed shared state, parallel fan-out, two human-in-the-loop interrupts (clarify,
  choose) and conditional routing. A SQLite checkpointer saves state per conversation, so trips survive restarts
  and refinements build on the last plan.
- **Clock-based planner.**
  - Real arrival times (flight legs), cab to the hotel with time and fare, 45 min to check in.
  - Sightseeing window 9:00–19:00; lunch slot 12:30–15:00, dinner from 19:30.
  - Places are scheduled only while they fit, and the planner waits up to 90 min for a place to open.
  - On the last day it leaves for the airport in time (2 h before a flight).
- **Area grouping.** Places are swept by direction from the hotel, then each day gets a share of the work in
  proportion to its free time (arrival days are shorter). Far places (over 25 km or 60 min) get a day of their own.
- **Directions.** OSRM road distance and time for every hop. Walk under 1 km, auto-rickshaw under 7 km, cab beyond.
  Typical app fares, plus a Google Maps link for each leg.
- **Opening hours.** Its own parser for OpenStreetMap `opening_hours` (common formats). The Critic flags visits
  outside opening hours.
- **Place cleaning.** Wikivoyage listings are parsed section by section (See/Do for sights, Eat for food), so
  hospitals and consulates never appear as sights. Duplicates across sources are merged by name and distance
  (under 150 m).
- **Live streaming UI.** Server-Sent Events show each agent's status (Working → Done / Replanned) as it happens.
- **Travel database** (`tripsync/db.py`, SQLite):

| Table | Holds | Used for |
|---|---|---|
| `places` | Sights and restaurants per city, merged, with must/add/skip counts | Fallback when OpenStreetMap is down; popularity ranking |
| `hotels`, `hotel_prices` | Hotel details; every price seen | Median real price per city and tier for budgets |
| `fares` | Live fares by route and month | Median fare for budgets; price trends |
| `routes` | Road km and minutes between points | No repeat routing calls for 90 days |
| `trips`, `trip_picks` | Finished plans (no names or emails) and picks | Popularity; evaluation on real trips |

---

## 7. Tech stack (all free)

| Layer | Choice |
|---|---|
| Agents | **LangGraph** (+ LangChain core), Pydantic v2 structured output |
| AI models | Groq `openai/gpt-oss-120b` → Gemini `gemini-flash-lite-latest` → local Ollama Llama 3.1 8B → rule-based (works with none) |
| API | **FastAPI** + Uvicorn, Server-Sent Events |
| Frontend | **React 19**, TypeScript, **Vite 8**, **Tailwind CSS 4**, Leaflet maps, lucide icons |
| Storage | SQLite: LangGraph checkpointer, travel database, HTTP cache (requests-cache) |
| Flights | **Kiwi.com MCP server** (no key, own Streamable-HTTP client) → SerpApi Google Flights → fast-flights |
| Hotels | **LiteAPI** → SerpApi Google Hotels → OpenStreetMap + price table |
| Places | OpenStreetMap Overpass → saved copy → Wikivoyage listings → bundled list (35 cities) |
| Routing | OSRM (road distance and time) → straight-line estimate |
| Weather | Open-Meteo forecast → last year's weather for the same dates |
| Geocoding | City table → Nominatim |
| Destination info | Wikivoyage text, Wikimedia Commons photo |
| Quality | pytest (52 offline tests), 16-trip evaluation harness, optional LangSmith tracing |

---

## 8. Results

Live evaluation on 16 varied test trips (weekend breaks, families, solo budget, premium couple, too-tight budget,
monsoon south, big group):

| Metric | Result |
|---|---|
| Trips finished | **16 / 16** |
| Within budget | **16 / 16** |
| Invented places | **0** |
| Leftover rain or closed-place conflicts | **0** |
| Average stops per day | **3.1** |
| Average replanning rounds | 2.25 |
| Average time per trip | ~18 s |
| Automated tests | **52 passing**, offline and deterministic |

---

## 9. Who it's for

- **Students and young travellers** on a fixed budget who need the whole trip to fit, not just the flight.
- **Families and groups** splitting costs: rooms, cabs and autos are counted per head, autos seat 3 and cabs seat 4.
- **First-time visitors to a city** who don't know that the "cheap" hotel is 30 km from everything.
- **Travel agents and colleges** planning group tours that need a defensible, explainable cost breakdown.

## 10. Where it could go

- **Booking hand-off:** deep links already exist; affiliate partnerships (flights, hotels) are the natural revenue
  model.
- **Accounts and shared trips:** a hosted database (Supabase or Postgres) for "My trips", collaborative editing and
  links to share.
- **Price alerts:** the fares table already tracks prices over time; "tell me when BLR→GOI drops below ₹4,000".
- **Live train data:** add timetables when a free, reliable source is available.
- **AI answers from the database:** let the agents look up stored place descriptions instead of guessing.
- **More of India:** the city table and bundled list scale to more destinations with no code changes.

## 11. Honest limitations

- Train and bus **times are typical**, not timetabled. Flights have real times.
- **LiteAPI's sandbox** returns real hotel names with test prices; production needs a live key.
- **Public OpenStreetMap and OSRM servers** are sometimes overloaded. The database and fallbacks keep it working,
  but data can be older.
- Local fares are **typical app fares**, not quotes.
- It plans and links out; **it does not book anything**.

---

## 12. Two-minute demo

1. New trip: *"4 days from Bengaluru to Goa on 18 Nov, 2 people, ₹60,000, beaches"* → asked what to spend more on
   → **Balanced**.
2. Watch the agents stream in: Budget → Transport, Accommodation, Activity in parallel.
3. **Choose screen:**
   - Mark Fort Aguada **Must visit** and skip a beach.
   - Switch the hotel to one in Anjuna and watch every distance recalculate.
   - Add a far place and see the warning with closer swaps.
   - Pick a flight.
4. **Generate:** days grouped by area, a route card for every hop, meals at real restaurants.
5. Open **What changed and why**: the budget move that paid for the flight, and places that didn't fit, each with
   a reason.
6. Switch the hotel from the plan page and see before/after time on the road and which places moved days.
7. Type *"make day 2 lighter"*: only the Planner reruns.
