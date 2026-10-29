"""Intercity transport options. Fallback chain from the design sheet:
flights: Kiwi MCP (no key) -> SerpApi Google Flights -> fast-flights; train/bus: static CSV.
Any pair not in the CSV gets distance-based estimates. All prices are per person, one way, INR."""
import csv
import logging
import os
from datetime import date
from functools import lru_cache
from urllib.parse import quote

from .. import db
from ..config import DATA_DIR, offline
from ..http import get_json
from .geo import city_info, haversine_km
from .mcp import call_tool

log = logging.getLogger(__name__)
KIWI_MCP_URL = os.getenv("KIWI_MCP_URL", "https://mcp.kiwi.com/")


@lru_cache
def _routes() -> list[dict]:
    with open(DATA_DIR / "transport_routes.csv", newline="") as f:
        return list(csv.DictReader(f))


def _csv_options(origin: str, dest: str) -> list[dict]:
    out = []
    for r in _routes():
        if {r["origin"].lower(), r["destination"].lower()} == {origin.lower(), dest.lower()}:
            out.append({"mode": r["mode"], "label": r["label"], "price_pp": int(r["price_pp_oneway"]),
                        "hours": float(r["hours"]), "source": "static price CSV"})
    return out


def _estimated_options(origin: str, dest: str, skip_modes: set[str]) -> list[dict]:
    a, b = city_info(origin), city_info(dest)
    if a["lat"] is None or b["lat"] is None:
        return []
    km = haversine_km((a["lat"], a["lon"]), (b["lat"], b["lon"])) * 1.25
    out = []
    if "train" not in skip_modes and km >= 80:
        out.append({"mode": "train", "label": "Train (3AC)", "price_pp": round(max(250, 1.4 * km), -1),
                    "hours": round(km / 55 + 0.5, 1), "source": "distance estimate"})
    if "bus" not in skip_modes and km <= 1200:
        out.append({"mode": "bus", "label": "AC bus", "price_pp": round(max(200, 1.6 * km), -1),
                    "hours": round(km / 45, 1), "source": "distance estimate"})
    if "flight" not in skip_modes and a["has_airport"] and b["has_airport"] and km >= 350:
        out.append({"mode": "flight", "label": "Flight (typical fare)", "price_pp": round(2200 + 2.0 * km, -2),
                    "hours": round(1 + km / 750, 1), "source": "distance estimate"})
    return out


def _flyable(a: dict, b: dict) -> bool:
    """Both cities have an airport code. Hill and coast towns without their own airport list the nearest
    one (Manali -> Kullu KUU, Darjeeling -> Bagdogra IXB), which is searched instead."""
    return bool(a.get("airport") and b.get("airport")) and a["airport"] != b["airport"]


def _nearby_airport_note(origin: str, dest: str) -> str:
    a, b = city_info(origin), city_info(dest)
    notes = [f"road from {origin} to {a['airport']} first" if not a["has_airport"] else "",
             f"then by road to {dest}" if not b["has_airport"] else ""]
    return "; ".join(n for n in notes if n)


def _kiwi_leg(leg: dict | None) -> dict | None:
    """One direction of a Kiwi itinerary: airports, local times, flight numbers."""
    if not leg or not leg.get("segments"):
        return None
    segs = leg["segments"]
    return {"from": leg.get("from"), "to": leg.get("to"), "from_name": segs[0].get("fromName"),
            "to_name": segs[-1].get("toName"), "depart": leg.get("departureTime"), "arrive": leg.get("arrivalTime"),
            "flights": [s.get("flightNumber") for s in segs if s.get("flightNumber")],
            "carrier": " + ".join(dict.fromkeys(_airline(s.get("carrierName")) for s in segs)),
            "duration_min": round((leg.get("durationSeconds") or 0) / 60) or None,
            "stops": leg.get("stops", 0), "via": (leg.get("route") or [])[1:-1]}


def _airline(name: str | None) -> str:
    return (name or "Flight").replace(" Limited", "").replace(" Airlines", "")


def _kiwi_mcp(origin: str, dest: str, out_date: date, back_date: date) -> list[dict]:
    """Kiwi.com's public MCP server (no key). Prices are round trip for one adult."""
    a, b = city_info(origin), city_info(dest)
    if not _flyable(a, b):
        return []
    try:
        res = call_tool(KIWI_MCP_URL, "search-flight", {
            "flyFrom": a["airport"], "flyTo": b["airport"], "departureDate": out_date.strftime("%d/%m/%Y"),
            "returnDate": back_date.strftime("%d/%m/%Y"), "adults": 1, "currency": "INR", "sort": "price"})
    except Exception as e:  # noqa: BLE001
        log.info("Kiwi MCP failed: %s", e)
        return []
    if res.get("error") or (res.get("currency") or "INR") != "INR":
        return []
    out, seen = [], set()
    for it in res.get("itineraries") or []:
        leg = it.get("outbound") or {}
        segs = leg.get("segments") or [{}]
        back_segs = (it.get("inbound") or {}).get("segments") or []
        carriers = list(dict.fromkeys(s.get("carrierName") or "Flight" for s in segs + back_segs))
        airline = " + ".join(_airline(c) for c in carriers[:2])
        key = (leg.get("departureTime"), (it.get("inbound") or {}).get("departureTime"))
        # Keep distinct schedules, at most two per outbound time, so there are real alternatives to pick from.
        same_out = sum(1 for k in seen if k[0] == key[0])
        if not it.get("price") or key in seen or same_out >= 2:
            continue
        seen.add(key)
        stops = leg.get("stops", 0)
        out.append({"mode": "flight", "label": f"{airline} (economy{', non-stop' if not stops else f', {stops} stop'})",
                    "price_pp": round(it["price"] / 2), "hours": round(leg.get("durationSeconds", 7200) / 3600, 1),
                    "source": "Kiwi.com", "booking_url": it.get("bookingUrl"), "live": True,
                    "out": _kiwi_leg(leg), "back": _kiwi_leg(it.get("inbound"))})
        if len(out) == 8:
            break
    return out


def _serpapi_flights(origin: str, dest: str, out_date: date, back_date: date) -> list[dict]:
    key = os.getenv("SERPAPI_API_KEY")
    a, b = city_info(origin), city_info(dest)
    if not key or not _flyable(a, b):
        return []
    try:
        res = get_json("https://serpapi.com/search.json", {
            "engine": "google_flights", "departure_id": a["airport"], "arrival_id": b["airport"],
            "outbound_date": out_date.isoformat(), "return_date": back_date.isoformat(),
            "currency": "INR", "hl": "en", "adults": 1, "api_key": key}, timeout=30)
    except Exception as e:  # noqa: BLE001
        log.info("SerpApi flights failed: %s", e)
        return []
    out, seen = [], set()
    url = (res.get("search_metadata") or {}).get("google_flights_url")
    for f in (res.get("best_flights") or []) + (res.get("other_flights") or []):
        airline = f["flights"][0].get("airline", "Flight")
        segs = f["flights"]
        key = (airline, (segs[0].get("departure_airport") or {}).get("time"))
        if key in seen or not f.get("price"):
            continue
        seen.add(key)
        dep, arr = segs[0].get("departure_airport") or {}, segs[-1].get("arrival_airport") or {}
        out_leg = {"from": dep.get("id"), "to": arr.get("id"), "from_name": dep.get("name"), "to_name": arr.get("name"),
                   "depart": (dep.get("time") or "").replace(" ", "T") or None,
                   "arrive": (arr.get("time") or "").replace(" ", "T") or None,
                   "flights": [x.get("flight_number") for x in segs if x.get("flight_number")], "carrier": airline,
                   "duration_min": f.get("total_duration"), "stops": len(segs) - 1, "via": [x.get("arrival_airport", {}).get("id") for x in segs[:-1]]}
        # Round-trip price for one adult -> one-way per person. Return times need a second search, so only
        # the outbound schedule is known.
        out.append({"mode": "flight", "label": f"{airline} (economy)", "price_pp": round(f["price"] / 2),
                    "hours": round(f.get("total_duration", 120) / 60, 1), "source": "SerpApi Google Flights",
                    "booking_url": url, "live": True, "out": out_leg, "back": None})
        if len(out) == 6:
            break
    return out


def _fast_flights(origin: str, dest: str, out_date: date, back_date: date) -> list[dict]:
    """Google Flights scraper (fast-flights), one way per adult. Breaks whenever Google changes the page,
    so any failure just means no result from this source."""
    a, b = city_info(origin), city_info(dest)
    if not _flyable(a, b) or offline():
        return []
    try:
        from fast_flights import FlightQuery, Passengers, create_query, get_flights
        q = create_query(flights=[FlightQuery(date=out_date.isoformat(), from_airport=a["airport"],
                                              to_airport=b["airport"])],
                         trip="one-way", seat="economy", passengers=Passengers(adults=1),
                         language="en", currency="INR")
        res = list(get_flights(q))
    except Exception as e:  # noqa: BLE001
        log.info("fast-flights failed: %s", e)
        return []
    out = []
    for f in sorted((f for f in res if f.price), key=lambda f: f.price)[:3]:
        minutes = sum(s.duration for s in f.flights) or 120
        out.append({"mode": "flight", "label": f"{', '.join(f.airlines[:1]) or 'Flight'} (economy)",
                    "price_pp": int(f.price), "hours": round(minutes / 60, 1), "source": "Google Flights (fast-flights)",
                    "live": True})
    return out


def transport_options(origin: str, dest: str, out_date: date, back_date: date, travellers: int,
                      live: bool = True) -> list[dict]:
    flights = []
    if live:
        flights = _kiwi_mcp(origin, dest, out_date, back_date)
        if len(flights) < 3:  # few results: add Google Flights (SerpApi) ones that Kiwi didn't have
            have = {tuple((f.get("out") or {}).get("flights") or []) for f in flights}
            flights += [f for f in _serpapi_flights(origin, dest, out_date, back_date)
                        if tuple((f.get("out") or {}).get("flights") or []) not in have]
        flights = flights or _fast_flights(origin, dest, out_date, back_date)
        if note := _nearby_airport_note(origin, dest):
            for f in flights:
                f["label"] += f" · {note}"
                f["airport_note"] = note
    opts = flights + [o for o in _csv_options(origin, dest) if not (flights and o["mode"] == "flight")]
    opts += _estimated_options(origin, dest, {o["mode"] for o in opts})
    for o in opts:
        o["total"] = int(o["price_pp"] * travellers * 2)  # round trip for the whole group
        o.setdefault("live", False)  # False: a typical fare from our tables, not a bookable schedule
        if o["mode"] == "flight" and not o["live"]:
            o["label"] = "Flight (typical fare)"
        legs = [(o.get(k) or {}).get("depart") or "" for k in ("out", "back")]
        o["id"] = "|".join([o["mode"], o["label"], *legs])
    if live:
        db.save_fares(origin, dest, out_date, opts)
    return sorted(opts, key=lambda o: o["total"])


def search_links(origin: str, dest: str, out_date: date, back_date: date) -> dict:
    """Where to check live fares and timetables yourself. Plain search pages; nothing is pre-booked."""
    a, b = city_info(origin), city_info(dest)
    frm, to = a.get("airport") or origin, b.get("airport") or dest
    q = quote(f"Flights from {frm} to {to} on {out_date.isoformat()} through {back_date.isoformat()}")
    return {"google_flights": f"https://www.google.com/travel/flights?q={q}",
            "kiwi": f"https://www.kiwi.com/en/search/results/{quote(origin.lower())}-india/"
                    f"{quote(dest.lower())}-india/{out_date.isoformat()}/{back_date.isoformat()}",
            "trains": "https://www.irctc.co.in/nget/train-search",
            "buses": f"https://www.redbus.in/bus-tickets/{quote(origin.lower())}-to-{quote(dest.lower())}"}
