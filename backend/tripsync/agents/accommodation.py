"""Step 3b: Accommodation Agent - pick a stay inside the stay limit."""
from datetime import date

from ..state import change, violation_for
from ..tools.geo import geocode
from ..tools.stays import TIERS, stay_options


def accommodation_node(state: dict) -> dict:
    from .review import stay_label
    req, limit = state["request"], state["allocations"]["stay"]
    knobs = dict(state.get("constraints", {}).get("stay") or {"tier": req.get("stay_tier", "mid")})
    prev = (state.get("stay") or {}).get("choice")
    loc = geocode(req["destination"]) or {"lat": None, "lon": None}
    opts = stay_options(req["destination"], loc["lat"], loc["lon"], date.fromisoformat(req["start_date"]),
                        date.fromisoformat(req["end_date"]), req["travellers"])
    v = violation_for(state, "accommodation")
    note, reason = "", None
    if v.get("type") == "stay_over" and not knobs.get("locked"):
        reason = (f"It was ₹{v['deficit']:,} over the stay limit and the whole trip was over budget, "
                  "so a cheaper stay was picked")
        knobs.pop("chosen", None)
        # A cheaper place in the same tier first; move down a tier only if there is none.
        if not any(o["tier"] == knobs["tier"] and o["total"] <= limit for o in opts) and TIERS.index(knobs["tier"]) > 0:
            knobs["tier"] = TIERS[TIERS.index(knobs["tier"]) - 1]
            note = f" (moved down to {knobs['tier']} tier)"
    chosen = next((o for o in opts if o["id"] == knobs.get("chosen")), None)
    if knobs.get("chosen") and not chosen:
        reason = "The stay you picked no longer has rooms for these dates"
        knobs.pop("chosen")
    in_tier = [o for o in opts if o["tier"] == knobs["tier"]]
    within = [o for o in in_tier if o["total"] <= limit]
    choice = chosen or (within[0] if within else min(in_tier or opts, key=lambda o: o["total"]))
    cheapest = min(o["total"] for o in opts)
    changes = ([change("stay", stay_label(prev), stay_label(choice), reason)]
               if reason and prev and prev.get("id") != choice["id"] else [])
    return {
        "stay": {"choice": choice, "options": opts, "limit": limit,
                 "at_cheapest": choice["total"] <= cheapest or bool(knobs.get("locked"))},
        "constraints": {"stay": knobs},
        "changes": changes,
        "log": [f"[Accommodation] {choice['name']} ({choice['tier']}), {choice['nights']} nights × "
                f"{choice['rooms']} room(s) = ₹{choice['total']:,} vs limit ₹{limit:,}{note}"],
    }
