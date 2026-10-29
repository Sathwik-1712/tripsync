# TripSync

A budget-first trip planner for India. You describe a trip ("4 days from Delhi to Jaipur in December, 2 of us,
₹30k, love forts"), and a team of AI agents plans it day by day, checks every cost against your budget, and fixes
its own mistakes before you see the plan.

Built with LangGraph, FastAPI and React, using only free APIs.

## What it does

- **Budget first, your way.** It asks what matters most (a nicer stay, faster travel, better food, more
  experiences, or balanced). Your budget is split into limits for transport, stay, activities and food (plus a 10%
  buffer) *before* anything is chosen, with your priority getting 1.5× its usual share. The plan shows how the
  split was worked out. Every agent works inside its limit.
- **Door-to-door travel plan.** Real flight numbers, airports and times (Kiwi.com / SerpApi), the cab from the
  airport or station to your stay with time and fare, check-in, and when to leave for your return.
- **Days planned by the clock.** Day 1 starts once you've arrived; the last day ends in time for your departure.
  Stops are added while they fit (3–5 a day by pace, one more for "more experiences"), with lunch and dinner slots at
  real restaurants from Wikivoyage where available.
- **Agents work in parallel.** Transport, Accommodation and Activity agents search at the same time.
- **You choose before anything is planned.** Every place found is listed by category (landmarks; nature, beaches
  and viewpoints; adventure; culture and history; food; shopping and nightlife; relaxation) with a description,
  distance from your stay, visit time, entry fee and opening hours, each marked "not verified" when the data doesn't
  say. Mark each one **Must visit**, **Add**, **Optional** or **Skip**, pick a stay and a flight/train/bus, and watch
  a live summary (fees, time needed vs available, budget left). The itinerary is built only when you press
  **Generate final itinerary**, and you can go back with **Edit places** at any time.
- **Real options, side by side.** Flights show airline, flight numbers, airports, times, duration, stops and total
  price for the outbound and return legs separately, with a booking link. Trains and buses are listed separately
  with typical fares and links to IRCTC / redBus. If live flight data can't be fetched, the app says so and links
  to Google Flights and Kiwi.com; it never invents flights. Towns without an airport (Darjeeling, Coorg, Munnar…)
  are searched via the nearest one and labelled "then by road". Stays are grouped budget / mid-range / premium with
  type, rating and review count, address, amenities, cancellation policy, price per night and for the whole stay.
- **Your hotel is the centre of the trip.** On the choose screen every place shows its road distance, travel time,
  suggested ride and fare *from the hotel you pick*, with a directions link, sorted nearest first. Change the hotel
  and it all recalculates. A stay without an exact location says distances are from the city centre instead.
- **Far-place warnings.** Picking a place more than 25 km or 60 min from the hotel shows the real round-trip time and
  cab cost, offers up to three closer places of the same kind (one-click **Swap**), and lets you keep it anyway.
- **Days grouped by area.** Far places get a day of their own (with anything near them); the rest are split by
  direction from the hotel so neighbours share a day, then each day's loop is untangled (nearest-neighbour + 2-opt).
- **Directions for every hop.** Hotel → place → place → hotel, each with distance, travel time, suggested mode (walk,
  auto-rickshaw or cab), typical fare and a Google Maps directions link.
- **"What changed and why."** Whenever something you chose changes (a cheaper stay to fit the budget, a different
  flight, a place moved because it's closed, a rainy day made indoor-only, a place that didn't fit), and after you
  change the hotel, transport or places yourself (time on the road before → after, local fares, which places moved to
  which day, total cost), the plan shows the original, the replanned version and the reason. Nothing is listed unless
  it actually changed; where an agent replaced your stay or transport, one click switches back.
- **Its own travel database.** Every trip saves what it learns into `backend/.cache/tripsync.db`: places (with how
  often travellers pick or skip them), hotels and every price seen, fares by route and month, and road routes. Later
  trips reuse it: saved OpenStreetMap places when Overpass is down, saved routes instead of new OSRM calls, real
  median hotel prices and fares for budget estimates, and popular places ranked higher. Stored prices are only used
  for estimates, never shown as live.
- **A Critic checks the plan** for overspending, rain on outdoor days, places that are closed, overpacked days, and
  places that didn't come from real data. Each problem goes back to the agent that can fix it.
- **Asks when it has to.** If details are missing, it asks. If the plan still doesn't fit after 3 rounds, it asks you
  to raise the budget, cut a day, or accept.
- **Real places only.** The Planner can only use places the tools actually returned (OpenStreetMap, Wikivoyage,
  or the bundled list), so it can't invent sights.
- **Refine by chatting.** "Make day 2 lighter", "cheaper stay", "go by train": only the affected agents rerun.
- **Live progress.** The UI shows each agent working as it happens, then the plan with a map, timeline, ticket and
  budget breakdown. Export the itinerary as Markdown.

## Quick start

You need **Python 3.12** and **Node.js 20+**. No virtual environment is used.

**1. Install (once)**

```bash
uv python install 3.12 --default
uv pip install --system --break-system-packages --python python3.12 -r backend/requirements.txt
npm --prefix frontend install
cp backend/.env.example backend/.env
```

**2. Run (two terminals)**

```bash
cd backend && python3.12 -m uvicorn tripsync.api:app --reload --port 8000
```

```bash
npm --prefix frontend run dev
```

**3. Open http://localhost:5173**

| Address | What it is |
|---|---|
| http://localhost:5173 | The app |
| http://localhost:8000/api/health | Which API keys and data sources are active |
| http://localhost:8000/docs | Interactive API docs |

**Single server instead:** run `npm --prefix frontend run build` once, then only the Uvicorn command, and open
http://localhost:8000.

> After editing `backend/.env`, restart the backend. Auto-reload only watches code, not `.env`.

## API keys

Everything works with **no keys at all**: requests are parsed with rules, flights come from Kiwi.com (no key), and
every data source has a fallback. Keys make it smarter and more accurate. All are free; never add a card.

| Key in `backend/.env` | Get it from | What it adds |
|---|---|---|
| `GROQ_API_KEY` | console.groq.com | AI reads free-text requests, reviews the plan, writes the overview |
| `GOOGLE_API_KEY` | aistudio.google.com | Gemini, backup if Groq fails |
| `LITEAPI_API_KEY` | dashboard.liteapi.travel (sandbox key, `sand_…`) | Real hotel names and rates (sandbox prices are test data) |
| `SERPAPI_API_KEY` | serpapi.com (250 searches/month free) | Google Flights and Google Hotels as a second source |
| `LANGSMITH_API_KEY` + `LANGSMITH_TRACING=true` | smith.langchain.com (US region) | Trace view of every agent run |
| `TRIPSYNC_USER_AGENT` | your email | OpenStreetMap services require a contact; the placeholder is rejected |

Models used: Groq `openai/gpt-oss-120b`, Gemini `gemini-flash-lite-latest`, optional local Ollama `llama3.1:8b`.
Change them with `GROQ_MODEL`, `GEMINI_MODEL`, `OLLAMA_MODEL`.

## How it works

```
Intake ─▶ Clarify ─▶ Budget ─┬▶ Transport ─────┐
 (asks if anything          ├▶ Accommodation ─┼▶ You choose ─▶ Planner ─▶ Critic ─┬▶ Final itinerary ─▶ Refine chat
  is missing)               └▶ Activity ──────┘  (places, stay,                   │
                                   ▲              transport)                      │ problem found
                                   └────────────── agent that can fix it ◀────────┘
                                         (after 3 rounds: rebalance budget, or ask you)
```

| Step | Agent | What it does | Code |
|---|---|---|---|
| 1 | Intake + Clarify | Reads the request (rules first, AI fills gaps); asks for anything missing or unknown | `agents/intake.py` |
| 2 | Budget | Splits the budget into hard limits, weighted by typical costs for that city and your priority | `agents/budget.py` |
| 3 | Transport / Accommodation / Activity | Run in parallel; each picks options inside its own limit | `agents/transport.py`, `accommodation.py`, `activity.py` |
| 3d | You choose | Pauses with every place, stay and transport option; resumes with your marks and picks (asked once; Critic loops pass straight through) | `agents/review.py` |
| 4 | Planner | Builds days by the clock from the places you kept (must-visit first, optional last): arrival, transfer, stops, meals, departure; directions and fares for every hop; respects opening hours | `agents/planner.py` |
| 5 | Critic | Code checks plus a short AI review | `agents/critic.py` |
| 6 | Router | Sends each problem to the agent that can fix it | `ROUTES` in `critic.py`, `graph.py` |
| 7 | Retry cap | After 3 rounds: rebalance if the total fits, otherwise ask you | `ask_user_node` in `critic.py` |
| 8 | Finalize | Final plan, warnings, overview | `agents/finalize.py` |
| 9 | Refine | Turns a follow-up into a targeted change; reruns only what's affected | `agents/refine.py` |

Trip state is saved per conversation in SQLite (LangGraph checkpointer), so refinements build on the last plan.

### The travel database (`tripsync/db.py`)

Plain SQLite (Python's built-in `sqlite3`), file `backend/.cache/tripsync.db`, created on first use.

| Table | Holds | Used for |
|---|---|---|
| `places` | Sights and restaurants per city, merged across sources; fee, hours, description; must/add/skip counts | Fallback when Overpass is down; ranking popular places higher |
| `hotels`, `hotel_prices` | Hotel details; one row per price seen (date, check-in, nights, tier) | Median real price per city and tier for budget estimates (5+ prices in 60 days) |
| `fares` | Live flight prices seen per route and travel month | Median fare for budget estimates (5+ fares) |
| `routes` | Road km and minutes between two points (OSRM) | Skip repeat OSRM calls for 90 days |
| `trips`, `trip_picks` | Each finished plan (no names or emails) and the places picked | Pick counts; evaluation on real trips |

Peek inside: `sqlite3 backend/.cache/tripsync.db "select city, count(*) from places group by city"`.
Delete the file to start fresh; tests use a throwaway in-memory copy.

### How the Critic's problems get fixed

| Problem | Sent to | Fix |
|---|---|---|
| Any category over its limit, but the whole plan fits | Budget | Moves spare money into it, so nothing is downgraded needlessly |
| Transport over its limit and the plan doesn't fit | Transport | Picks a cheaper option (a mode you asked for is dropped only after everything else) |
| Stay over its limit and the plan doesn't fit | Accommodation | Moves down a tier |
| Rain on a day with outdoor stops | Activity | Makes that day indoor-only |
| Place closed at the planned time | Planner | Keeps that place off that day |
| Day too packed | Activity | Fewer stops that day |
| Entry fees over limit | Activity | Caps entry fees |
| Agent already at its cheapest, or food over | Budget | Moves money from the buffer, then from other categories |
| Still failing after 3 rounds | Budget or you | Rebalance if the total fits; otherwise raise budget / cut a day / accept |

## Data sources

Each need has a chain: the first source that answers wins. All HTTP responses are cached on disk.

| Need | Sources, in order |
|---|---|
| AI model | Groq → Gemini → Ollama → rule-based |
| Flights | Kiwi.com MCP server (no key) → SerpApi Google Flights → fast-flights → route CSV / distance estimate. Kiwi gives flight numbers and times both ways; the agent prefers schedules that don't waste day 1 or the last day |
| Train / bus | `data/transport_routes.csv` → distance estimate |
| Hotels | LiteAPI → SerpApi Google Hotels → OpenStreetMap hotels + price table |
| Places | OpenStreetMap Overpass (cached 30 days) → Wikivoyage "See/Do" listings → `data/sights.csv` (every city covered); duplicates merged by name and distance |
| Restaurants for meal slots | Wikivoyage "Eat" listings |
| Directions between places | OSRM road distance and time → straight-line estimate; walk under 1 km, auto-rickshaw under 7 km, cab beyond; typical app fares |
| Airport/station transfers | Airport coordinates in `data/cities.csv` + OSRM drive time; fare estimated at ₹150 + ₹18/km per cab |
| City lookup | `data/cities.csv` (35 cities) → Nominatim |
| Weather | Open-Meteo forecast (up to 16 days ahead) → last year's weather for the same dates |
| Travel times | OSRM → straight-line estimate |
| Opening hours | OpenStreetMap `opening_hours` tag, parsed in `tools/hours.py` |
| Destination text and photo | Wikivoyage, Wikipedia (Wikimedia Commons) |
| Currency | Frankfurter → static rates |

All prices are shown as estimates. TripSync never books anything.

## Project structure

```
tripsync/
├── README.md
├── techstack.md            stack and versions
├── design.md               visual design system
├── backend/
│   ├── tripsync/
│   │   ├── api.py          FastAPI app; streams agent progress (Server-Sent Events)
│   │   ├── graph.py        LangGraph wiring
│   │   ├── state.py        trip state and validation
│   │   ├── llm.py          Groq → Gemini → Ollama chain
│   │   ├── view.py         state → what the UI shows; Markdown export
│   │   ├── agents/         intake, budget, transport, accommodation, activity, planner, critic, refine, finalize
│   │   └── tools/          geo, weather, places, hours, transport, stays, mcp, currency
│   ├── data/               cities.csv, sights.csv, transport_routes.csv
│   ├── tests/              pytest suite (offline, deterministic)
│   ├── eval.py             evaluation over 16 test trips
│   ├── cli.py              terminal version
│   ├── requirements.txt
│   └── .env.example        copy to .env
└── frontend/
    ├── src/App.tsx         screens: form → progress → question → plan
    ├── src/api.ts          API client and stream reader
    └── src/components/     PlanView, TripForm, TripMap, Progress, Sidebar, …
```

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Active keys and data sources |
| `GET` | `/api/meta` | Known cities, interests, active AI models |
| `POST` | `/api/trips` | New trip, returns `thread_id` |
| `POST` | `/api/trips/{id}/messages` | Body `{"text": "..."}`. Starts a trip, answers a question, or asks for a change ("use stay: <id>", "use transport: <id>", "edit places"). Answer the choose step with `{"selection": {"places": {id: "must"\|"add"\|"optional"\|"skip"}, "stay": id, "transport": id}}`. Streams `progress` events, then `done` with the view (`question`, `select` or `plan`) |
| `GET` | `/api/trips/{id}` | Current state of a trip |
| `GET` | `/api/trips/{id}/nearby?stay=<id>` | Road distance, time, ride, fare, directions and far flag from that hotel to every place |
| `GET` | `/api/trips/{id}/export.md` | Itinerary as Markdown |

## Testing

From `backend/`:

```bash
python3.12 -m pytest -q            # 52 tests, no network
python3.12 eval.py --offline       # 16 test trips, bundled data only
python3.12 eval.py                 # same trips with live data
python3.12 cli.py                  # plan a trip in the terminal
```

The evaluation reports, per trip: finished, within budget, replanning rounds, invented places (must be 0), and
leftover rain or opening-hours conflicts. Results are saved to `backend/.cache/eval.json`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Places come from the "bundled sights list" | Overpass (OpenStreetMap) is overloaded or down. It retries automatically; make sure `TRIPSYNC_USER_AGENT` has a real email |
| Planning takes 30–45 s | Overpass is slow; it's given up to 45 s before falling back. Later trips to the same city use the 30-day cache |
| Hotel shows as "Mid-range hotel near X centre" | No hotel source answered; add `LITEAPI_API_KEY` |
| `/api/health` shows no AI model | Key missing in `backend/.env`, or the backend wasn't restarted after editing it |
| Free-text request asks lots of questions | No AI model is active, so only rule-based parsing runs |
| Port already in use | Another server is running; stop it or change `--port` |

## Known limitations

- **fast-flights** fails at the moment (Google changed its page). Kiwi.com and SerpApi cover flights.
- **LiteAPI sandbox prices** are test data; real hotel names, approximate prices.
- **Train and bus times are typical, not exact**: our route data has prices and durations but no timetables, so
  arrival and departure times for them are marked as typical. Flights from Kiwi/SerpApi have real times.
- **Premium trips can under-spend**: agents pick the cheapest option that fits; choosing "Nicer stay" or "Better food"
  helps.
- **Late arrivals leave day 1 empty** apart from dinner.
- **Local fares are typical estimates** (₹30 + ₹15/km per auto, ₹100 + ₹18/km per cab), not live quotes.
- **Hotel booking links** open a Google Hotels search for that property; LiteAPI's sandbox has no public booking page.
- **Not built yet**: Wikivoyage search for the AI (RAG), PDF export.
