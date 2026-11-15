"""A readable record of every agent step, for the "Under the hood" view.

While a graph node runs, every outside call it makes (HTTP APIs, the Kiwi MCP server, saved routes, the AI
model) is recorded here. When the node finishes, `traced` turns those calls plus the node's own explanation
into one trace entry: which agent ran, what it was given, which services it called, what it decided and why,
and what the AI suggested and whether the code accepted it."""
import inspect
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from urllib.parse import urlparse

from langchain_core.runnables import RunnableConfig

_step: ContextVar[dict | None] = ContextVar("trace_step", default=None)

# Host fragment -> name shown to the traveller.
SERVICES = [
    ("router.project-osrm.org", "OSRM (road routes)"), ("overpass", "OpenStreetMap (Overpass)"),
    ("nominatim", "OpenStreetMap (Nominatim)"), ("open-meteo", "Open-Meteo (weather)"),
    ("liteapi", "LiteAPI (hotels)"), ("serpapi", "SerpApi (Google)"), ("wikivoyage", "Wikivoyage"),
    ("wikipedia", "Wikipedia"), ("wikimedia", "Wikipedia"), ("kiwi", "Kiwi.com (flights, MCP)"),
    ("frankfurter", "Frankfurter (exchange rates)"), ("google.com/travel", "Google Flights"),
]


def service_name(url: str) -> str:
    low = url.lower()
    return next((name for frag, name in SERVICES if frag in low), urlparse(url).netloc or url)


def record(service: str, what: str, ok: bool = True, ms: int = 0, cached: bool = False, kind: str = "api",
           error: str | None = None) -> None:
    """Note one outside call made by the running agent. Does nothing outside a traced node (tests, scripts)."""
    step = _step.get()
    if step is not None:
        step["calls"].append({"service": service, "what": what, "ok": ok, "ms": ms, "cached": cached,
                              "kind": kind, **({"error": error[:160]} if error else {})})


@contextmanager
def call(service: str, what: str, kind: str = "api"):
    """Time an outside call; the body may set info["cached"] = True. Failures are recorded and re-raised."""
    info, t0 = {"cached": False}, time.monotonic()
    try:
        yield info
    except Exception as e:
        record(service, what, False, round((time.monotonic() - t0) * 1000), kind=kind, error=str(e) or type(e).__name__)
        raise
    record(service, what, True, round((time.monotonic() - t0) * 1000), info["cached"], kind)


def ai(purpose: str, suggested: str, verdict: str, accepted: bool) -> None:
    """An AI suggestion and what the code did with it after checking it against real data."""
    step = _step.get()
    if step is not None:
        step["ai"].append({"purpose": purpose, "suggested": suggested[:600], "verdict": verdict, "accepted": accepted})


def _entry(agent: str, step: dict, out: dict, ms: int) -> dict:
    explain = out.pop("explain", None) or {}
    logs = out.get("log") or []
    decided = explain.get("decided") or "; ".join(l.split("] ", 1)[-1] for l in logs)
    return {"agent": agent, "at": datetime.now().strftime("%H:%M:%S"), "ms": ms, "decided": decided,
            "why": explain.get("why"), "inputs": explain.get("inputs") or [], "sent_to": explain.get("sent_to"),
            "calls": step["calls"], "ai": step["ai"]}


def traced(agent: str, fn):
    """Wrap a graph node so each run adds one entry to state["trace"]. Keeps the node's signature, since
    LangGraph passes `config` only to nodes that ask for it."""
    wants_config = "config" in inspect.signature(fn).parameters

    def run(state, config):
        token = _step.set({"calls": [], "ai": []})
        t0 = time.monotonic()
        try:
            out = fn(state, config) if wants_config else fn(state)
            out = dict(out or {})
            step = _step.get()
            out["trace"] = [_entry(agent, step, out, round((time.monotonic() - t0) * 1000))]
            return out
        finally:
            _step.reset(token)

    if wants_config:
        def node(state: dict, config: RunnableConfig) -> dict:
            return run(state, config)
    else:
        def node(state: dict) -> dict:
            return run(state, None)
    node.__name__ = node.__qualname__ = fn.__name__
    return node
