"""Step 3a: Transport Agent - pick an intercity option inside the transport limit."""
from datetime import date

from ..state import change, violation_for
from ..tools.transport import transport_options


def _convenience(o: dict) -> float:
    """Journey hours, plus a penalty for schedules that waste a day: landing late on day 1 or
    leaving early on the last day. Options without a known schedule get no penalty."""
    penalty = 0.0
    arrive = ((o.get("out") or {}).get("arrive") or "")[11:13]
    depart = ((o.get("back") or {}).get("depart") or "")[11:13]
    if arrive and int(arrive) >= 18:
        penalty += 4
    if depart and int(depart) < 12:
        penalty += 3
    return o["hours"] + penalty


def choose(opts: list[dict], limit: int, preferred: str | None) -> dict:
    pref = [o for o in opts if o["mode"] == preferred] if preferred else []
    within_pref = [o for o in pref if o["total"] <= limit]
    within = [o for o in opts if o["total"] <= limit]
    if within_pref:
        return min(within_pref, key=_convenience)
    if pref:  # honour the user's preference; the Critic will flag it if it's over the limit
        return min(pref, key=lambda o: (o["total"], _convenience(o)))
    if within:
        return min(within, key=_convenience)
    return min(opts, key=lambda o: o["total"])


def _why(choice: dict, chosen: dict | None, limit: int, preferred: str | None, n: int) -> str:
    if chosen:
        return "You picked this option yourself, so it is kept"
    if choice["total"] <= limit:
        return (f"The most convenient of the options within the ₹{limit:,} limit"
                f"{f' for your preferred {preferred}' if preferred == choice['mode'] else ''}: fewest journey hours, "
                "with a penalty for landing late on day 1 or leaving early on the last day")
    if preferred == choice["mode"]:
        return f"Your preferred {preferred} costs more than the limit; it was kept and the Critic will check the budget"
    return f"None of the {n} options fits the ₹{limit:,} limit, so the cheapest was taken; the Critic checks the rest"


def transport_node(state: dict) -> dict:
    from .review import transport_label
    req, limit = state["request"], state["allocations"]["transport"]
    knobs = dict(state.get("constraints", {}).get("transport") or {"preferred_mode": req.get("preferred_mode")})
    prev = (state.get("transport") or {}).get("choice")
    v = violation_for(state, "transport")
    note, reason = "", None
    if v.get("type") == "transport_over" and not knobs.get("locked"):
        reason = (f"It was ₹{v['deficit']:,} over the transport limit and the whole trip was over budget, "
                  "so a cheaper option was picked")
        knobs.pop("chosen", None)
        if knobs.get("preferred_mode"):
            note = f" (dropped preference for {knobs['preferred_mode']} to fit the limit)"
            knobs["preferred_mode"] = None
    opts = transport_options(req["origin"], req["destination"], date.fromisoformat(req["start_date"]),
                             date.fromisoformat(req["end_date"]), req["travellers"])
    first_run = not state.get("constraints", {}).get("transport")
    if req.get("priority") == "travel" and opts and first_run and not req.get("preferred_mode"):
        # "Faster travel": treat the quickest mode like one the traveller asked for, so it's funded, not skipped.
        knobs["preferred_mode"] = min(opts, key=lambda o: o["hours"])["mode"]
    chosen = next((o for o in opts if o["id"] == knobs.get("chosen")), None)
    if knobs.get("chosen") and not chosen:
        reason = "The option you picked is no longer offered by the flight search"
        knobs.pop("chosen")
        knobs.pop("locked", None)  # the replacement is ours, so budget fixes may change it again
    if not opts:
        choice = {"mode": "unknown", "label": "No route data", "price_pp": 0, "hours": 0, "total": 0, "source": "none",
                  "id": "none", "live": False}
    else:
        choice = chosen or choose(opts, limit, knobs.get("preferred_mode"))
    cheapest = min((o["total"] for o in opts), default=0)
    changes = ([change("transport", transport_label(prev), transport_label(choice), reason)]
               if reason and prev and prev.get("id") != choice["id"] else [])
    return {
        "transport": {"choice": choice, "options": opts, "limit": limit,
                      "at_cheapest": choice["total"] <= cheapest or bool(knobs.get("locked"))},
        "constraints": {"transport": knobs},
        "changes": changes,
        "log": [f"[Transport] {choice['label']} ({choice['mode']}), ₹{choice['total']:,} round trip "
                f"vs limit ₹{limit:,}{note}"],
        "explain": {"why": reason or _why(choice, chosen, limit, knobs.get("preferred_mode"), len(opts)),
                    "inputs": [f"Transport limit ₹{limit:,}", f"{len(opts)} options found "
                               f"({sum(1 for o in opts if o.get('live'))} live)",
                               f"Preferred mode: {knobs.get('preferred_mode') or 'none'}"]},
    }
