"""Step 3d: the traveller reviews before the final plan. After the three agents have searched, the graph
pauses with every place, stay and transport option found. The traveller marks places as must visit /
add / optional / skip and picks a stay and a way to travel; only then does the Planner build the days.

Once confirmed, the selection is kept: Critic loops and refinements pass straight through."""
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from .. import db
from ..state import trip_dates
from .planner import DAY_END, DAY_START, MEAL_MIN, day_caps, day_window

MARKS = ("must", "add", "optional", "skip")
FAR_KM, FAR_MIN = 25, 60  # beyond this from the hotel a place takes a big chunk of the day: warn and plan it apart
TRAVEL_PER_PLACE = 25  # rough minutes between places, before real routes are known


def sightseeing_minutes(req: dict, transport: dict) -> int:
    """Roughly how much sightseeing time the trip has: full days, less arrival and departure, less lunch."""
    dates = trip_dates(req)
    start, end = day_window(transport.get("mode", "train"), transport, dates[0], dates[-1])
    span = lambda a, b: max(0, b - a - (MEAL_MIN if b - a > 180 else 0))  # noqa: E731
    if len(dates) == 1:
        return span(max(DAY_START, start), min(DAY_END, end))
    return (span(max(DAY_START, start), DAY_END) + span(DAY_START, min(DAY_END, end))
            + (len(dates) - 2) * span(DAY_START, DAY_END))


def default_selection(state: dict) -> dict:
    """Pre-tick the best-ranked places that fit both the time available and the pace."""
    req = state["request"]
    cap = sum(day_caps(req, len(trip_dates(req)), {}))
    left, out = sightseeing_minutes(req, state["transport"]["choice"]), {}
    # The AI's suggestions first (in its order), then the rest by score; the same time and pace limits for both.
    cands = sorted(state["activities"]["candidates"], key=lambda c: (c.get("ai_rank") is None, c.get("ai_rank") or 0))
    for c in cands:
        need = c["minutes"] + TRAVEL_PER_PLACE
        if len(out) < cap and need <= left:
            out[c["id"]] = "add"
            left -= need
    return out


def transport_label(o: dict) -> str:
    flights = " + ".join((o.get("out") or {}).get("flights") or [])
    return f"{o['label']}{f' · {flights}' if flights else ''} (₹{o['total']:,})"


def stay_label(o: dict) -> str:
    return f"{o['name']}, {o['tier']} (₹{o['total']:,})"


def _pick(options: list[dict], wanted: str | None) -> dict | None:
    return next((o for o in options if o.get("id") == wanted), None) if wanted else None


def review_node(state: dict, config: RunnableConfig) -> dict:
    sel = state.get("selection") or {}
    if sel.get("confirmed"):
        return {"explain": {"decided": "Your choices are already made, so they are kept as they are",
                            "why": "You choose once; later fixes by the Critic never change your picks"}}
    defaults = sel.get("places") or default_selection(state)
    answer = interrupt({"type": "select", "question": "Choose what goes into your trip, then generate the plan.",
                        "defaults": defaults})
    answer = answer if isinstance(answer, dict) else {}  # a typed reply just accepts the suggestions
    # An empty dict is a real answer (nothing picked), so only a missing "places" means the suggestions.
    places = {k: v for k, v in (answer["places"] if "places" in answer else defaults).items() if v in MARKS}

    out: dict = {"changes": [{"reset": True}], "constraints": {}}
    t_state, s_state = dict(state["transport"]), dict(state["stay"])
    # A stay or transport the traveller switched to here is their explicit choice: locked, like a pick made
    # from the plan page, so budget fixes don't swap it back. Keeping the suggestion leaves it unlocked.
    if (t := _pick(t_state["options"], answer.get("transport"))) and t["id"] != t_state["choice"].get("id"):
        t_state.update(choice=t, at_cheapest=True)
        out["transport"] = t_state
        out["constraints"]["transport"] = {**(state["constraints"].get("transport") or {}),
                                           "chosen": t["id"], "preferred_mode": t["mode"], "locked": True}
    if (s := _pick(s_state["options"], answer.get("stay"))) and s["id"] != s_state["choice"].get("id"):
        s_state.update(choice=s, at_cheapest=True)
        out["stay"] = s_state
        out["constraints"]["stay"] = {**(state["constraints"].get("stay") or {}), "tier": s["tier"], "chosen": s["id"],
                                      "locked": True}

    by_id = {c["id"]: c["name"] for c in state["activities"]["candidates"]}
    by_id |= {f["id"]: f["name"] for f in state["activities"].get("food_spots") or [] if f.get("id")}
    names = {k: by_id[k] for k in places if k in by_id}
    db.record_picks(config["configurable"]["thread_id"], places)
    picked = lambda mark: [names[k] for k, v in places.items() if v == mark and k in names]  # noqa: E731
    transport, stay = out.get("transport", t_state)["choice"], out.get("stay", s_state)["choice"]
    out.update(
        selection={"confirmed": True, "places": places, "names": names},
        original={"transport": transport_label(transport), "stay": stay_label(stay), "must": picked("must"),
                  "add": picked("add"), "optional": picked("optional"), "skip": picked("skip")},
        explain={"decided": f"You kept {len(picked('must')) + len(picked('add')) + len(picked('optional'))} places "
                            f"and skipped {len(picked('skip'))}; {transport['label']}; {stay['name']}",
                 "why": "The plan waits for you here: you choose the places, the stay and the transport, and the "
                        "Planner builds the days only from what you kept",
                 "inputs": [f"{len(state['activities']['candidates'])} places found",
                            f"{len(state['stay']['options'])} stays", f"{len(state['transport']['options'])} ways to travel"]},
        log=[f"[You] confirmed {len(picked('must'))} must-visit, {len(picked('add'))} added, "
             f"{len(picked('optional'))} optional, {len(picked('skip'))} skipped; "
             f"{transport['label']}; {stay['name']}"])
    return out
