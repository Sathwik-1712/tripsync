from langgraph.types import Command
from datetime import date, timedelta

import pytest

from tripsync.agents.critic import check
from tripsync.agents.planner import planner_node, schedule
from tripsync.graph import build_graph
from tripsync.tools import hours, mcp, stays, transport

START = date.today() + timedelta(days=40)


@pytest.mark.parametrize("spec,weekday,expect", [
    ("Mo-Su 09:00-17:00", 0, ((540, 1020),)),
    ("Tu-Su 10:00-17:00; Mo off", 0, ()),
    ("Tu-Su 10:00-17:00; Mo off", 3, ((600, 1020),)),
    ("Mo-Fr 09:00-13:00,14:00-18:00", 5, ()),
    ("24/7", 6, ((0, 1440),)),
    ("sunrise-sunset", 2, ((360, 1110),)),
    ("Sa-Mo 08:00-12:00", 0, ((480, 720),)),
])
def test_opening_hours_parser(spec, weekday, expect):
    assert hours.parse(spec)[weekday] == expect


def test_unreadable_hours_are_unknown():
    assert hours.parse("Mo-Fr 09:00-17:00; PH off") is None
    assert hours.visit_problem("dawn till dusk", 0, 600, 60) is None
    assert hours.visit_problem("Mo off", 0, 600, 60) == "closed on Mondays"
    assert hours.visit_problem("Mo-Su 09:00-10:00", 0, 590, 60) == "open 09:00–10:00"


def test_schedule_waits_for_opening():
    day = {"date": "2026-12-01", "legs_min": [10, 10],  # a Tuesday
           "stops": [{"name": "A", "minutes": 60, "opening_hours": "Tu 10:30-17:00"},
                     {"name": "B", "minutes": 30}]}
    a, b = schedule(day)
    assert (a["arrive"], a["wait_min"], b["arrive"]) == ("10:30", 80, "11:40")  # day starts 09:00


def _plan():
    g = build_graph()
    cfg = {"configurable": {"thread_id": "hours"}}
    g.invoke({"user_message": f"4 days from Delhi to Jaipur on {START:%d %b %Y}, 2 people, ₹40000, balanced"}, cfg)
    g.invoke(Command(resume={"accept": True}), cfg)  # take the suggested places
    return g.get_state(cfg).values


def test_planner_skips_places_closed_that_day():
    v = _plan()
    for c in v["activities"]["candidates"]:
        c["opening_hours"] = "Mo-Sa 09:00-18:00; Su off"
    out = planner_node(v)
    for d in out["itinerary"]["days"]:
        if date.fromisoformat(d["date"]).weekday() == 6:
            assert d["stops"] == []
    v.update(out)
    assert not any(x["type"] == "closed_place" for x in check(v))


def test_critic_flags_visit_after_closing_and_planner_avoids_it():
    v = _plan()
    target = v["itinerary"]["days"][1]["stops"][-1]
    for c in v["activities"]["candidates"]:
        if c["id"] == target["id"]:
            c["opening_hours"] = "Mo-Su 06:00-08:00"
    for s in v["itinerary"]["days"][1]["stops"]:
        if s["id"] == target["id"]:
            s["opening_hours"] = "Mo-Su 06:00-08:00"
    closed = [x for x in check(v) if x["type"] == "closed_place"]
    assert closed and closed[0]["places"][0]["id"] == target["id"]
    out = planner_node({**v, "last_violation": closed[0], "next_agent": "planner"})
    assert [2, target["id"]] in out["constraints"]["planner"]["avoid"]
    assert target["id"] not in {s["id"] for s in out["itinerary"]["days"][1]["stops"]}


class _Resp:
    def __init__(self, text, ctype="text/event-stream"):
        self.text, self.headers = text, {"content-type": ctype}

    def json(self):
        import json
        return json.loads(self.text)


def test_mcp_reads_sse_reply():
    r = _Resp('event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"ok":1}}\n\n')
    assert mcp._rpc_result(r, 2) == {"ok": 1}
    with pytest.raises(mcp.MCPError):
        mcp._rpc_result(_Resp('{"jsonrpc":"2.0","id":2,"error":{"message":"bad"}}', "application/json"), 2)


def test_kiwi_results_become_one_way_per_person(monkeypatch):
    def it(price, carrier, dep, stops=0, secs=4500, url=None):
        seg = {"carrierName": carrier, "flightNumber": "6E1", "fromName": "Bengaluru", "toName": "Goa"}
        return {"price": price, "bookingUrl": url, "outbound": {
            "from": "BLR", "to": "GOI", "departureTime": dep, "arrivalTime": dep, "stops": stops,
            "durationSeconds": secs, "segments": [seg]}}
    monkeypatch.setattr(transport, "call_tool", lambda *a, **k: {"currency": "INR", "itineraries": [
        it(9000, "IndiGo Airlines", "2026-12-01T07:00:00", url="u"),
        it(9000, "IndiGo Airlines", "2026-12-01T07:00:00"),            # same schedule: dropped
        it(9500, "IndiGo Airlines", "2026-12-01T18:00:00"),            # same airline, other time: kept
        it(12000, "Air India", "2026-12-01T09:00:00", stops=1, secs=18000)]})
    out = transport._kiwi_mcp("Bengaluru", "Goa", START, START + timedelta(days=4))
    assert [(o["label"], o["price_pp"], o["hours"]) for o in out] == [
        ("IndiGo (economy, non-stop)", 4500, 1.2), ("IndiGo (economy, non-stop)", 4750, 1.2),
        ("Air India (economy, 1 stop)", 6000, 5.0)]
    assert out[0]["source"] == "Kiwi.com" and out[0]["booking_url"] == "u"
    assert out[0]["out"]["depart"] == "2026-12-01T07:00:00" and out[0]["out"]["flights"] == ["6E1"]


def test_transport_prefers_flights_that_keep_the_days():
    from tripsync.agents.transport import choose
    late = {"mode": "flight", "total": 18000, "hours": 1.2, "out": {"arrive": "2026-12-01T21:00:00"}}
    good = {"mode": "flight", "total": 19000, "hours": 1.2, "out": {"arrive": "2026-12-01T09:30:00"}}
    assert choose([late, good], 20000, "flight") is good
    assert choose([late, good], 18500, "flight") is late  # only the late one fits the limit


def test_liteapi_rates_become_nightly_per_room(monkeypatch):
    monkeypatch.setenv("LITEAPI_API_KEY", "sand_x")
    monkeypatch.setattr(stays, "get_json", lambda *a, **k: {"data": [
        {"id": "h1", "name": "Sea View Inn", "latitude": 15.5, "longitude": 73.8, "stars": 3}]})
    sent = {}

    def fake_post(url, **kw):
        sent.update(kw["json"])
        return {"data": [{"hotelId": "h1", "roomTypes": [{"offerRetailRate": {"amount": 24000}},
                                                         {"offerRetailRate": {"amount": 30000}}]}]}
    monkeypatch.setattr(stays, "post_json", fake_post)
    out = stays._liteapi("Goa", START, START + timedelta(days=4), 3)
    assert sent["occupancies"] == [{"adults": 2}, {"adults": 1}]
    assert out[0]["nightly"] == 3000 and out[0]["source"] == "LiteAPI"  # 24000 / 4 nights / 2 rooms


def test_live_providers_are_skipped_offline():
    assert transport._kiwi_mcp("Bengaluru", "Goa", START, START + timedelta(days=4)) == []
    assert transport._fast_flights("Bengaluru", "Goa", START, START + timedelta(days=4)) == []


def test_wikivoyage_skips_hospitals_and_consulates(monkeypatch):
    from tripsync.tools import places
    text = """== See ==
{{see | name=Lalbagh | lat=12.95 | long=77.58 | price=₹30 }}
{{listing | name=Bangalore Palace | lat=12.99 | long=77.59 }}
== Eat ==
{{listing | name=MTR | lat=12.95 | long=77.58 }}
== Cope ==
=== Consulates ===
{{listing | name=France | lat=12.97 | long=77.60 }}
=== Hospitals ===
{{listing | name=Manipal Hospital | lat=12.96 | long=77.64 }}
{{see | name=Aster CMI Hospital | lat=13.05 | long=77.59 }}
"""
    monkeypatch.setattr(places, "_wikitext", lambda page: text)
    sights, eats = places.wikivoyage_listings("Testcity", [])
    assert sorted(s["name"] for s in sights) == ["Bangalore Palace", "Lalbagh"]
    assert [e["name"] for e in eats] == ["MTR"]
