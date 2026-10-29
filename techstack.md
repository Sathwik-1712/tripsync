# TripSync tech stack

Everything is free. Versions are what is installed in this repo as of 27 Oct 2026.

## Frontend (`frontend/`)

| Layer | Choice | Why |
|---|---|---|
| UI framework | **React 19** + **TypeScript** | Component model fits the design system (cards, chips, ticket, timeline) |
| Build / dev server | **Vite 8** | Fast dev server; proxies `/api` to the backend |
| Styling | **Tailwind CSS 4** (`@tailwindcss/vite`) | Design tokens from `design.md` live in `src/index.css` under `@theme` (`bg-paper`, `bg-lime`, `rounded-card`, …) |
| Font | **Outfit** (Google Fonts) | Specified in `design.md`; tabular numbers for prices |
| Icons | **lucide-react** | Outline, 2px stroke, as `design.md` requires (no emoji) |
| Map | **Leaflet** + **react-leaflet 5**, OpenStreetMap tiles | Day-coloured pins and routes; free, no key |
| Live agent progress | **Server-Sent Events** over `fetch` | Each agent's status streams in as it finishes |

Replaces the earlier Streamlit + streamlit-folium prototype.

## Backend (`backend/`)

| Layer | Choice | Cost | Notes |
|---|---|---|---|
| API | **FastAPI** + **Uvicorn** | Free | `tripsync/api.py`; also serves `frontend/dist` in production |
| Agent orchestration | **LangGraph** (+ LangChain core) | Free | Graph, parallel fan-out, `interrupt()`, conditional replanning |
| Memory / persistence | SQLite + LangGraph **SqliteSaver** | Free | Trip state per thread; enables refinement chat |
| LLM (primary) | Groq free tier (`openai/gpt-oss-120b`) | Free | Optional; used for parsing and short reviews |
| LLM (backup) | Gemini API (`gemini-flash-lite-latest`) | Free tier | Optional |
| LLM (local fallback) | Ollama (Llama 3.1 8B) | Free | Optional; rule-based mode works with no LLM at all |
| Structured output | Pydantic v2 | Free | |
| Weather | Open-Meteo (forecast + archive) | Free, no key | |
| Geocoding | City table → Nominatim | Free, no key | 1 req/s, proper User-Agent |
| Places | Overpass API → Wikivoyage listings → bundled sights CSV | Free, no key | Circuit breaker when public servers are down; Wikivoyage also supplies restaurants for meal slots |
| Routing | OSRM table API → haversine estimate | Free, no key | |
| Destination info | Wikivoyage API; photo from Wikipedia (Wikimedia Commons) | Free | |
| Flights | **Kiwi.com MCP** (Streamable HTTP, own small client) → SerpApi → **fast-flights** → static CSV | Free, no key for Kiwi | All prices labelled estimates |
| Hotels | **LiteAPI** (sandbox key) → SerpApi → OSM + price table | Free tier | |
| Opening hours | OSM `opening_hours` tag, own parser (`tools/hours.py`) | Free | Common formats; unknown formats are ignored |
| Train / bus | Static route CSV → distance estimate | Free | |
| Currency | Frankfurter | Free, no key | |
| Caching | requests-cache (SQLite) | Free | Raw API replies |
| Travel database | SQLite via Python `sqlite3` (`tripsync/db.py`) | Free | Places, hotels and prices, fares, routes, trips; reused across trips |
| Tests | pytest + FastAPI TestClient | Free | Offline, deterministic |
| Evaluation | `backend/eval.py`, 16 test trips | Free | Finish rate, budget fit, invented places, replanning rounds |
| Tracing | LangSmith free tier | Free | Optional, via `.env` |

## Runtime

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 (installed user-wide with `uv python install 3.12 --default`) | macOS system Python 3.9 is too old for LangGraph |
| Node.js / npm | 24 / 11 | |

No virtual environment: backend packages are installed straight into Python 3.12
(`uv pip install --system --break-system-packages --python python3.12 -r backend/requirements.txt`).

## Deployment

Build the frontend (`npm run build`), then one Uvicorn process serves both the API and the built site.
Free hosts that run a Python web process work (e.g. Hugging Face Spaces with Docker, Render free tier).
