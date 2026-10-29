"""Step 9: Refinement chat. Turns a follow-up edit into a targeted change and
reruns only the agents it affects (checkpointed state keeps everything else)."""
import re
from typing import Literal, Optional

from pydantic import BaseModel

from .. import llm
from ..state import trip_dates
from ..tools.stays import TIERS
from .intake import INTEREST_WORDS, parse_budget
from .review import stay_label, transport_label


class RefineAction(BaseModel):
    type: Literal["lighter_day", "swap_days", "stay_down", "stay_up", "prefer_mode", "more_indoor",
                  "add_interest", "set_budget", "edit_places", "unknown"]
    day: Optional[int] = None
    day2: Optional[int] = None
    mode: Optional[Literal["flight", "train", "bus"]] = None
    interest: Optional[str] = None
    amount_inr: Optional[float] = None


def parse_refinement(msg: str) -> dict | None:
    low = msg.lower()
    # Exact picks sent by the plan page's buttons.
    if m := re.match(r"\s*use (stay|transport):\s*(.+)$", msg, re.I | re.S):
        return {"type": f"use_{m.group(1).lower()}", "id": m.group(2).strip()}
    if re.search(r"(edit|change|choose|pick|review)\s+(the\s+|my\s+)?(places|stops|activities|sights)", low):
        return {"type": "edit_places"}
    if m := re.search(r"swap\s+day\s*(\d+)\s*(?:and|with|&|,)\s*(?:day\s*)?(\d+)", low):
        return {"type": "swap_days", "day": int(m.group(1)), "day2": int(m.group(2))}
    if (m := re.search(r"day\s*(\d+)", low)) and re.search(r"light|less|fewer|relax|easier|too (much|many|busy)", low):
        return {"type": "lighter_day", "day": int(m.group(1))}
    if re.search(r"budget", low) and (b := parse_budget(msg)) and b[1] == "INR":
        return {"type": "set_budget", "amount_inr": b[0]}
    if re.search(r"(cheaper|budget|less expensive|affordable).{0,15}(hotel|stay|accommodation|room)|hostel", low):
        return {"type": "stay_down"}
    if re.search(r"(better|nicer|luxur|premium|upgrade).{0,20}(hotel|stay|accommodation|room)", low):
        return {"type": "stay_up"}
    if m := re.search(r"\b(train|flight|bus|fly)\b", low):
        return {"type": "prefer_mode", "mode": "flight" if m.group(1) == "fly" else m.group(1)}
    if re.search(r"indoor|rain", low):
        return {"type": "more_indoor"}
    if re.search(r"\b(add|more|include|want|some)\b", low):
        for interest, pat in INTEREST_WORDS.items():
            if re.search(pat, low):
                return {"type": "add_interest", "interest": interest}
    return None


def plan_summary(state: dict) -> dict:
    """What the traveller sees now: hotel, transport, time on the road, local fares, total, and which day
    each place is on. Compared with the next plan to explain what changed."""
    days = state["itinerary"]["days"]
    return {"hotel": state["stay"]["choice"]["name"], "hotel_id": state["stay"]["choice"].get("id"),
            "transport": state["transport"]["choice"]["label"],
            "road_min": sum(d["travel_min"] for d in days), "local": state["costs"].get("local_travel", 0),
            "total": state["costs"]["total"],
            "day_of": {s["id"]: d["day"] for d in days for s in d["stops"]},
            "names": {s["id"]: s["name"] for d in days for s in d["stops"]}}


def refine_node(state: dict) -> dict:
    msg = state.get("user_message", "")
    action = parse_refinement(msg)
    if action is None:
        a = llm.structured(RefineAction, (
            "Classify this edit request for an existing trip itinerary. Use type 'unknown' if it doesn't match. "
            f"Valid interests: {', '.join(INTEREST_WORDS)}.\nRequest: {msg}"))
        action = a.model_dump() if a else {"type": "unknown"}

    req, cons = dict(state["request"]), state.get("constraints", {})
    act = {**{"indoor_days": [], "day_caps": {}, "max_fee": None}, **(cons.get("activity") or {})}
    out = {"revision_count": 0, "last_violation": None, "violations": [], "replans": [], "changes": [{"reset": True}]}
    original = dict(state.get("original") or {})
    out["baseline"] = plan_summary(state)
    t = action["type"]
    n_days = len(state["itinerary"]["days"])

    if t == "lighter_day" and 1 <= (action.get("day") or 0) <= n_days:
        count = len(state["itinerary"]["days"][action["day"] - 1]["stops"])
        act["day_caps"] = {**act["day_caps"], str(action["day"]): max(1, count - 1)}
        out.update(constraints={"activity": act}, next_agent="planner")
    elif t == "swap_days" and all(1 <= (action.get(k) or 0) <= n_days for k in ("day", "day2")):
        swaps = (cons.get("planner") or {}).get("swaps", []) + [[action["day"], action["day2"]]]
        out.update(constraints={"planner": {**(cons.get("planner") or {}), "swaps": swaps}}, next_agent="planner")
    elif t in ("stay_down", "stay_up"):
        tier = (cons.get("stay") or {}).get("tier", req.get("stay_tier", "mid"))
        i = max(0, min(2, TIERS.index(tier) + (-1 if t == "stay_down" else 1)))
        out.update(constraints={"stay": {"tier": TIERS[i]}}, next_agent="accommodation")
    elif t == "prefer_mode" and action.get("mode"):
        out.update(constraints={"transport": {"preferred_mode": action["mode"]}}, next_agent="transport")
    elif t == "more_indoor":
        act["indoor_days"] = [d.isoformat() for d in trip_dates(req)]
        out.update(constraints={"activity": act}, next_agent="planner")
    elif t == "add_interest" and action.get("interest") in INTEREST_WORDS:
        req["interests"] = sorted(set(req.get("interests", [])) | {action["interest"]})
        out.update(request=req, next_agent="activity")
    elif t == "use_stay" and (opt := next((o for o in state["stay"]["options"] if o["id"] == action["id"]), None)):
        # The traveller's explicit pick: kept even if it costs more than the stay's share (locked).
        out.update(constraints={"stay": {"tier": opt["tier"], "chosen": opt["id"], "locked": True}},
                   original={**original, "stay": stay_label(opt)}, next_agent="accommodation")
    elif t == "use_transport" and (opt := next((o for o in state["transport"]["options"]
                                                if o["id"] == action["id"]), None)):
        out.update(constraints={"transport": {"preferred_mode": opt["mode"], "chosen": opt["id"], "locked": True}},
                   original={**original, "transport": transport_label(opt)}, next_agent="transport")
    elif t == "edit_places" and state.get("selection"):
        out.update(selection={**state["selection"], "confirmed": False}, next_agent="review")
    elif t == "set_budget" and action.get("amount_inr"):
        req["budget_inr"] = round(action["amount_inr"])
        out.update(request=req, budget_action={"type": "split"}, next_agent="budget")
    else:
        out.pop("changes")  # nothing changed, so keep the last plan's change list
        out.pop("baseline")
        out.update(next_agent=None, reply=(
            "I couldn't map that to a change. Try e.g. 'make day 2 lighter', 'swap day 1 and 3', "
            "'cheaper hotel', 'go by train', 'add museums', 'more indoor', or 'set budget to ₹50,000'."))
        return {**out, "log": [f"[Refine] not understood: {msg}"]}
    return {**out, "log": [f"[Refine] {t} -> rerun {out['next_agent']}"]}
