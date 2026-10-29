"""The travel database and hotel-centred planning: saved places, cached routes, real prices in estimates,
far-place warnings, days grouped by area, and explanations after a hotel change."""
from datetime import date, timedelta

from tripsync import db
from tripsync.agents import planner
from tripsync.agents.activity import activity_node
from tripsync.agents.budget import typical_costs
from tripsync.agents.planner import group_days, schedule
from tripsync.tools import geo
from tripsync.view import nearby

START = date.today() + timedelta(days=40)
REQ = {"origin": "Delhi", "destination": "Jaipur", "start_date": START.isoformat(),
       "end_date": (START + timedelta(days=2)).isoformat(), "travellers": 2, "budget_inr": 30000,
       "interests": [], "priority": "balanced"}


def _place(i: int, lat: float, lon: float, **kw) -> dict:
    return {"id": f"p{i}@{lat},{lon}", "name": f"Place {i}", "kind": "fort", "lat": lat, "lon": lon, "indoor": False,
            "fee": 100, "minutes": 60, "score": 5 - i * 0.1, "source": "OpenStreetMap", **kw}


def test_saved_places_used_when_overpass_is_down():
    db.save_places("Jaipur", [_place(1, 26.92, 75.82), _place(2, 26.95, 75.80)])
    out = activity_node({"request": REQ, "constraints": {}})  # offline: Overpass "fails"
    cands = out["activities"]["candidates"]
    assert "saved" in out["activities"]["source"]
    assert {"p1@26.92,75.82", "p2@26.95,75.8"} <= {c["id"] for c in cands}


def test_routes_are_fetched_once_then_read_from_the_database(monkeypatch):
    calls = []

    def fake(url, params=None, **kw):
        calls.append(url)
        return {"code": "Ok", "durations": [[0, 600], [660, 0]], "distances": [[0, 5000], [5200, 0]]}
    monkeypatch.setattr(geo, "get_json", fake)
    pts = [(26.9, 75.8), (26.95, 75.85)]
    first = geo.travel_table(pts)
    second = geo.travel_table(pts)
    assert len(calls) == 1 and first == second and second[1][0][1] == 5.0 and second[0][1][0] == 11.0


def test_real_hotel_prices_replace_the_static_table():
    opts = [{"id": f"h{i}", "name": f"Hotel {i}", "tier": "mid", "nightly": 2000 + i * 100, "nights": 2, "rooms": 1,
             "source": "LiteAPI", "estimate": False} for i in range(5)]
    db.save_hotels("Jaipur", START, opts)
    stats = db.hotel_price_stats("Jaipur", "mid")
    assert stats["median"] == 2200 and stats["n"] == 5
    assert typical_costs({**REQ, "stay_tier": "mid"})["stay"] == 2200 * 1 * 2


def test_far_places_are_flagged_from_the_hotel():
    hotel = {"id": "h", "name": "Pink City Hotel", "lat": 26.92, "lon": 75.82, "tier": "mid"}
    values = {"request": REQ, "destination": {"lat": 26.91, "lon": 75.79},
              "stay": {"choice": hotel, "options": [hotel]},
              "activities": {"candidates": [_place(1, 26.93, 75.83), _place(2, 27.40, 76.10)], "food_spots": []}}
    out = nearby(values)
    near, far = out["places"]["p1@26.93,75.83"], out["places"]["p2@27.4,76.1"]
    assert out["reference"] == "hotel" and not near["far"] and far["far"]
    assert far["km"] > 25 and far["fare"] > 0 and "google.com/maps/dir" in far["maps_url"]


def test_days_keep_each_area_together():
    home = (26.92, 75.82)
    west = [_place(i, 26.92, 75.70 + i * 0.005) for i in range(3)]
    east = [_place(i + 3, 26.92, 75.94 + i * 0.005) for i in range(3)]
    groups = group_days(home, west + east, [600, 600], [4, 4])
    ids = lambda ps: {p["id"] for p in ps}  # noqa: E731
    assert sorted([ids(west), ids(east)], key=str) == sorted(groups, key=str)


def test_far_place_gets_its_own_day():
    home = (26.92, 75.82)
    far = _place(9, 27.40, 76.10)
    near = [_place(i, 26.92 + i * 0.01, 75.82) for i in range(4)]
    groups = group_days(home, [far] + near, [300, 600, 300], [4, 4, 4])
    assert groups[1] == {far["id"]}


def test_dinner_comes_after_check_in_on_a_late_arrival():
    day = {"date": START.isoformat(), "stops": [], "start_min": 20 * 60 + 17, "meals": {"dinner": None}}
    dinner = schedule(day)[0]
    assert dinner["meal"] == "dinner" and dinner["arrive_min"] >= 20 * 60 + 47


def test_two_opt_untangles_a_crossing_route():
    home = (0.0, 0.0)
    pts = [_place(1, 0.0, 1.0), _place(2, 1.0, 0.0), _place(3, 1.0, 1.0)]  # visiting the far corner second crosses
    out = planner._two_opt(home, [pts[0], pts[1], pts[2]])
    assert planner._tour_km(home, out) < planner._tour_km(home, pts)
