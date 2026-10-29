"""Shared LangGraph state. Values are plain dicts/lists (JSON-friendly) so the
SQLite checkpointer can store them; Pydantic models validate at the edges."""
import operator
from datetime import date, timedelta
from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def add_changes(a: list | None, b: list | None) -> list:
    """Append plan changes; an item {"reset": True} starts a fresh list (a new plan after a refinement)."""
    out = list(a or [])
    for item in b or []:
        out = [] if item.get("reset") else out + [item]
    return out


class TripState(TypedDict, total=False):
    user_message: str
    request: dict            # TripRequest fields
    allocations: dict        # Budget Agent hard limits per category
    budget_action: Optional[dict]
    destination: dict        # coords, summary
    weather: list
    transport: dict          # chosen option + alternatives
    stay: dict
    activities: dict         # ranked candidate POIs (the only places the Planner may use)
    itinerary: dict
    costs: dict
    violations: list
    last_violation: Optional[dict]
    next_agent: Optional[str]
    revision_count: int
    replans: list            # [{problem, target}] for the Critic note in the UI
    constraints: Annotated[dict, merge_dicts]  # per-agent knobs, adjusted by fixes and refinements
    selection: Optional[dict]  # the traveller's picks: {"confirmed", "places": {id: must|add|optional|skip}}
    original: Optional[dict]   # transport, stay and places as the traveller confirmed them
    changes: Annotated[list, add_changes]  # what the agents changed after that, and why
    baseline: Optional[dict]   # the plan just before the traveller's last change, to explain what moved
    final: Optional[dict]
    reply: str
    log: Annotated[list, operator.add]


class TripDraft(BaseModel):
    """What the LLM extracts from free text. Everything optional."""
    origin: Optional[str] = Field(None, description="Departure city")
    destination: Optional[str] = Field(None, description="Destination city in India")
    start_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    num_days: Optional[int] = None
    travellers: Optional[int] = None
    budget_amount: Optional[float] = Field(None, description="Total trip budget as a number")
    budget_currency: Optional[str] = Field(None, description="ISO code, e.g. INR, USD")
    interests: Optional[list[str]] = None  # models often send null rather than []
    pace: Optional[Literal["relaxed", "moderate", "packed"]] = None
    preferred_mode: Optional[Literal["flight", "train", "bus"]] = None
    stay_tier: Optional[Literal["budget", "mid", "premium"]] = None
    priority: Optional[Literal["balanced", "stay", "travel", "food", "experiences"]] = Field(
        None, description="What the user explicitly wants to spend more on; null unless they clearly say so")


REQUIRED = ["origin", "destination", "start_date", "end_date", "travellers", "budget_inr", "priority"]
PRIORITIES = ["balanced", "stay", "travel", "food", "experiences"]
FIELD_QUESTIONS = {
    "origin": "Which city are you starting from?",
    "destination": "Where do you want to go?",
    "start_date": "What date do you want to leave? (e.g. 12 Dec 2026)",
    "end_date": "How many days is the trip, or what date do you return?",
    "travellers": "How many people are travelling?",
    "budget_inr": "What's the total budget for the whole group? (e.g. ₹40,000)",
    "priority": "What should get the bigger share of the budget: a nicer stay, faster travel, better food, "
                "more experiences, or keep it balanced?",
}


def missing_fields(req: dict) -> list[str]:
    return [f for f in REQUIRED if not req.get(f)]


def trip_dates(req: dict) -> list[date]:
    start, end = date.fromisoformat(req["start_date"]), date.fromisoformat(req["end_date"])
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def validation_errors(req: dict, today: date | None = None) -> list[str]:
    from .config import MAX_TRIP_DAYS
    today = today or date.today()
    errs = []
    if req.get("start_date") and date.fromisoformat(req["start_date"]) < today:
        errs.append("The start date is in the past.")
    if req.get("start_date") and req.get("end_date"):
        n = (date.fromisoformat(req["end_date"]) - date.fromisoformat(req["start_date"])).days + 1
        if n < 1:
            errs.append("The return date is before the start date.")
        elif n > MAX_TRIP_DAYS:
            errs.append(f"Trips are limited to {MAX_TRIP_DAYS} days.")
    if req.get("origin") and req.get("destination") and req["origin"].lower() == req["destination"].lower():
        errs.append("Origin and destination are the same city.")
    if req.get("travellers") is not None and not 1 <= req["travellers"] <= 20:
        errs.append("Travellers must be between 1 and 20.")
    return errs


def change(area: str, before: str | None, after: str | None, reason: str) -> dict:
    """One entry for "What changed in your plan?"."""
    return {"area": area, "before": before, "after": after, "reason": reason}


def violation_for(state: dict, agent: str) -> dict:
    """The Critic's violation, only if the Critic routed it to this agent. After a Budget Agent
    fix every specialist reruns, and they must not also apply their own fix for the same problem."""
    return (state.get("last_violation") or {}) if state.get("next_agent") == agent else {}
