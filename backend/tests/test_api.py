import json
from datetime import date, timedelta

from fastapi.testclient import TestClient

from tripsync.api import app

client = TestClient(app)
START = (date.today() + timedelta(days=40)).strftime("%d %b %Y")


def _events(resp) -> list[tuple[str, dict]]:
    out = []
    for block in resp.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_meta_lists_cities():
    assert "Goa" in client.get("/api/meta").json()["cities"]


def test_question_then_plan_then_export():
    tid = client.post("/api/trips").json()["thread_id"]
    ev = _events(client.post(f"/api/trips/{tid}/messages", json={"text": f"4 days from Delhi to Jaipur on {START}, 2 people"}))
    assert ev[-1][0] == "done" and ev[-1][1]["status"] == "question"
    ev = _events(client.post(f"/api/trips/{tid}/messages", json={"text": "₹30000, keep it balanced"}))
    assert any(e == "progress" for e, _ in ev)
    pick = ev[-1][1]
    assert pick["status"] == "select" and pick["selection"]["places"] and pick["selection"]["stays"]
    first = pick["selection"]["places"][0]
    ev = _events(client.post(f"/api/trips/{tid}/messages", json={"selection": {
        "places": {first["id"]: "must"}, "stay": pick["selection"]["stays"][0]["id"]}}))
    view = ev[-1][1]
    assert view["status"] == "plan" and view["stay"]["id"] == pick["selection"]["stays"][0]["id"]
    stops = [s for d in view["days"] for s in d["stops"]]
    assert [s["name"] for s in stops] == [first["name"]]  # only what was picked
    assert stops[0]["leg"]["maps_url"].startswith("https://www.google.com/maps/dir/")
    assert view["statuses"]["critic"] in ("Passed", "Replanned")
    md = client.get(f"/api/trips/{tid}/export.md")
    assert md.status_code == 200 and md.text.startswith("# Jaipur trip")


def test_health_lists_providers():
    r = client.get("/api/health").json()
    assert r["ok"] and r["offline"] and r["providers"]["flights"][0] == "Kiwi.com MCP"
