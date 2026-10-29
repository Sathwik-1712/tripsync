"""FastAPI layer over the LangGraph workflow.

Run:  python3.12 -m uvicorn tripsync.api:app --reload --port 8000   (from backend/)
Agent progress streams to the browser as Server-Sent Events."""
import json
import os
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel

from . import llm
from .agents.intake import INTEREST_WORDS
from .config import ROOT, offline
from .graph import pending_interrupt, sqlite_graph
from .tools.geo import cities
from .view import build_view, export_markdown, nearby

app = FastAPI(title="TripSync API")
graph = sqlite_graph()

# Which agents start once a node finishes (for the live "Working" status).
NEXT = {"budget": ["transport", "accommodation", "activity"], "transport": [], "accommodation": [],
        "activity": [], "review": ["planner"], "planner": ["critic"]}
AGENTS = {"budget", "transport", "accommodation", "activity", "planner", "critic"}


class Message(BaseModel):
    text: str = ""
    selection: dict | None = None  # answer to the "choose your places" step


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _view(thread_id: str, notice: str | None = None) -> dict:
    cfg = _config(thread_id)
    view = build_view(graph.get_state(cfg).values, pending_interrupt(graph, cfg))
    view["notice"] = notice
    return view


@app.get("/api/meta")
def meta():
    return {"cities": sorted(c["city"] for k, c in cities().items() if k != "_default"),
            "interests": list(INTEREST_WORDS), "llm": llm.provider_names()}


@app.get("/api/health")
def health():
    """Which data sources are configured. Everything without a key is free and always on."""
    return {"ok": True, "offline": offline(), "llm": llm.provider_names(),
            "providers": {"flights": ["Kiwi.com MCP"] + (["SerpApi"] if os.getenv("SERPAPI_API_KEY") else [])
                          + ["fast-flights", "static CSV"],
                          "hotels": (["LiteAPI"] if os.getenv("LITEAPI_API_KEY") else [])
                          + (["SerpApi"] if os.getenv("SERPAPI_API_KEY") else []) + ["OpenStreetMap", "price table"],
                          "places": ["OpenStreetMap (Overpass)", "bundled sights"],
                          "weather": ["Open-Meteo"], "routing": ["OSRM"]}}


@app.post("/api/trips")
def new_trip():
    return {"thread_id": str(uuid.uuid4())}


@app.get("/api/trips/{thread_id}")
def get_trip(thread_id: str):
    return _view(thread_id)


@app.get("/api/trips/{thread_id}/nearby")
def nearby_places(thread_id: str, stay: str | None = None):
    """Distances, times, fares and directions from a hotel (default: the current pick) to every place."""
    values = graph.get_state(_config(thread_id)).values
    if not values.get("activities") or not values.get("stay"):
        raise HTTPException(404, "This trip has no places or hotels yet.")
    return nearby(values, stay)


@app.get("/api/trips/{thread_id}/export.md", response_class=PlainTextResponse)
def export(thread_id: str):
    values = graph.get_state(_config(thread_id)).values
    if not values.get("final"):
        raise HTTPException(404, "No finished plan for this trip yet.")
    return PlainTextResponse(export_markdown(values), headers={
        "Content-Disposition": f'attachment; filename="tripsync-{values["request"]["destination"].lower()}.md"'})


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/api/trips/{thread_id}/messages")
def send_message(thread_id: str, msg: Message):
    """Start a trip, answer a question, or ask for a change. Streams progress, then the final view."""
    cfg = _config(thread_id)
    asked = pending_interrupt(graph, cfg)
    refining = not asked and bool(graph.get_state(cfg).values.get("final"))
    if not asked and not refining and not msg.text.strip():
        raise HTTPException(422, "Message text is empty.")
    answer = msg.text
    if asked and asked.get("type") == "select":  # never resume with a falsy value: LangGraph would ask again
        answer = {"accept": True, **(msg.selection or {})}
    payload = Command(resume=answer) if asked else {"user_message": msg.text}

    def events():
        live = {} if refining else {"intake": "Working"}
        notes, notice = [], None
        title = "Updating your plan" if refining else "Planning your trip"
        yield _sse("progress", {"statuses": live, "notes": notes, "title": title})
        try:
            for chunk in graph.stream(payload, cfg, stream_mode="updates"):
                for node, upd in chunk.items():
                    upd = upd or {}
                    if node in ("intake", "clarify"):
                        live["intake"], live["budget"] = "Done", "Working"
                    elif node == "refine":
                        if upd.get("reply"):
                            notice = upd["reply"]
                        elif upd.get("next_agent"):
                            live[upd["next_agent"]] = "Working"
                    elif node == "critic":
                        target = upd.get("next_agent")
                        if not upd.get("violations"):
                            live["critic"] = "Passed"
                        else:
                            live["critic"] = "Replanned"
                            if upd.get("replans"):
                                notes.append(f'{upd["replans"][-1]["problem"]}. Sending it back to the '
                                             f'{target.replace("_", " ")} step.')
                            if target in AGENTS:
                                live[target] = "Working"
                    elif node in NEXT:
                        live[node] = "Done"
                        for nxt in NEXT[node]:
                            live[nxt] = "Working"
                    yield _sse("progress", {"statuses": live, "notes": notes, "title": title})
        except Exception as e:  # noqa: BLE001 - surface to the UI instead of a broken stream
            yield _sse("error", {"message": f"Something went wrong while planning: {e}"})
            return
        yield _sse("done", _view(thread_id, notice))

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Serve the built React app (frontend/dist) when it exists, so one command runs everything.
DIST = ROOT.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
