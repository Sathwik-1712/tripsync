from datetime import date, timedelta

from langgraph.types import Command

from tripsync.agents.critic import check
from tripsync.graph import build_graph, pending_interrupt

START = (date.today() + timedelta(days=40)).strftime("%d %b %Y")


def _run(graph, payload, thread, select: dict | None = None):
    """Run until the next question. The "choose your places" step is answered with `select`
    (default: accept the suggestions), since most tests are about what happens after it."""
    cfg = {"configurable": {"thread_id": thread}}
    graph.invoke(payload, cfg)
    while (ask := pending_interrupt(graph, cfg)) and ask["type"] == "select":
        graph.invoke(Command(resume=select or {"accept": True}), cfg)
    return pending_interrupt(graph, cfg), graph.get_state(cfg).values


def test_clarify_then_plan_uses_only_tool_places():
    g = build_graph()
    ask, _ = _run(g, {"user_message": f"4 days from Delhi to Jaipur on {START} for 2 people"}, "a")
    assert ask["type"] == "clarify" and ask["missing"] == ["budget_inr", "priority"]
    ask, v = _run(g, Command(resume="₹30000, balanced"), "a")
    assert ask is None and v["final"]
    allowed = {c["id"] for c in v["activities"]["candidates"]}
    assert all(s["id"] in allowed for d in v["itinerary"]["days"] for s in d["stops"])
    assert v["costs"]["total"] <= v["request"]["budget_inr"]


def test_preference_over_limit_is_routed_to_transport():
    g = build_graph()
    _, v = _run(g, {"user_message": f"4 days from Delhi to Jaipur on {START}, 2 people, ₹30000, by flight, balanced"}, "b")
    assert any("Transport is" in line and "-> transport" in line for line in v["log"])
    assert v["transport"]["choice"]["mode"] != "flight"


def test_retry_cap_asks_user_and_raise_finishes():
    g = build_graph()
    ask, _ = _run(g, {"user_message": f"5 days from Delhi to Goa on {START} for 2 people, budget ₹8000, balanced"}, "c")
    assert ask["type"] == "retry_cap" and ask["raise_by"] > 0
    ask, v = _run(g, Command(resume="raise"), "c")
    assert ask is None and v["final"] and v["request"]["budget_inr"] > 8000


def test_refinement_reruns_only_affected_agent():
    g = build_graph()
    _run(g, {"user_message": f"4 days from Delhi to Jaipur on {START}, 2 people, ₹40000, balanced"}, "d")
    before = g.get_state({"configurable": {"thread_id": "d"}}).values
    _, v = _run(g, {"user_message": "swap day 2 and 3"}, "d")
    assert v["itinerary"]["days"][1]["stops"] == before["itinerary"]["days"][2]["stops"]
    new_lines = v["log"][len(before["log"]):]
    assert not any(line.startswith(("[Transport]", "[Accommodation]", "[Activity]", "[Budget]")) for line in new_lines)


def test_critic_flags_rain_on_outdoor_day():
    stop = {"id": "x", "name": "Fort", "indoor": False, "fee": 0, "minutes": 60}
    state = {
        "costs": {"transport": 0, "stay": 0, "activities": 0, "food": 0, "total": 0, "budget": 100},
        "allocations": {"transport": 10, "stay": 10, "activities": 10, "food": 10, "buffer": 10},
        "transport": {"at_cheapest": False}, "stay": {"at_cheapest": False},
        "activities": {"candidates": [stop]},
        "itinerary": {"days": [{"day": 1, "date": "2026-12-01", "rainy": True, "stops": [stop],
                                "visit_min": 60, "travel_min": 20}]},
    }
    assert [v["type"] for v in check(state)] == ["rain_outdoor"]


def test_plan_under_total_budget_rebalances_instead_of_asking():
    g = build_graph()
    ask, v = _run(g, {"user_message": f"Bangalore to Goa from {START} for 4 days, 3 friends, Rs 45,000, beaches, balanced"}, "e")
    assert ask is None and v["final"] and not v["final"]["warnings"]


def test_preferred_mode_kept_when_total_fits():
    g = build_graph()
    _, v = _run(g, {"user_message": f"3 days from Bengaluru to Mysuru on {START}, 2 people, ₹15000, by train, balanced"}, "f")
    assert v["transport"]["choice"]["mode"] == "train"
    assert v["costs"]["total"] <= v["request"]["budget_inr"] and not v["final"]["warnings"]


def test_specialist_ignores_violation_routed_to_budget():
    from tripsync.agents.transport import transport_node
    state = {"request": {"origin": "Delhi", "destination": "Goa", "start_date": "2026-12-01",
                         "end_date": "2026-12-04", "travellers": 2, "preferred_mode": "flight"},
             "allocations": {"transport": 40000}, "constraints": {"transport": {"preferred_mode": "flight"}},
             "last_violation": {"type": "transport_over", "category": "transport", "deficit": 5000}}
    kept = transport_node({**state, "next_agent": "budget"})
    assert kept["transport"]["choice"]["mode"] == "flight"
    dropped = transport_node({**state, "next_agent": "transport"})
    assert dropped["constraints"]["transport"]["preferred_mode"] is None


def test_priority_is_asked_and_shifts_the_split():
    from tripsync.agents.budget import initial_split
    g = build_graph()
    ask, _ = _run(g, {"user_message": f"4 days from Delhi to Jaipur on {START} for 2 people, ₹40000"}, "p")
    assert ask["type"] == "clarify" and ask["missing"] == ["priority"]
    ask, v = _run(g, Command(resume="stay"), "p")
    assert ask is None and v["request"]["priority"] == "stay" and v["request"]["stay_tier"] == "premium"
    base = {**v["request"], "priority": "balanced", "stay_tier": "mid"}
    even, _, _ = initial_split(base)
    for prio, cat in (("food", "food"), ("experiences", "activities"), ("travel", "transport")):
        boosted, _, basis = initial_split({**base, "priority": prio})
        assert boosted[cat] > even[cat] and "1.5×" in basis[1]


def test_day_plan_follows_arrival_and_departure():
    g = build_graph()
    _, v = _run(g, {"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹40000, balanced"}, "q")
    days = v["itinerary"]["days"]
    first, last = days[0], days[-1]
    assert first["arrival"]["place"] and first["arrival"]["transfer"]["minutes"] >= 10
    assert last["departure"]["leave_stay"] and "dinner" not in last["meals"]
    from tripsync.agents.planner import schedule
    for d in days:
        items = schedule(d)
        stops = [x for x in items if x["type"] == "stop"]
        assert all(x["arrive_min"] >= d["start_min"] for x in stops)
        if stops:
            assert stops[-1]["arrive_min"] + stops[-1]["minutes"] <= d["end_min"] + 15
    assert v["costs"]["transfers"] > 0


def test_requested_flight_and_stay_kept_when_trip_fits():
    g = build_graph()
    _, v = _run(g, {"user_message": f"2 of us flying from Bangalore to Goa on {START} for 4 days, about 60k total, "
                                    "beaches, more experiences"}, "r")
    assert v["transport"]["choice"]["mode"] == "flight"
    assert v["stay"]["choice"]["tier"] != "budget"  # no downgrade while the whole trip fits
    assert v["costs"]["total"] <= 60000 and not v["final"]["warnings"]


def test_faster_travel_funds_the_quickest_mode():
    g = build_graph()
    _, v = _run(g, {"user_message": f"5 days from Chennai to Kochi on {START}, 2 people, ₹40000, faster travel"}, "s")
    fastest = min(v["transport"]["options"], key=lambda o: o["hours"])
    assert v["transport"]["choice"]["mode"] == fastest["mode"] == "flight"
    assert v["costs"]["total"] <= 40000


def test_big_overspend_is_fixed_before_tiny_ones():
    from tripsync.agents.critic import critic_node
    stop = {"id": "x", "name": "Fort", "indoor": False, "fee": 0, "minutes": 60}
    state = {
        "costs": {"transport": 28000, "stay": 7000, "activities": 4300, "food": 6400, "total": 45700, "budget": 40000},
        "allocations": {"transport": 16600, "stay": 9100, "activities": 3900, "food": 6400, "buffer": 4000},
        "constraints": {"transport": {"preferred_mode": "flight"}},
        "transport": {"at_cheapest": False, "choice": {"mode": "flight"}}, "stay": {"at_cheapest": False},
        "activities": {"candidates": [stop]},
        "itinerary": {"days": [{"day": 1, "date": "2026-12-01", "rainy": False, "stops": [stop],
                                "visit_min": 60, "travel_min": 20}]},
    }
    out = critic_node(state)
    assert out["last_violation"]["type"] == "transport_over" and out["next_agent"] == "transport"


def test_selection_skips_and_prioritises_places():
    g = build_graph()
    cfg = {"configurable": {"thread_id": "sel"}}
    g.invoke({"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹60000, balanced"}, cfg)
    ask = pending_interrupt(g, cfg)
    assert ask["type"] == "select" and ask["defaults"]
    cands = g.get_state(cfg).values["activities"]["candidates"]
    must, skip = cands[-1], cands[0]  # the lowest-ranked place is a must, the top one is skipped
    g.invoke(Command(resume={"places": {must["id"]: "must", skip["id"]: "skip", cands[1]["id"]: "add"}}), cfg)
    v = g.get_state(cfg).values
    planned = [s["id"] for d in v["itinerary"]["days"] for s in d["stops"]]
    assert must["id"] in planned and skip["id"] not in planned
    assert set(planned) <= {must["id"], cands[1]["id"]}  # only what was kept
    assert v["original"]["must"] == [must["name"]] and v["original"]["skip"] == [skip["name"]]
    leg = v["itinerary"]["days"][0]["legs"][0]
    assert leg["km"] >= 0 and leg["mode"] in ("walk", "auto", "cab") and "google.com/maps/dir" in leg["maps_url"]


def test_picked_stay_used_and_downgrade_is_explained():
    g = build_graph()
    cfg = {"configurable": {"thread_id": "stay"}}
    g.invoke({"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹14000, balanced"}, cfg)
    stays = g.get_state(cfg).values["stay"]["options"]
    dearest = max(stays, key=lambda o: o["total"])
    g.invoke(Command(resume={"stay": dearest["id"]}), cfg)
    v = g.get_state(cfg).values
    while pending_interrupt(g, cfg):  # the retry cap may ask; keep the plan
        g.invoke(Command(resume="accept"), cfg)
        v = g.get_state(cfg).values
    assert v["original"]["stay"].startswith(dearest["name"])
    if v["stay"]["choice"]["id"] != dearest["id"]:  # replaced: there must be a reason on record
        stay_changes = [c for c in v["changes"] if c["area"] == "stay"]
        assert stay_changes and "over budget" in stay_changes[0]["reason"]
    else:
        assert not [c for c in v["changes"] if c["area"] == "stay"]  # never claims a change that didn't happen


def test_refine_use_stay_locks_the_pick():
    g = build_graph()
    _run(g, {"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹60000, balanced"}, "lock")
    cfg = {"configurable": {"thread_id": "lock"}}
    other = [o for o in g.get_state(cfg).values["stay"]["options"]
             if o["id"] != g.get_state(cfg).values["stay"]["choice"]["id"]][0]
    ask, v = _run(g, {"user_message": f"use stay: {other['id']}"}, "lock")
    assert v["stay"]["choice"]["id"] == other["id"] and v["constraints"]["stay"]["locked"]


def test_edit_places_asks_again_with_previous_picks():
    g = build_graph()
    _run(g, {"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹60000, balanced"}, "edit")
    cfg = {"configurable": {"thread_id": "edit"}}
    g.invoke({"user_message": "edit places"}, cfg)
    ask = pending_interrupt(g, cfg)
    assert ask["type"] == "select" and ask["defaults"] == g.get_state(cfg).values["selection"]["places"]


def test_hotel_change_explains_what_moved():
    g = build_graph()
    _run(g, {"user_message": f"3 days from Delhi to Jaipur on {START}, 2 people, ₹60000, balanced"}, "move")
    cfg = {"configurable": {"thread_id": "move"}}
    v = g.get_state(cfg).values
    other = next(o for o in v["stay"]["options"] if o["id"] != v["stay"]["choice"]["id"] and o.get("lat"))
    _, v = _run(g, {"user_message": f"use stay: {other['id']}"}, "move")
    stay = [c for c in v["changes"] if c["area"] == "stay"]
    assert stay and stay[0]["after"] == other["name"] and "recalculated" in stay[0]["reason"]
    assert v.get("baseline") is None  # used once, then cleared
