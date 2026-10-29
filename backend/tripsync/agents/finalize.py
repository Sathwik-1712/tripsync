"""Step 8: Final itinerary text (the UI renders map and tables from state)."""
from langchain_core.runnables import RunnableConfig

from .. import db, llm
from ..state import change
from .critic import describe

MARK_LABEL = {"must": "Must visit", "add": "Added", "optional": "Optional"}


def dropped_places(state: dict) -> list[dict]:
    """Places the traveller kept that aren't in the final days, each with the real reason."""
    sel = state.get("selection") or {}
    marks, names = sel.get("places") or {}, sel.get("names") or {}
    planned = {s["id"] for d in state["itinerary"]["days"] for s in d["stops"]}
    cands = {c["id"]: c for c in state["activities"]["candidates"]}
    knobs = state.get("constraints", {})
    max_fee = (knobs.get("activity") or {}).get("max_fee")
    closed = {pid for _, pid in (knobs.get("planner") or {}).get("avoid", [])}
    out = []
    for pid, mark in marks.items():
        if mark not in MARK_LABEL or pid.startswith("eat:") or pid in planned or pid not in names:
            continue
        if pid not in cands:
            why = (f"Entry fees were capped at ₹{max_fee} per person to fit the budget" if max_fee is not None
                   else "It was no longer in the place search results")
        elif pid in closed:
            why = "It isn't open at any time we could fit it in"
        elif mark == "optional":
            why = "Optional, and the days were already full"
        else:
            why = "It didn't fit in the time available at your pace"
        out.append(change("places", f"{names[pid]} ({MARK_LABEL[mark].lower()})", "Not in the itinerary", why))
    return out


def _fmt_day(d: dict) -> str:
    w = d.get("weather")
    wx = f" | {w['tmin']:.0f}–{w['tmax']:.0f}°C, {w['precip_mm']:.0f} mm rain" if w else ""
    stops = " → ".join(s["name"] for s in d["stops"]) or "Free / rest day"
    return f"Day {d['day']} ({d['date']}){wx}\n   {stops}  ({d['travel_min']} min travelling)"


def _hm(minutes: int) -> str:
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


def compare_with_baseline(state: dict) -> list[dict]:
    """After the traveller changes something, say what moved as a result and why. Only real differences."""
    from .refine import plan_summary
    old = state.get("baseline")
    if not old:
        return []
    new, out = plan_summary(state), []
    hotel_changed = old["hotel_id"] != new["hotel_id"]
    if hotel_changed:
        out.append(change("stay", old["hotel"], new["hotel"],
                          "You changed the hotel, so every distance, route and day was recalculated from it"))
    if old["transport"] != new["transport"]:
        out.append(change("transport", old["transport"], new["transport"],
                          "You changed how you travel, so arrival and departure times were recalculated"))
    why = "Routes were recalculated from the new hotel" if hotel_changed else "The days were rebuilt after your change"
    if abs(new["road_min"] - old["road_min"]) >= 10 or abs(new["local"] - old["local"]) >= 100:
        out.append(change("schedule", f"{_hm(old['road_min'])} on the road, local rides ₹{old['local']:,}",
                          f"{_hm(new['road_min'])} on the road, local rides ₹{new['local']:,}", why))
    old_days, new_days = old["day_of"], new["day_of"]
    moved = [pid for pid in new_days if pid in old_days and old_days[pid] != new_days[pid]]
    for pid in moved[:6]:
        out.append(change("schedule", f"{new['names'][pid]} on day {old_days[pid]}", f"Day {new_days[pid]}",
                          "Grouped with places near it so the day stays in one area"
                          if hotel_changed else "Reshuffled to fit the new plan"))
    if len(moved) > 6:
        out.append(change("schedule", None, f"{len(moved) - 6} more places moved to other days", why))
    marks = (state.get("selection") or {}).get("places") or {}
    for pid in [p for p in old_days if p not in new_days][:6]:
        if marks.get(pid) in MARK_LABEL:
            continue  # listed by dropped_places with its own reason
        out.append(change("places", f"{old['names'][pid]} (day {old_days[pid]})", "Not in the itinerary",
                          "You skipped it" if marks.get(pid) == "skip" else
                          "It no longer fits the time available after this change"))
    for pid in [p for p in new_days if p not in old_days][:6]:
        out.append(change("places", None, f"{new['names'][pid]} added on day {new_days[pid]}",
                          "Time freed up after this change"))
    if abs(new["total"] - old["total"]) >= 100:
        out.append(change("budget", f"Total ₹{old['total']:,}", f"₹{new['total']:,}",
                          "The cost of the changes above"))
    return out


def finalize_node(state: dict, config: RunnableConfig) -> dict:
    req, costs, alloc = state["request"], state["costs"], state["allocations"]
    t, s = state["transport"]["choice"], state["stay"]["choice"]
    warnings = [describe(v) for v in state.get("violations", [])]
    if not state["activities"]["candidates"]:
        warnings.append(f"No sightseeing places found for {req['destination']} right now, so the days are left free")
    lines = [
        f"Trip: {req['origin']} → {req['destination']}, {req['start_date']} to {req['end_date']}, "
        f"{req['travellers']} traveller(s), budget ₹{req['budget_inr']:,}",
        f"Getting there: {t['label']} ({t['mode']}), ₹{t['total']:,} round trip [{t['source']}]",
        f"Stay: {s['name']} ({s['tier']}), ₹{s['total']:,} [{s['source']}]",
        "",
        *[_fmt_day(d) for d in state["itinerary"]["days"]],
        "",
        "Costs vs limits: " + ", ".join(f"{c} ₹{costs[c]:,}/₹{alloc[c]:,}" for c in ("transport", "stay", "activities", "food")),
        f"Total ₹{costs['total']:,} of ₹{costs['budget']:,} (buffer ₹{alloc['buffer']:,}). All prices are estimates.",
    ]
    if warnings:
        lines.append("Unresolved: " + "; ".join(warnings))
    intro = llm.text(
        "Write a two-sentence friendly overview of this trip. Mention only places listed; do not add any.\n"
        + "\n".join(lines))
    text = ((intro.strip() + "\n\n") if intro else "") + "\n".join(lines)
    changes = compare_with_baseline(state) + dropped_places(state)
    db.save_trip(config["configurable"]["thread_id"], {**state, "changes": (state.get("changes") or []) + changes})
    return {"final": {"warnings": warnings, "text": text}, "reply": text, "next_agent": None,
            "changes": changes, "baseline": None,
            "log": ["[Final] itinerary ready" + (f" with {len(warnings)} warning(s)" if warnings else "")]}
