# TripSync: project summary (source for the project report)

> **Note for whoever writes the report from this file:** every fact and number here comes from the actual code,
> test runs and recorded trips. Please don't add features, results or numbers that aren't listed. Where a section
> of the report needs something not covered here (team names, guide, institution, dates of reviews), leave a
> placeholder for the team to fill in.

---

## 1. Title and one-line description

**TripSync: a budget-first multi-agent trip planner for India.**
You describe a trip in plain words; a team of software agents plans it day by day, keeps every cost inside your
budget, checks its own plan and fixes problems before you see it. Facts come only from real, free data services;
an AI model helps with judgement and language, and code checks every AI answer.

## 2. Abstract (draft)

Planning a trip in India on a fixed budget means juggling flights or trains, hotels, sights, local travel, food,
weather and opening hours across many websites, and most planners only add up the cost at the end. TripSync is a
web application that plans the whole trip **budget first**. The budget is split into hard limits for transport,
stay, activities and food before anything is searched. Specialised agents, built as a LangGraph workflow, then
search in parallel inside their limits using free live services (Kiwi.com flight search over MCP, LiteAPI hotels,
OpenStreetMap places, OSRM road routes, Open-Meteo weather). The traveller chooses places, stay and transport; a
Planner builds clock-timed days grouped by area; a Critic checks the plan for overspending, rain on outdoor days,
closed places, overpacked days and invented places, and sends each problem back to the one agent that can fix it.
An AI model (Groq, with Gemini as backup) is used under a strict rule, **"AI proposes, code verifies"**: it may
only choose among real options it is shown, and anything else is discarded. An "Under the hood" panel shows every
agent step, every real service call and every AI decision live. Evaluation on 16 varied trips: 16/16 finished,
16/16 within budget, 0 invented places; 62 automated offline tests pass.

## 3. Problem statement

- Trip costs are spread across transport, stay, entry fees, local travel and food; travellers overspend because
  no tool plans all of them against one budget.
- Existing planners and chat-based AI assistants either ignore the budget until the end or **invent** places,
  prices and timings that sound right but don't exist.
- A "cheap" hotel can be far from everything, so local travel time and cost are hidden.
- Weather and opening hours are rarely checked against the actual day plan.
- Users can't see *why* a plan looks the way it does.

## 4. Objectives

1. Split the budget into category limits **before** searching, weighted by the traveller's priority.
2. Use only **real data** from free services, with labelled fallbacks when a service fails.
3. Let the traveller **choose** places, stay and transport before the itinerary is built.
4. Build realistic days: by the clock, grouped by area around the hotel, respecting opening hours and weather.
5. **Self-correct**: detect problems and route each one to the agent that can fix it, with a retry limit.
6. Use AI only where it helps, with every AI answer **validated by code**, and still work with no AI at all.
7. Make the system **explainable**: show every agent step, service call and AI decision.
8. Use **free APIs only**.

## 5. Scope

- **In scope:** domestic trips within India (35 cities in the city table, nationwide via geocoding), 1 to many
  travellers, flights/trains/buses, hotels, sights, restaurants for meal slots, weather, local transfers, budget
  tracking, refinement by chat, Markdown export.
- **Out of scope:** booking and payment (TripSync links out to booking sites), user accounts, international trips,
  live train timetables.

## 6. System architecture

**Three layers:**

1. **Frontend:** React 19 + TypeScript single-page app (Vite, Tailwind CSS 4, Leaflet map). Receives live
   progress from the backend as Server-Sent Events.
2. **Backend:** FastAPI app hosting a **LangGraph** state graph of agents. Trip state is saved after every step in
   SQLite (LangGraph `SqliteSaver` checkpointer), so a trip can be paused for the user and refined later.
3. **Data layer:** free external services (each with a fallback chain), an HTTP response cache (requests-cache),
   and TripSync's own SQLite **travel database** that learns from every trip.

**Agent workflow (LangGraph graph):**

```
Intake ─▶ Clarify ─▶ Budget ─┬▶ Transport ─────┐
 (asks if anything          ├▶ Accommodation ─┼▶ You choose ─▶ Planner ─▶ Critic ─┬▶ Finalize ─▶ Refine chat
  is missing)               └▶ Activity ──────┘  (places, stay,                   │
                                   ▲              transport)                      │ problem found
                                   └────────────── agent that can fix it ◀────────┘
                                         (after 3 rounds: rebalance budget, or ask you)
```

- **Parallel fan-out:** Transport, Accommodation and Activity run at the same time.
- **Human-in-the-loop:** LangGraph `interrupt()` pauses the graph for missing details and for the choose screen;
  `Command(resume=…)` continues it with the user's answer.
- **Conditional routing:** the Critic's verdict decides the next node (a specific agent, or Finalize).
- **Retry cap:** after 3 Critic rounds, rebalance the budget if the total fits, otherwise ask the user to raise
  the budget, cut a day or accept.

## 7. The agents

| # | Agent | Job | AI involvement | File |
|---|---|---|---|---|
| 1 | Intake | Reads the request with pattern rules; AI fills only what rules missed | AI extracts fields; rules win; values validated | `agents/intake.py` |
| 2 | Clarify | Asks for anything missing or unknown (interrupt) | none | `agents/intake.py` |
| 3 | Budget | Splits budget into limits (transport, stay, activities, food, 10% buffer); priority gets 1.5× share; uses median real prices from the database when available | none | `agents/budget.py` |
| 4 | Transport | Flights (Kiwi MCP, SerpApi, fast-flights), trains/buses (route table); picks the most convenient option within limit | none | `agents/transport.py` |
| 5 | Accommodation | Hotels (LiteAPI, SerpApi, OSM + price table) by tier; picks within limit | none | `agents/accommodation.py` |
| 6 | Activity | Places (Overpass, saved copy, Wikivoyage, bundled list), restaurants, weather | **AI suggests places** from the real list, with a reason each | `agents/activity.py` |
| 7 | Review ("You choose") | Pauses with every place, stay and transport; resumes with the user's marks (must / add / optional / skip) and picks | none | `agents/review.py` |
| 8 | Planner | Clock-timed days: arrival, transfer, stops, meals, departure; groups by area (direction from hotel), orders each day (nearest neighbour + 2-opt); respects opening hours; directions and fares for every hop | none | `agents/planner.py` |
| 9 | Critic | Rule checks: category limits, total budget, rain on outdoor days, closed places, overpacked days, invented places; routes each problem to the agent that fixes it | **AI picks which problem to fix first** (among rule-allowed ones); **AI second opinion** on whether a day is too much (can send one real day back once; else tips) | `agents/critic.py` |
| 10 | Finalize | Final plan, warnings, "what changed and why", overview | **AI writes one line per day** on why its stops belong together (text only) | `agents/finalize.py` |
| 11 | Refine | Turns a follow-up ("make day 2 lighter", "cheaper stay", "go by train") into a targeted change; reruns only affected agents | AI classifies into fixed change types only | `agents/refine.py` |

**How the Critic routes problems:**

| Problem | Sent to | Fix |
|---|---|---|
| Category over limit but whole plan fits | Budget | Re-splits money around the real plan in one round |
| Transport over and plan doesn't fit | Transport | Cheaper option |
| Stay over and plan doesn't fit | Accommodation | Down a tier |
| Rain on a day with outdoor stops | Activity | Indoor-only that day |
| Place closed at planned time | Planner | Keeps it off that day |
| Day too packed | Activity | Fewer stops that day |
| Entry fees over limit | Activity | Caps fees |
| Agent already at cheapest, or food over | Budget | Moves money from buffer, then other categories |
| Still failing after 3 rounds | Budget or user | Rebalance if total fits; else ask |

## 8. "AI proposes, code verifies" (key design idea)

All AI decisions are in one file, `backend/tripsync/agents/ai.py`. Each follows the same pattern:

1. The model is shown **only real data** (numbered list of real places, the real day plan, the real problems).
2. It answers in **structured output** (Pydantic schema), choosing by **number**.
3. **Code validates**: numbers not in the list, non-existent days and duplicates are thrown away.
4. If no model answers (offline, rate limit, no key), the **rule-based choice** is used, so the app always works.
5. What the AI suggested and what the code did with it is recorded in the trace ("Checked: used / not used").

**AI models (free tiers, tried in order):** Groq `openai/gpt-oss-120b` → Google Gemini `gemini-flash-lite-latest`
→ local Ollama `llama3.1:8b` → rules only.

**Why not let the LLM plan everything?** LLMs can invent forts, prices and train times. Restricting the AI to
choosing among verified options gets its judgement without its hallucinations. Tests feed the AI deliberately
wrong answers and confirm they are rejected.

## 9. Explainability: the "Under the hood" panel

- `backend/tripsync/trace.py` wraps every graph node. While a node runs, every HTTP call, MCP call, AI call and
  database lookup is recorded with: service name, what was asked, success or failure, milliseconds, and whether the
  answer came from cache.
- Each node also reports what it was **given**, what it **decided** and **why**.
- The frontend (`UnderTheHood.tsx`) shows a timeline of agent cards, live while planning (over Server-Sent Events)
  and afterwards on the choose and plan screens. Badges: **Live**, **Saved** (cache/database), **Estimate**,
  **Failed**, **AI**. Critic send-backs appear as "Critic sent this back to the X agent". A summary line counts
  steps, real service calls and AI suggestions used.
- Optional LangSmith tracing gives the same runs in LangSmith's web UI.

## 10. Data sources (all free)

| Need | Sources, in order (first that answers wins) |
|---|---|
| AI model | Groq → Gemini → Ollama → rules |
| Flights | Kiwi.com MCP server (no key) → SerpApi Google Flights → fast-flights → route table / distance estimate |
| Train / bus | Route table (`data/transport_routes.csv`) → distance estimate |
| Hotels | LiteAPI (sandbox) → SerpApi Google Hotels → OpenStreetMap hotels + price table |
| Places | OpenStreetMap Overpass (cached 30 days) → saved copy in database → Wikivoyage listings → bundled list |
| Restaurants | Wikivoyage "Eat" listings |
| Road distance and time | OSRM → straight-line × 1.4 estimate |
| Weather | Open-Meteo forecast (16 days) → last year's weather for the same dates |
| Geocoding | City table (35 cities) → Nominatim |
| Opening hours | OpenStreetMap `opening_hours`, own parser |
| Destination text / photo | Wikivoyage, Wikipedia / Wikimedia Commons |
| Currency | Frankfurter → static rates |

Every fallback is labelled in the UI (e.g. "typical fare", "estimate", "not verified"). TripSync never invents a
flight: if none can be fetched it says so and links to Google Flights and Kiwi.com.

## 11. Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Vite 8, Tailwind CSS 4, Leaflet + react-leaflet 5, lucide-react icons, Outfit font |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Agent orchestration | LangGraph 1.x (state graph, parallel fan-out, interrupt, conditional edges), LangChain core |
| LLM access | langchain-groq, langchain-google-genai, langchain-ollama; Pydantic v2 structured output |
| Persistence | SQLite: LangGraph checkpointer, travel database (`sqlite3`), HTTP cache (requests-cache) |
| Protocols | REST + Server-Sent Events; Model Context Protocol (own Streamable-HTTP client for Kiwi.com) |
| Testing | pytest, FastAPI TestClient (offline, deterministic) |
| Evaluation | `backend/eval.py` over 16 test trips |
| Tracing | Custom trace (`trace.py`), optional LangSmith |

Code size: about 4,270 lines of backend Python, 2,000 lines of frontend TypeScript/TSX, 740 lines of tests.

## 12. Travel database (`backend/tripsync/db.py`)

SQLite file `backend/.cache/tripsync.db`, created on first use; every trip saves what it learns.

| Table | Holds | Used for |
|---|---|---|
| `places` | Sights and restaurants per city, merged across sources; fee, hours, description; must/add/skip counts | Fallback when Overpass is down; ranking popular places higher |
| `hotels`, `hotel_prices` | Hotel details; every price seen | Median real price per city and tier for budget estimates |
| `fares` | Flight prices per route and month | Median fare for budget estimates |
| `routes` | Road km and minutes between points | Skips repeat OSRM calls for 90 days |
| `trips`, `trip_picks` | Finished plans (no names or emails) and picks | Popularity; evaluation |

## 13. User interface (screens)

1. **Trip form:** from/to, dates, days, travellers, budget, interests, pace, stay level; "How it works" panel.
2. **Clarify:** a question card when something is missing; asks what to prioritise (nicer stay, faster travel,
   better food, more experiences, balanced).
3. **Live progress:** each agent's status plus "Under the hood, live".
4. **Choose screen:** every place by category with description, distance/time/fare from the chosen hotel, fee,
   hours, "Why the AI suggested it"; Must visit / Add / Optional / Skip; far-place warnings with closer swaps;
   stays by tier; transport options side by side; live summary (fees, time needed vs available, budget left).
5. **Plan:** map with day-coloured routes, day timeline with directions for every hop, travel ticket, budget
   breakdown, "What changed and why", AI tips, one-line AI explanation per day, Under the hood, Markdown export,
   refine chat.

## 14. Testing and evaluation

**Automated tests: 62 passing** (pytest, offline, no network), in `backend/tests/`:

- `test_graph.py`: whole-graph runs: budget fit, Critic routing, retry cap, user selection, empty selection,
  refinement, one-round budget rebalance.
- `test_trace.py`: every agent step is traced; calls recorded; **AI place picks keep only real places**; an
  **invalid AI "fix first" answer is rejected**; AI review can lighten one real day only once; **with no model the
  rules decide**.
- `test_data.py`, `test_providers.py`: data sources, fallbacks, unroutable routes estimated, only missing routes
  fetched.
- `test_intake.py`, `test_budget.py`, `test_api.py`: request parsing, budget split, API endpoints.

**Evaluation harness (`backend/eval.py`), 16 varied trips** (weekend breaks, families, solo budget, premium
couple, too-tight budget, monsoon south, big group):

| Metric | Live data | Offline (bundled data), latest run |
|---|---|---|
| Trips finished | 16 / 16 | 16 / 16 |
| Within budget | 16 / 16 | 16 / 16 |
| Invented places | 0 | 0 |
| Leftover rain / closed-place conflicts | 0 | 0 |
| Average replanning rounds | 2.25 (before the one-round rebalance) | 1.44 |
| Average stops per day | 3.1 | 1.6 (bundled list is small) |
| Average time per trip | ~18 s | under 1 s |

The one-round budget rebalance (Critic re-splits money when the whole trip fits) cut average replanning rounds in
the offline evaluation from 1.88 to 1.62 at the time it was added.

## 15. Sample run (recorded 31 Oct 2026)

Request: *"4 days from Bengaluru to Goa on 21 Nov 2026 for 2 people, budget ₹40000, beach and history, balanced."*

- **Intake:** rules found everything, so the AI wasn't called.
- **Budget:** typical cost ~₹39,645; stay estimate from 23 real mid-range Goa hotel prices in the database (median
  ₹5,615/night). Limits: transport ₹6,200, stay ₹15,300, activities ₹5,100, food ₹9,400, buffer ₹4,000.
- **Transport:** Kiwi.com returned 10 options (8 live); IndiGo non-stop ~₹21,736 was over limit; picked AC sleeper
  bus ₹5,600 (11 h) over train ₹4,800 (13 h).
- **Accommodation:** LiteAPI: Sort By Stays, Grand Peddem, Anjuna, rated 8.3, ₹6,363 for 3 nights.
- **Activity:** OpenStreetMap timed out after 40 s (shown as Failed); fell back to Wikivoyage + bundled list: 19
  places, 16 restaurants. **AI suggested 12 of 19**, all verified real. Weather: last year's for those dates.
- **Planner:** 4 days, 13 stops, total ₹30,073.
- **Critic:** round 1: several categories slightly over their own limits but trip ₹10,000 under budget, so sent to
  Budget to re-split (transport ₹7,781, stay ₹7,617, activities ₹8,152, food ₹12,449). Round 2 passed. AI second
  opinion added heat tips (33–34 °C) for days 1–2.
- **Finalize:** AI one-line notes per day; "What changed" explained two places left out for time.

## 16. Key differentiators

1. Budget split into hard limits **before** searching.
2. Self-correcting loop: Critic routes each problem to the one agent that can fix it, max 3 rounds.
3. AI proposes, code verifies: no invented places, prices or times; works with no AI.
4. Traveller chooses in the middle (human-in-the-loop), not after.
5. Hotel-centred planning: every distance, time and fare recalculated from the chosen hotel.
6. Live, explainable "Under the hood" view of every agent, service call and AI decision.
7. Own travel database that improves estimates and survives outages.
8. Free APIs only, with labelled fallbacks for every service; Kiwi.com flights over MCP.

## 17. Limitations

- Train and bus fares and times are typical, not timetabled; flights have real times.
- LiteAPI sandbox returns real hotel names with test prices.
- Weather more than ~2 weeks ahead uses last year's data.
- Public OpenStreetMap / OSRM servers can be slow or overloaded (fallbacks cover this; data may be older).
- Local auto/cab fares are typical estimates, not live quotes.
- fast-flights currently fails (Google changed its page); Kiwi.com and SerpApi cover flights.
- It plans and links out; it does not book.
- Late arrivals leave day 1 mostly empty apart from dinner.

## 18. Future work

- Booking hand-off via affiliate partners.
- Accounts and shared/collaborative trips (hosted Postgres).
- Price alerts from the stored fare history.
- Live train timetables when a free, reliable source exists.
- Let the AI look up stored place descriptions from the database (retrieval) instead of only choosing from lists.
- PDF export; more destinations (city table scales without code changes).

## 19. How to run

Requirements: Python 3.12, Node.js 20+ (no virtual environment).

```bash
uv pip install --system --break-system-packages --python python3.12 -r backend/requirements.txt
npm --prefix frontend install
cp backend/.env.example backend/.env      # add free API keys (all optional)
cd backend && python3.12 -m uvicorn tripsync.api:app --reload --port 8000
npm --prefix frontend run dev             # in a second terminal; open http://localhost:5173
```

Tests: `cd backend && python3.12 -m pytest -q`. Evaluation: `python3.12 eval.py --offline` or `python3.12 eval.py`.

## 20. Other documents in this repository

- `README.md`: features, setup, API, troubleshooting.
- `docs/walkthrough.md`: plain-English walkthrough of the sample run, demo script, 15 viva questions.
- `docs/pitch.md`: differentiators and results.
- `docs/techstack.md`: technology choices and versions.
- `docs/design.md`: visual design system (colours, type, components).
