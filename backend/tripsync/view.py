"""Turns graph state into what the frontend renders, plus the Markdown export."""
import math
import re
from datetime import date

from .agents.costs import food_per_person_day, food_tier
from .agents.planner import DAY_END, DAY_START, MEAL_MIN, _mode, day_window, local_fare, maps_url, schedule
from .agents.review import FAR_KM, FAR_MIN
from .state import trip_dates
from .tools.geo import city_info, travel_from
from .tools.transport import search_links

AGENT_KEYS = ["budget", "transport", "accommodation", "activity", "planner", "critic"]

THEMES = [({"beach"}, "Beaches and sea air"),
          ({"fort", "palace", "monument", "archaeological_site", "memorial"}, "Forts and history"),
          ({"temple"}, "Temples and old quarters"), ({"museum", "gallery"}, "Museums and art"),
          ({"park", "garden", "nature_reserve", "waterfall", "viewpoint", "zoo"}, "Green spaces and views"),
          ({"marketplace", "mall"}, "Markets and shopping"), ({"cafe", "nightlife"}, "Food and evenings")]


def day_title(day: dict, n_days: int) -> str:
    if day["day"] == 1 and n_days > 1 and len(day["stops"]) <= 1:
        return "Arrive and settle in"
    if day["day"] == n_days and n_days > 1 and len(day["stops"]) <= 1:
        return "Last stops and head home"
    if day.get("indoor_only"):
        return "An indoor day"
    kinds = [s["kind"] for s in day["stops"]]
    if not kinds:
        return "Free day"
    best = max(THEMES, key=lambda t: sum(k in t[0] for k in kinds))
    return best[1] if any(k in best[0] for k in kinds) else "Around town"


def statuses(values: dict, question: dict | None) -> dict:
    if not values.get("itinerary"):
        return {}
    st = {k: "Done" for k in AGENT_KEYS}
    for r in values.get("replans", []):
        if r["target"] in st:
            st[r["target"]] = "Replanned"
    st["critic"] = "Replanned" if values.get("replans") else "Passed"
    if question and question.get("type") == "retry_cap":
        st["critic"] = "Needs you"
    return st


# Place categories for the "choose your places" step, in display order.
GROUPS = [
    ("landmarks", "Tourist attractions and landmarks", {"monument", "memorial", "attraction", "zoo", "aquarium"}),
    ("nature", "Nature, beaches, waterfalls and viewpoints", {"beach", "waterfall", "viewpoint", "nature_reserve"}),
    ("adventure", "Adventure activities", {"theme_park"}),
    ("culture", "Cultural and historical places", {"fort", "palace", "temple", "museum", "gallery",
                                                   "archaeological_site"}),
    ("food", "Food spots and restaurants", {"cafe"}),
    ("shopping", "Shopping and nightlife", {"marketplace", "mall", "nightlife"}),
    ("leisure", "Relaxation and leisure", {"park", "garden"}),
]
ADVENTURE = re.compile(r"trek|raft|paraglid|scuba|div(e|ing)|kayak|zip ?line|safari|surf|parasail|climb|adventure", re.I)


def place_group(p: dict) -> str:
    if ADVENTURE.search(p["name"]):
        return "adventure"
    return next((key for key, _, kinds in GROUPS if p["kind"] in kinds), "landmarks")


def _place(p: dict) -> dict:
    hours = p.get("opening_hours") or p.get("hours_text")
    return {"id": p["id"], "name": p["name"], "kind": p["kind"], "group": place_group(p), "lat": p["lat"],
            "lon": p["lon"], "description": p.get("description"), "minutes": p["minutes"], "fee": p["fee"],
            "fee_known": bool(p.get("fee_known")), "hours": hours, "indoor": p["indoor"], "source": p["source"],
            "score": round(p["score"], 1), "picks": p.get("picks")}


def _food(f: dict) -> dict:
    return {"id": f["id"], "name": f["name"], "kind": "restaurant", "group": "food", "lat": f["lat"], "lon": f["lon"],
            "description": f.get("description"), "minutes": MEAL_MIN, "fee": 0, "fee_known": False,
            "price": f.get("price"), "hours": f.get("hours"), "indoor": True, "source": f["source"], "meal": True,
            "score": 0, "picks": None}


def stay_choices(stay: dict) -> list[dict]:
    """Up to five per tier, best rated first, always including the current pick."""
    out, chosen = [], stay["choice"]
    for tier in ("budget", "mid", "premium"):
        opts = sorted((o for o in stay["options"] if o["tier"] == tier),
                      key=lambda o: (o.get("generic", False), -(o.get("rating") or 0), o["total"]))
        out += opts[:5]
    if chosen["id"] not in {o["id"] for o in out}:
        out.append(chosen)
    return out


def _transport(values: dict) -> dict:
    req, t = values["request"], values["transport"]
    start, end = date.fromisoformat(req["start_date"]), date.fromisoformat(req["end_date"])
    opts = [{**o, "window": day_window(o["mode"], o, start, end)} for o in t["options"]]
    return {"options": opts, "choice_id": t["choice"].get("id"),
            "links": search_links(req["origin"], req["destination"], start, end),
            "flights_live": any(o["mode"] == "flight" and o.get("live") for o in opts)}


def nearby(values: dict, stay_id: str | None = None) -> dict:
    """Road distance, time, suggested ride, fare and directions from the chosen hotel to every place.
    The hotel's own coordinates are the reference; without them, the city centre is used and said so."""
    stays = values["stay"]["options"]
    stay = next((o for o in stays if o["id"] == stay_id), None) or values["stay"]["choice"]
    dest = values.get("destination") or {}
    if stay.get("lat") is not None and stay.get("lon") is not None and not stay.get("generic"):
        origin, reference = (stay["lat"], stay["lon"]), "hotel"
    elif dest.get("lat") is not None:
        origin, reference = (dest["lat"], dest["lon"]), "city centre"
    else:
        return {"stay_id": stay.get("id"), "reference": "none", "source": "none", "places": {}}
    acts, n = values["activities"], values["request"]["travellers"]
    places = list(acts["candidates"]) + [f for f in acts.get("food_spots") or [] if f.get("id")]
    rows, source = travel_from(origin, [(p["lat"], p["lon"]) for p in places])
    out = {}
    for p, (km, minutes) in zip(places, rows):
        km = round(km, 1)
        mode = _mode(km)
        minutes = max(3, round(km / 4.5 * 60)) if mode == "walk" else max(5, round(minutes))
        out[p["id"]] = {"km": km, "minutes": minutes, "mode": mode, "fare": local_fare(mode, km, n),
                        "maps_url": maps_url(origin, (p["lat"], p["lon"]), mode),
                        "far": km > FAR_KM or minutes > FAR_MIN}
    return {"stay_id": stay.get("id"), "reference": reference, "name": stay["name"] if reference == "hotel" else
            values["request"]["destination"], "source": source, "places": out,
            "far_km": FAR_KM, "far_min": FAR_MIN}


def selection_view(values: dict) -> dict:
    """Everything the traveller needs to pick places, a stay and transport, with live budget maths."""
    req, acts = values["request"], values["activities"]
    n, days = req["travellers"], len(trip_dates(req))
    places = [_place(p) for p in acts["candidates"]] + [_food(f) for f in acts.get("food_spots") or [] if f.get("id")]
    stay = values["stay"]["choice"]
    return {
        "request": req, "codes": _codes(req),
        "groups": [{"key": k, "title": title} for k, title, _ in GROUPS],
        "places": places, "places_source": acts.get("source", "none"),
        "stays": stay_choices(values["stay"]), "stay_id": stay["id"],
        "stays_live": any(not o.get("estimate") for o in values["stay"]["options"]),
        "transport": _transport(values),
        "home": {k: (values.get("destination") or {}).get(k) for k in ("lat", "lon")},
        "estimates": {
            # Food at the stay's level (or premium for food lovers), cabs to and from the airport/station,
            # and a typical auto ride per place. Mirrors agents/costs.py.
            "food_by_tier": {tier: food_per_person_day(req["destination"], food_tier(req, tier)) * n * days
                             for tier in ("budget", "mid", "premium")},
            "transfers": 2 * math.ceil(n / 4) * 600, "local_per_place": local_fare("auto", 4, n),
            "travel_per_place_min": 25, "lunch_min": MEAL_MIN, "day_start": DAY_START, "day_end": DAY_END,
        },
        "days": days, "budget": req["budget_inr"], "allocations": values.get("allocations"),
        "nearby": nearby(values),
    }


def _codes(req: dict) -> dict:
    return {k: city_info(req[k]).get("airport") or req[k][:3].upper() for k in ("origin", "destination")}


def build_view(values: dict, question: dict | None) -> dict:
    base = {"statuses": statuses(values, question), "notice": None}
    if question and question.get("type") == "select":
        return {**base, "status": "select", "question": question, "selection": selection_view(values)}
    if question:
        return {**base, "status": "question", "question": question}
    if not values.get("final"):
        return {**base, "status": "empty"}
    days = values["itinerary"]["days"]
    return {
        **base,
        "status": "plan",
        "request": values["request"],
        "codes": _codes(values["request"]),
        "transport": values["transport"]["choice"],
        "transport_options": values["transport"]["options"],
        "transport_links": _transport(values)["links"],
        "stay": values["stay"]["choice"],
        "stay_options": stay_choices(values["stay"]),
        "destination": values["destination"],
        "places_source": values["activities"]["source"],
        "days": [_day_view(d, len(days)) for d in days],
        "transfers": values["itinerary"].get("transfers"),
        "budget_basis": (values.get("constraints", {}).get("budget") or {}).get("basis", []),
        "priority": values["request"].get("priority") or "balanced",
        "home": values["itinerary"]["home"],
        "routing": values["itinerary"]["routing"],
        "costs": values["costs"],
        "allocations": values["allocations"],
        "replans": values.get("replans", []),
        "changes": values.get("changes", []),
        "original": values.get("original"),
        "warnings": values["final"]["warnings"],
        "log": values.get("log", []),
    }


def _day_view(d: dict, n_days: int) -> dict:
    timeline, legs = schedule(d), d.get("legs") or []
    k = 0
    for x in timeline:  # directions to each stop: legs[i] ends at stop i; the last leg returns to the stay
        if x["type"] == "stop":
            x["leg"] = legs[k] if k < len(legs) else None
            k += 1
    return {**d, "title": day_title(d, n_days), "timeline": timeline,
            "stops": [x for x in timeline if x["type"] == "stop"], "return_leg": legs[-1] if legs else None}


def _journey_lines(d: dict) -> list[str]:
    a, dep, out = d.get("arrival"), d.get("departure"), []
    if a:
        when = f"{a['time']}{' (typical, check the schedule)' if a['assumed'] else ''}"
        what = f"flight {a['flight']}" if a.get("flight") else "arrival"
        out.append(f"- {when} {what} reaches {a['place']}; cab to the stay ~{a['transfer']['minutes']} min, "
                   f"~{inr(a['transfer']['fare'])}; ready by {a['ready']}")
    return out + ([] if not dep else [
        f"- {dep['leave_stay']} leave for {dep['place']} (~{dep['transfer']['minutes']} min, "
        f"~{inr(dep['transfer']['fare'])}); "
        f"{'flight ' + dep['flight'] if dep.get('flight') else 'departure'} at {dep['time']}"
        f"{' (typical, check the schedule)' if dep['assumed'] else ''}"])


MODE_WORD = {"walk": "Walk", "auto": "Auto-rickshaw", "cab": "Taxi / app cab"}


def _leg_line(leg: dict) -> str:
    fare = f", ~{inr(leg['fare'])}" if leg["fare"] else ""
    return (f"  - Route: {leg['from']} → {leg['to']} · {leg['km']} km · ~{leg['minutes']} min · "
            f"{MODE_WORD[leg['mode']]}{fare} · [directions]({leg['maps_url']})")


def inr(n: float) -> str:
    s = str(abs(int(round(n))))
    if len(s) > 3:
        head, tail, groups = s[:-3], s[-3:], []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def export_markdown(values: dict) -> str:
    req, costs, alloc = values["request"], values["costs"], values["allocations"]
    t, s = values["transport"]["choice"], values["stay"]["choice"]
    days = values["itinerary"]["days"]
    lines = [f"# {req['destination']} trip", "",
             f"{req['start_date']} to {req['end_date']} · {req['travellers']} traveller(s) · from {req['origin']}", "",
             f"**Getting there:** {t['label']} ({t['mode']}), {inr(t['total'])} round trip (estimated)",
             f"**Stay:** {s['name']} ({s['tier']}), {inr(s['total'])} (estimated)", ""]
    for d in days:
        lines.append(f"## Day {d['day']} · {date.fromisoformat(d['date']):%a %d %b} · {day_title(d, len(days))}")
        items = []
        for x in _day_view(d, len(days))["timeline"]:
            if x.get("leg"):
                items.append(_leg_line(x["leg"]))
            items.append(f"- {x['arrive']} {x['name']}"
                         + (f" ({x['kind'].replace('_', ' ')}, ~{x['minutes']} min)" if x["type"] == "stop" else ""))
        if d.get("legs"):
            items.append(_leg_line(d["legs"][-1]))
        journey = _journey_lines(d)
        lines += (journey[:1] if d.get("arrival") else []) + (items or ["- Free time"]) \
            + (journey[-1:] if d.get("departure") else [])
        lines.append("")
    if values.get("changes"):
        lines += ["## What changed and why", ""]
        lines += [f"- {c['before'] or '—'} → {c['after'] or '—'}: {c['reason']}" for c in values["changes"]] + [""]
    lines.append("## Budget")
    lines += [f"> {b}" for b in (values.get("constraints", {}).get("budget") or {}).get("basis", [])] + [""]
    lines += [f"- {c.title()}: {inr(costs[c])} of {inr(alloc[c])}" for c in ("transport", "stay", "activities", "food")]
    lines += [f"- **Total: {inr(costs['total'])} of {inr(req['budget_inr'])}**", "",
              "_All prices are typical estimates, not booking prices._"]
    return "\n".join(lines)
