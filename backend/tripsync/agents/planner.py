"""Step 4: Planner Agent. Builds the day-wise plan deterministically from the
Activity Agent's candidates only, so it cannot invent places.

Each day is planned against the clock: day 1 starts once you've landed (or arrived by train/bus),
reached the stay and dropped your bags; the last day ends in time to get back to the airport or
station. Stops are added while they fit, with lunch and dinner slots in between."""
import math
from datetime import date, datetime

from ..state import change, trip_dates, violation_for
from ..tools import hours
from ..tools.geo import city_info, haversine_km, travel_matrix, travel_table
from ..tools.weather import is_rainy
from .costs import compute_costs

PACE_CAP = {"relaxed": 3, "moderate": 4, "packed": 5}
DAY_START, DAY_END = 9 * 60, 19 * 60       # sightseeing window on a full day
MAX_WAIT = 90                               # wait up to 90 min for a place to open
LUNCH_FROM, LUNCH_LATEST, MEAL_MIN = 12 * 60 + 30, 15 * 60, 60
DINNER_AT = 19 * 60 + 30
CHECK_IN_MIN = 45                           # drop bags / freshen up after arriving
STATION_BUFFER = {"flight": 120, "train": 45, "bus": 30}  # be there this early before departure


def _pt(p: dict) -> tuple[float, float]:
    return p["lat"], p["lon"]


def _hm(t: int) -> str:
    return f"{t // 60 % 24:02d}:{t % 60:02d}"


def _order(home: tuple, stops: list[dict]) -> list[dict]:
    """Nearest-neighbour ordering starting from the stay."""
    left, out, cur = list(stops), [], home
    while left:
        nxt = min(left, key=lambda s: haversine_km(cur, _pt(s)))
        left.remove(nxt)
        out.append(nxt)
        cur = _pt(nxt)
    return out


def _est_leg(a: tuple, b: tuple) -> float:
    """Rough driving minutes for picking stops (real OSRM times are applied afterwards):
    city traffic for short hops, faster roads for longer ones."""
    km = haversine_km(a, b) * 1.4
    return km / (22 if km < 10 else 38) * 60 + 5


def schedule(day: dict) -> list[dict]:
    """The day's timeline: stops with arrival times (waiting a little if a place hasn't opened yet),
    plus lunch and dinner where the planner put them. Meal items have type "meal"."""
    t, weekday, out = day.get("start_min", DAY_START), date.fromisoformat(day["date"]).weekday(), []
    meals = day.get("meals") or {}
    legs = day.get("legs_min", [])

    def meal(kind: str, at: int):
        spot = meals[kind]
        name = f"{kind.title()} at {spot['name']}" if spot else f"{kind.title()} break"
        out.append({"type": "meal", "meal": kind, "name": name, "spot": spot, "arrive": _hm(at), "arrive_min": at,
                    "minutes": MEAL_MIN, "leg_min": 0})
        return at + MEAL_MIN

    lunch_due = "lunch" in meals
    for i, s in enumerate(day["stops"]):
        if lunch_due and LUNCH_FROM <= t <= LUNCH_LATEST:
            t, lunch_due = meal("lunch", t), False
        leg = legs[i] if i < len(legs) else 0
        t += leg
        week, wait = hours.parse(s.get("opening_hours")), 0
        if week:
            opens = [a for a, _ in week[weekday] if t < a <= t + MAX_WAIT]
            if opens and not any(a <= t < b for a, b in week[weekday]):
                wait = min(opens) - t
        t += wait
        out.append({"type": "stop", **s, "arrive": _hm(t), "arrive_min": t, "leg_min": leg, "wait_min": wait})
        t += s["minutes"]
    if lunch_due and t <= LUNCH_LATEST:
        t = meal("lunch", max(t, LUNCH_FROM))
    if "dinner" in meals:  # never before you've checked in: a late arrival eats 30 min after reaching the stay
        meal("dinner", max(t + (legs[-1] if legs else 0), DINNER_AT,
                           day.get("start_min", DAY_START) + 30 if not day["stops"] else 0))
    return out


def day_caps(req: dict, n_days: int, overrides: dict) -> list[int]:
    base = PACE_CAP.get(req.get("pace", "moderate"), 4) + (1 if req.get("priority") == "experiences" else 0)
    return [min(base, int(overrides.get(str(i), base))) for i in range(1, n_days + 1)]


def _iso_min(iso: str | None, on: date) -> int | None:
    """Minutes after midnight of `on` for an ISO local time, or None if it isn't that day."""
    if not iso:
        return None
    dt = datetime.fromisoformat(iso)
    return dt.hour * 60 + dt.minute + (dt.date() - on).days * 24 * 60


def _transfer(a: tuple, b: tuple, travellers: int, frm: str, to: str) -> dict:
    """Cab between the airport/station and the stay: driving time plus a typical app-cab fare."""
    matrix, _ = travel_matrix([a, b])
    minutes = max(10, round(matrix[0][1]))  # stations/airports aren't at the exact hotel door
    km = round(haversine_km(a, b) * 1.3, 1)
    cabs = math.ceil(travellers / 4)
    return {"from": frm, "to": to, "minutes": minutes, "km": km, "cabs": cabs,
            "fare": int(cabs * max(250, round(150 + 18 * km, -1)))}


def plan_journey(req: dict, choice: dict, home: tuple, stay_name: str) -> dict:
    """When the traveller arrives and must leave, and the transfers either side. Uses the real flight
    schedule when a provider returned one; otherwise typical timings, marked as assumed."""
    dest, start, end = city_info(req["destination"]), date.fromisoformat(req["start_date"]), \
        date.fromisoformat(req["end_date"])
    mode, out_leg, back_leg = choice.get("mode", "train"), choice.get("out"), choice.get("back")
    if mode == "flight" and dest.get("airport_lat"):
        point = (dest["airport_lat"], dest["airport_lon"])
        name = (out_leg or {}).get("to_name") or f"{req['destination']} airport"
        place = f"{name} ({dest['airport']})" if dest.get("airport") and dest["airport"] not in name else name
    else:
        point = (dest["lat"], dest["lon"]) if dest.get("lat") else home
        place = f"{req['destination']} {'bus stand' if mode == 'bus' else 'railway station'}"
    t_in = _transfer(point, home, req["travellers"], place, stay_name)
    t_out = {**t_in, "from": stay_name, "to": place}

    hrs = choice.get("hours") or 0
    arrive = _iso_min((out_leg or {}).get("arrive"), start)
    depart = _iso_min((back_leg or {}).get("depart"), end)
    arrive_known, depart_known = arrive is not None, depart is not None
    if not arrive_known:  # typical timings: short trips leave early morning, long ones overnight
        arrive = (11 * 60 if mode == "flight" else 6 * 60 + 30 + round(hrs * 60) if hrs <= 10 else 8 * 60)
    if not depart_known:
        depart = 18 * 60 if mode == "flight" else 17 * 60
    ready = arrive + t_in["minutes"] + CHECK_IN_MIN
    leave = depart - STATION_BUFFER.get(mode, 45) - t_out["minutes"]
    leg_label = lambda leg: " + ".join(leg.get("flights") or []) if leg else None  # noqa: E731
    return {
        "mode": mode, "transfers": {"in": t_in, "out": t_out},
        "arrival": {"time": _hm(arrive), "assumed": not arrive_known, "place": place, "ready": _hm(ready),
                    "flight": leg_label(out_leg), "depart_time": (out_leg or {}).get("depart", "")[11:16] or None,
                    "depart_from": (out_leg or {}).get("from_name"), "transfer": t_in},
        "departure": {"time": _hm(depart), "assumed": not depart_known, "place": place, "leave_stay": _hm(leave),
                      "flight": leg_label(back_leg), "arrive_time": (back_leg or {}).get("arrive", "")[11:16] or None,
                      "arrive_at": (back_leg or {}).get("to_name"), "transfer": t_out},
        "start_min": ready, "end_min": leave,
    }


def day_window(mode: str, option: dict, start: date, end: date) -> tuple[int, int]:
    """Rough sightseeing window on the first and last day for a transport option, without network calls
    (about 30 min of transfer each way). plan_journey() works out the exact one once a stay is chosen."""
    arrive = _iso_min((option.get("out") or {}).get("arrive"), start)
    depart = _iso_min((option.get("back") or {}).get("depart"), end)
    hrs = option.get("hours") or 0
    if arrive is None:
        arrive = 11 * 60 if mode == "flight" else 6 * 60 + 30 + round(hrs * 60) if hrs <= 10 else 8 * 60
    if depart is None:
        depart = 18 * 60 if mode == "flight" else 17 * 60
    return arrive + 30 + CHECK_IN_MIN, depart - STATION_BUFFER.get(mode, 45) - 30


WALK_KM, AUTO_KM = 1.0, 7.0  # walk short hops, take an auto-rickshaw across town, a cab for longer rides


def _mode(km: float) -> str:
    return "walk" if km < WALK_KM else "auto" if km < AUTO_KM else "cab"


def local_fare(mode: str, km: float, travellers: int) -> int:
    """Typical app fares: autos seat 3, cabs 4. Estimates, not quotes."""
    if mode == "walk":
        return 0
    if mode == "auto":
        return math.ceil(travellers / 3) * int(max(40, round(30 + 15 * km, -1)))
    return math.ceil(travellers / 4) * int(max(200, round(100 + 18 * km, -1)))


def maps_url(a: tuple, b: tuple, mode: str) -> str:
    return (f"https://www.google.com/maps/dir/?api=1&origin={a[0]:.5f},{a[1]:.5f}"
            f"&destination={b[0]:.5f},{b[1]:.5f}&travelmode={'walking' if mode == 'walk' else 'driving'}")


def route_legs(table: tuple, pts: list[tuple], names: list[str], n: int, travellers: int) -> list[dict]:
    """Directions for stay -> stop 1 -> ... -> stop n -> stay. `table` is travel_table() over `pts`,
    whose index 0 is the stay; only the first n stops are used."""
    if n == 0:
        return []
    minutes, km, source = table
    hops = [(k, k + 1) for k in range(n)] + [(n, 0)]
    legs = []
    for a, b in hops:
        d = round(km[a][b], 1)
        mode = _mode(d)
        legs.append({"from": names[a], "to": names[b], "km": d, "mode": mode,
                     "minutes": max(3, round(d / 4.5 * 60)) if mode == "walk" else max(5, round(minutes[a][b])),
                     "fare": local_fare(mode, d, travellers), "maps_url": maps_url(pts[a], pts[b], mode),
                     "source": source})
    return legs


def _nearest_spot(spots: list[dict], near: tuple, used: set, marks: dict | None = None) -> dict | None:
    """Closest restaurant to `near`; ones the traveller picked win if they are within 15 km."""
    marks = marks or {}
    free = [s for s in spots if s["name"] not in used and marks.get(s.get("id")) != "skip"]
    picked = [s for s in free if marks.get(s.get("id")) in ("must", "add", "optional")
              and haversine_km(near, _pt(s)) <= 15]
    free = [s for s in free if haversine_km(near, _pt(s)) <= 8]
    if not (picked or free):
        return None
    best = min(picked or free, key=lambda s: haversine_km(near, _pt(s)))
    used.add(best["name"])
    return {k: best[k] for k in ("name", "lat", "lon", "price", "description", "source") if k in best} | {
        "maps_url": f"https://www.google.com/maps/search/?api=1&query={best['lat']:.5f},{best['lon']:.5f}"}


FAR_KM = 25  # matches agents/review.py; a place this far from the hotel gets its own day when there is one


def _tour_km(home: tuple, stops: list[dict]) -> float:
    pts = [home] + [_pt(s) for s in stops] + [home]
    return sum(haversine_km(a, b) for a, b in zip(pts, pts[1:]))


def _two_opt(home: tuple, stops: list[dict]) -> list[dict]:
    """Untangle the day's loop (hotel -> stops -> hotel) by reversing segments while that shortens it."""
    best, improved = list(stops), True
    while improved and len(best) > 2:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 2, len(best) + 1):
                cand = best[:i] + best[i:j][::-1] + best[j:]
                if _tour_km(home, cand) < _tour_km(home, best) - 0.05:
                    best, improved = cand, True
    return best


def group_days(home: tuple, cands: list[dict], windows: list[int], caps: list[int]) -> list[set]:
    """Which places go on which day, so each day stays in one part of town.

    Keeps the best-ranked places that roughly fit the whole trip, gives far places (plus anything near them)
    a full day of their own where one exists, then sweeps the rest by direction from the hotel and fills the
    days in that order, so neighbours share a day."""
    total, picked = sum(windows), []
    tier = {"must": 0, "add": 1, None: 1, "optional": 2}
    # Must-visit first and optional last; among equals, nearer places win (each 4 km costs a ranking point).
    cands = sorted(cands, key=lambda c: (tier.get(c.get("mark"), 1),
                                         -(c["score"] - SELECT_BOOST.get(c.get("mark"), 0))
                                         + haversine_km(home, _pt(c)) / 4))
    for c in cands:
        far = haversine_km(home, _pt(c)) * 1.4 > FAR_KM
        need = c["minutes"] + (2 * _est_leg(home, _pt(c)) if far else 25)
        if need <= total and len(picked) < sum(caps):
            picked.append(c)
            total -= need
    groups: list[set] = [set() for _ in windows]
    left = {i: w for i, w in enumerate(windows)}
    full_days = [i for i in range(len(windows)) if 0 < i < len(windows) - 1] or \
        [i for i, w in enumerate(windows) if w >= 420]
    rest = []
    for c in picked:
        if haversine_km(home, _pt(c)) * 1.4 > FAR_KM and full_days:
            day = full_days.pop(0)
            near = [o for o in picked if o is not c and haversine_km(_pt(c), _pt(o)) < 8]
            for o in [c] + near[:caps[day] - 1]:
                groups[day].add(o["id"])
            left[day] = 0
    rest = [c for c in picked if not any(c["id"] in g for g in groups)]
    if not rest:
        return groups
    ang = {c["id"]: math.atan2(c["lat"] - home[0], c["lon"] - home[1]) for c in rest}
    rest.sort(key=lambda c: ang[c["id"]])
    # Start the sweep after the widest empty wedge, so one area isn't split across the first and last day.
    gaps = [(ang[rest[(k + 1) % len(rest)]["id"]] - ang[rest[k]["id"]]) % (2 * math.pi) for k in range(len(rest))]
    k = max(range(len(rest)), key=lambda k: gaps[k])
    rest = rest[k + 1:] + rest[:k + 1]
    order = [i for i in range(len(windows)) if left[i] > 0]
    if not order:
        return groups
    # Each day gets its share of the work, in proportion to its free time (arrival days are shorter).
    work = sum(c["minutes"] + 25 for c in rest)
    room = sum(left[i] for i in order) or 1
    target = {i: work * left[i] / room for i in order}
    day_i, done = 0, 0.0
    for c in rest:
        need = c["minutes"] + 25
        while day_i < len(order) - 1 and (done + need / 2 > target[order[day_i]]
                                          or len(groups[order[day_i]]) >= caps[order[day_i]]):
            day_i, done = day_i + 1, 0.0
        groups[order[day_i]].add(c["id"])
        done += need
    return groups


SELECT_BOOST = {"must": 50, "add": 0, "optional": -20}  # must-visit places are scheduled first, optional last


def selected_candidates(cands: list[dict], marks: dict) -> list[dict]:
    """The places the traveller kept, ranked by their marks. With no marks at all, every place is fair game."""
    chosen = {k for k, v in marks.items() if v in SELECT_BOOST}
    keep = [c for c in cands if marks.get(c["id"]) != "skip" and (not chosen or c["id"] in chosen)]
    ranked = [{**c, "mark": marks.get(c["id"]), "score": c["score"] + SELECT_BOOST.get(marks.get(c["id"]), 0)}
              for c in keep]
    return sorted(ranked, key=lambda c: -c["score"])


def planner_node(state: dict) -> dict:
    req = state["request"]
    dates = trip_dates(req)
    act_knobs = state.get("constraints", {}).get("activity") or {}
    knobs = dict(state.get("constraints", {}).get("planner") or {})
    swaps = knobs.get("swaps", [])
    avoid = [list(x) for x in knobs.get("avoid", [])]  # [day, place id] pairs the Critic found closed
    v, changes = violation_for(state, "planner"), []
    if v.get("type") == "closed_place":
        avoid += [[p["day"], p["id"]] for p in v["places"] if [p["day"], p["id"]] not in avoid]
        changes += [change("schedule", f"{p['name']} on day {p['day']}", "Moved to another day if one fits",
                           f"It isn't open at the planned time ({p['why']})") for p in v["places"]]
    avoid_set = {(d, pid) for d, pid in avoid}
    marks = (state.get("selection") or {}).get("places") or {}
    cands = selected_candidates(state["activities"]["candidates"], marks)
    food_spots = state["activities"].get("food_spots") or []
    stay, dest = state["stay"]["choice"], state["destination"]
    home = (stay["lat"], stay["lon"]) if stay.get("lat") else (dest["lat"], dest["lon"])
    indoor_days = set(act_knobs.get("indoor_days", []))
    weather = {w["date"]: w for w in state.get("weather", [])}
    journey = plan_journey(req, state["transport"]["choice"], home, stay["name"])
    n_days = len(dates)

    caps = day_caps(req, n_days, act_knobs.get("day_caps", {}))
    windows = []
    for i in range(1, n_days + 1):
        start = journey["start_min"] if i == 1 else DAY_START
        end = journey["end_min"] if i == n_days else DAY_END
        lunch = MEAL_MIN if start <= LUNCH_LATEST - MEAL_MIN and end >= LUNCH_FROM + MEAL_MIN else 0
        windows.append(max(0, end - start - lunch))
    groups = group_days(home, cands, windows, caps)

    used, used_food, days, routing = set(), set(), [], "n/a"
    for i, (d, cap) in enumerate(zip(dates, caps), 1):
        start = journey["start_min"] if i == 1 else DAY_START
        end = journey["end_min"] if i == n_days else DAY_END
        indoor_only = d.isoformat() in indoor_days
        has_lunch = start <= LUNCH_LATEST - MEAL_MIN and end >= LUNCH_FROM + MEAL_MIN
        avail = end - start - (MEAL_MIN if has_lunch else 0)
        mine = groups[i - 1]
        pool = [c for c in cands if c["id"] not in used and (c["indoor"] or not indoor_only)
                and (i, c["id"]) not in avoid_set and not hours.closed_on(c.get("opening_hours"), d.weekday())]
        stops: list[dict] = []
        est = 0.0
        while pool and len(stops) < cap:
            last = _pt(stops[-1]) if stops else home
            # This day's area first (best-ranked to start, then the closest), then other places near the
            # last stop to fill spare time. If the best one doesn't fit the time left, try the next.
            def rank(c: dict) -> float:
                away = 0 if c["id"] in mine else 15
                return away + (-min(c["score"], 12) if not stops else
                               haversine_km(last, _pt(c)) - min(c["score"], 12) * 0.5)
            ranked = sorted(pool, key=rank)
            fits = [c for c in ranked
                    if est + _est_leg(last, _pt(c)) + c["minutes"] + _est_leg(_pt(c), home) <= avail]
            if not fits:
                break
            nxt = fits[0]
            stops.append(nxt)
            pool.remove(nxt)
            est += _est_leg(last, _pt(nxt)) + nxt["minutes"]
        stops = _two_opt(home, _order(home, stops))
        # Real travel times; drop the last stop until the day fits its window.
        pts, names = [home] + [_pt(s) for s in stops], [stay["name"]] + [s["name"] for s in stops]
        table = travel_table(pts) if stops else ([[0]], [[0]], routing)
        routing = table[2] if stops else routing
        day = {"day": i, "date": d.isoformat(), "indoor_only": indoor_only, "stops": stops,
               "weather": weather.get(d.isoformat()), "start_min": start, "end_min": end}
        while True:
            day["legs"] = route_legs(table, pts, names, len(day["stops"]), req["travellers"])
            day["legs_min"] = [leg["minutes"] for leg in day["legs"]]
            items = schedule(day)
            last_stop = [x for x in items if x["type"] == "stop"][-1:] or None
            if not last_stop or last_stop[0]["arrive_min"] + last_stop[0]["minutes"] <= end + 15:
                break
            day["stops"] = day["stops"][:-1]
        used |= {s["id"] for s in day["stops"]}
        mid = _pt(day["stops"][len(day["stops"]) // 2]) if day["stops"] else home
        day["meals"] = {}
        if has_lunch:
            day["meals"]["lunch"] = _nearest_spot(food_spots, mid, used_food, marks)
        if end >= DAY_END:
            day["meals"]["dinner"] = _nearest_spot(food_spots, home, used_food, marks)
        if i == 1:
            day["arrival"] = journey["arrival"]
        if i == n_days:
            day["departure"] = journey["departure"]
        days.append(day)

    for a, b in swaps:
        if 1 <= a <= len(days) and 1 <= b <= len(days):
            days[a - 1]["stops"], days[b - 1]["stops"] = days[b - 1]["stops"], days[a - 1]["stops"]
            for x in (days[a - 1], days[b - 1]):
                pts = [home] + [_pt(s) for s in x["stops"]]
                names = [stay["name"]] + [s["name"] for s in x["stops"]]
                table = travel_table(pts) if x["stops"] else ([[0]], [[0]], None)
                x["legs"] = route_legs(table, pts, names, len(x["stops"]), req["travellers"])
                x["legs_min"] = [leg["minutes"] for leg in x["legs"]]

    for day in days:
        day["travel_min"] = sum(day["legs_min"])
        day["visit_min"] = sum(s["minutes"] for s in day["stops"])
        day["rainy"] = bool(day["weather"] and is_rainy(day["weather"]))

    itinerary = {"days": days, "home": {"name": stay["name"], "lat": home[0], "lon": home[1]}, "routing": routing,
                 "transfers": journey["transfers"]}
    costs = compute_costs(req, state["transport"], state["stay"], itinerary)
    n_stops = sum(len(d["stops"]) for d in days)
    a = journey["arrival"]
    return {"itinerary": itinerary, "costs": costs, "constraints": {"planner": {**knobs, "avoid": avoid}},
            "changes": changes,
            "log": [f"[Planner] {len(days)} days, {n_stops} stops; arrive {a['time']}"
                    f"{' (assumed)' if a['assumed'] else ''}, ready by {a['ready']}; travel times via {routing}; "
                    f"total ₹{costs['total']:,} of ₹{costs['budget']:,}"]}
