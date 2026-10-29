"""Evaluation over a fixed set of test trips.

    python3.12 eval.py             # live data (free APIs, plus any keys in .env)
    python3.12 eval.py --offline   # no network: bundled data only, deterministic

Prints one row per trip and a summary, and writes everything to .cache/eval.json.
Clarifying questions are answered from the trip's `answers`; a retry-cap question is answered "raise"."""
import json
import sys
import time
from datetime import date, timedelta

if "--offline" in sys.argv:
    import os
    os.environ["TRIPSYNC_OFFLINE"] = "1"

from langgraph.types import Command  # noqa: E402

from tripsync.agents.critic import check  # noqa: E402
from tripsync.config import CACHE_DIR  # noqa: E402
from tripsync.graph import build_graph, pending_interrupt  # noqa: E402


def _d(days: int) -> str:
    return (date.today() + timedelta(days=days)).strftime("%d %b %Y")


TRIPS = [
    ("weekend, comfortable", f"3 days from Delhi to Jaipur on {_d(30)} for 2 people, budget ₹25000, nicer stay", []),
    ("beach group trip", f"Bangalore to Goa from {_d(35)} for 4 days, 3 friends, Rs 45,000, beaches, more experiences", []),
    ("history, flight wanted", f"5 days from Mumbai to Delhi on {_d(40)}, 2 people, ₹60000, history, by flight, balanced", []),
    ("solo budget", f"4 days from Pune to Goa on {_d(45)}, solo, ₹12000, balanced", []),
    ("family of four", f"5 days Chennai to Bengaluru on {_d(50)} for 4 people, budget 50k, museums and parks, more activities", []),
    ("long trip", f"7 days from Delhi to Varanasi on {_d(55)}, 2 people, ₹40000, culture, balanced", []),
    ("hill station", f"4 days from Delhi to Shimla on {_d(60)}, 2 people, ₹30000, nature, relaxed pace, balanced", []),
    ("packed city break", f"3 days from Hyderabad to Mumbai on {_d(25)} for 2, ₹35000, packed, shopping, balanced", []),
    ("missing budget", f"4 days from Kolkata to Darjeeling on {_d(65)} for 2 people", ["₹30000, better food"]),
    ("missing dates", "Trip from Delhi to Agra for 2 people, budget ₹15000, 2 days, balanced", [_d(20)]),
    ("too tight -> ask user", f"5 days from Delhi to Goa on {_d(40)} for 2 people, budget ₹8000, balanced", []),
    ("premium couple", f"4 days from Mumbai to Udaipur on {_d(70)}, 2 people, ₹120000, luxury, palaces, nicer stay", []),
    ("train lover", f"3 days from Bengaluru to Mysuru on {_d(28)}, 2 people, ₹15000, by train, balanced", []),
    ("food and nightlife", f"4 days from Delhi to Mumbai on {_d(33)}, 3 people, ₹70000, food, nightlife, splurge on food", []),
    ("monsoon-ish south", f"5 days from Chennai to Kochi on {_d(48)}, 2 people, ₹40000, nature, beach, faster travel", []),
    ("big group", f"3 days from Pune to Mumbai on {_d(22)} for 6 people, ₹60000, balanced", []),
]


def run_trip(graph, name: str, message: str, answers: list[str]) -> dict:
    cfg = {"configurable": {"thread_id": f"eval-{name}"}}
    t0, asked, payload = time.perf_counter(), [], {"user_message": message}
    answers = list(answers)
    for _ in range(8):  # each loop resumes after one question
        graph.invoke(payload, cfg)
        q = pending_interrupt(graph, cfg)
        if not q:
            break
        if q["type"] == "select":  # accept the suggested places, stay and transport
            payload = Command(resume={"accept": True})
            continue
        asked.append(q["type"])
        if q["type"] == "clarify" and not answers:
            break  # the parser missed something the trip did say
        payload = Command(resume=answers.pop(0) if q["type"] == "clarify" else "raise")
    v = graph.get_state(cfg).values
    secs = round(time.perf_counter() - t0, 1)
    if not v.get("final"):
        return {"trip": name, "finished": False, "asked": asked, "seconds": secs,
                "error": f"stuck on {asked[-1]}: {q['question']}" if asked else "did not finish"}
    allowed = {c["id"] for c in v["activities"]["candidates"]}
    stops = [s for d in v["itinerary"]["days"] for s in d["stops"]]
    left = {x["type"] for x in check(v)}
    return {
        "trip": name, "finished": True, "asked": asked, "seconds": secs,
        "rounds": len(v.get("replans", [])), "budget": v["costs"]["budget"], "total": v["costs"]["total"],
        "within_budget": v["costs"]["total"] <= v["costs"]["budget"],
        "invented_places": sum(s["id"] not in allowed for s in stops),
        "stops": len(stops), "empty_days": sum(not d["stops"] for d in v["itinerary"]["days"]),
        "priority": v["request"].get("priority"), "n_days": len(v["itinerary"]["days"]), "meals": sum(len(d.get("meals") or {}) for d in v["itinerary"]["days"]),
        "rain_conflicts": "rain_outdoor" in left, "closed_conflicts": "closed_place" in left,
        "warnings": v["final"]["warnings"], "transport": f'{v["transport"]["choice"]["mode"]} '
                                                          f'({v["transport"]["choice"]["source"]})',
        "stay_source": v["stay"]["choice"]["source"], "places_source": v["activities"]["source"],
    }


def main():
    graph = build_graph()
    rows = []
    print(f"{'trip':26} {'ok':3} {'budget':>9} {'total':>9} {'rnds':>4} {'stops':>5} {'secs':>5}  transport")
    for name, msg, answers in TRIPS:
        try:
            r = run_trip(graph, name, msg, answers)
        except Exception as e:  # noqa: BLE001 - one broken trip shouldn't stop the run
            r = {"trip": name, "finished": False, "error": repr(e)}
        rows.append(r)
        if r["finished"]:
            ok = "yes" if r["within_budget"] and not r["warnings"] else "~"
            print(f"{name:26} {ok:3} {r['budget']:>9,} {r['total']:>9,} {r['rounds']:>4} {r['stops']:>5} "
                  f"{r['seconds']:>5}  {r['transport']}" + (f"  asked: {', '.join(r['asked'])}" if r["asked"] else ""))
        else:
            print(f"{name:26} NO   {r.get('error') or 'did not finish'}")

    done = [r for r in rows if r["finished"]]
    n = len(rows)
    summary = {
        "trips": n,
        "finished": len(done),
        "within_budget": sum(r["within_budget"] for r in done),
        "no_warnings": sum(not r["warnings"] for r in done),
        "invented_places": sum(r["invented_places"] for r in done),
        "rain_conflicts_left": sum(r["rain_conflicts"] for r in done),
        "closed_conflicts_left": sum(r["closed_conflicts"] for r in done),
        "avg_replan_rounds": round(sum(r["rounds"] for r in done) / max(1, len(done)), 2),
        "avg_stops_per_day": round(sum(r["stops"] for r in done) / max(1, sum(r["n_days"] for r in done)), 1),
        "avg_seconds": round(sum(r["seconds"] for r in done) / max(1, len(done)), 1),
    }
    print("\n" + "\n".join(f"{k:>22}: {v}" for k, v in summary.items()))
    out = CACHE_DIR / "eval.json"
    out.write_text(json.dumps({"summary": summary, "trips": rows}, indent=2, default=str))
    print(f"\nSaved to {out}")
    return 0 if summary["finished"] == n and summary["invented_places"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
