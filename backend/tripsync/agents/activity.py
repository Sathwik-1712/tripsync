"""Step 3c: Activity Agent - real places from tools, plus weather. Its candidate
list is the ONLY set of places the Planner is allowed to use."""
import re
import unicodedata
from datetime import date

from .. import db
from ..state import change, trip_dates, violation_for
from ..tools.geo import city_info, geocode, haversine_km
from ..tools.places import (destination_image, destination_summary, fallback_pois, fetch_pois,
                             wikivoyage_listings)
from ..tools.weather import daily_weather

GENERIC = {"the", "of", "church", "temple", "museum", "fort", "beach", "palace", "and", "sri", "shri"}


def _name_key(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.findall(r"[a-z0-9]+", plain) if w not in GENERIC)


def same_place(a: dict, b: dict) -> bool:
    """Same sight from two sources: matching names (ignoring accents and words like 'church'),
    or two points less than 150 m apart."""
    return _name_key(a["name"]) == _name_key(b["name"]) or haversine_km((a["lat"], a["lon"]), (b["lat"], b["lon"])) < 0.15


def saved_osm_places(city: str) -> list[dict]:
    """OpenStreetMap places saved by earlier trips, for when Overpass is down. Same ids as live results."""
    out = []
    for r in db.places_for(city, "sight", max_age_days=180, source_like="OpenStreetMap%"):
        out.append({"id": r["id"], "name": r["name"], "kind": r["kind"], "lat": r["lat"], "lon": r["lon"],
                    "indoor": bool(r["indoor"]), "fee": r["fee"] or 0, "fee_known": bool(r["fee_known"]),
                    "minutes": r["minutes"] or 60, "score": r["score"] or 0, "opening_hours": r["hours"],
                    "description": r["description"], "wikipedia": None,
                    "source": f"OpenStreetMap (saved {r['last_seen']})"})
    return sorted(out, key=lambda p: -p["score"])


def popularity(places: list[dict], city: str) -> None:
    """Nudge ranking by what earlier travellers did: must-visit and added places up, skipped ones down."""
    counts = db.pick_counts(city)
    for p in places:
        must, add, skip = counts.get(p["id"], (0, 0, 0))
        p["picks"] = {"must": must, "add": add, "skip": skip}
        p["score"] += max(-2.0, min(3.0, (2 * must + add - 2 * skip) / 5))


DEFAULT_KNOBS = {"max_fee": None, "indoor_days": [], "day_caps": {}}


def activity_node(state: dict) -> dict:
    req = state["request"]
    knobs = {**DEFAULT_KNOBS, **(state.get("constraints", {}).get("activity") or {})}
    knobs["indoor_days"] = list(knobs["indoor_days"])
    knobs["day_caps"] = dict(knobs["day_caps"])
    v, notes, changes = violation_for(state, "activity"), [], []
    if v.get("type") == "rain_outdoor":
        knobs["indoor_days"] = sorted(set(knobs["indoor_days"]) | set(v["dates"]))
        notes.append(f"indoor-only on rainy {', '.join(v['dates'])}")
        changes.append(change("schedule", f"Outdoor stops on {', '.join(v['dates'])}", "Indoor places only that day",
                              "Rain is forecast on that day"))
    elif v.get("type") == "overpacked_day":
        knobs["day_caps"][str(v["day"])] = max(1, v["count"] - 1)
        notes.append(f"day {v['day']} capped at {knobs['day_caps'][str(v['day'])]} stops")
        changes.append(change("schedule", f"Day {v['day']}: {v['count']} stops",
                              f"Day {v['day']}: at most {knobs['day_caps'][str(v['day'])]} stops",
                              f"The day was too long ({v['travel_min']} min on the road)"))
    elif v.get("type") == "activities_over":
        knobs["max_fee"] = 100 if knobs["max_fee"] is None or knobs["max_fee"] > 100 else 0
        notes.append(f"entry fees capped at ₹{knobs['max_fee']}")
        changes.append(change("places", "Any entry fee", f"Entry fees up to ₹{knobs['max_fee']} per person",
                              f"Activities were ₹{v['deficit']:,} over their limit and the whole trip was over budget"))

    city = req["destination"]
    loc = geocode(city)
    if not loc:
        return {"activities": {"candidates": [], "source": "none"}, "constraints": {"activity": knobs},
                "log": [f"[Activity] could not locate {city}"]}
    dates = trip_dates(req)
    weather = daily_weather(loc["lat"], loc["lon"], dates[0], dates[-1])
    interests = req.get("interests", [])
    pois = fetch_pois(loc["lat"], loc["lon"], city_info(city)["radius_km"], interests)
    wv_sights, food_spots = wikivoyage_listings(city, interests)
    db.save_places(city, pois)
    db.save_places(city, wv_sights)
    db.save_places(city, food_spots, role="eat")
    source = "OpenStreetMap (Overpass)"
    if not pois and (pois := saved_osm_places(city)):  # Overpass is down: use what earlier trips found
        source = pois[0]["source"]
    if len(pois) < 12:  # top up from Wikivoyage, then the bundled list, skipping places we already have
        sources = [source] if pois else []
        for extra, label in ((wv_sights, "Wikivoyage"), (fallback_pois(city, interests), "bundled sights list")):
            new = []
            for p in extra:
                if not any(same_place(p, q) for q in pois + new):
                    new.append(p)
            if new:
                pois += new
                sources.append(label)
        pois.sort(key=lambda p: -p["score"])
        source = " + ".join(sources) or "none"
    popularity(pois, city)
    pois.sort(key=lambda p: -p["score"])
    if knobs["max_fee"] is not None:
        pois = [p for p in pois if p["fee"] <= knobs["max_fee"]]
    pois = pois[:60]
    rainy = [w["date"] for w in weather if w.get("precip_mm", 0) >= 5 or (w.get("precip_prob") or 0) >= 60]
    return {
        "destination": {**loc, "city": city, "summary": destination_summary(city), "image": destination_image(city)},
        "weather": weather,
        "activities": {"candidates": pois, "source": source, "food_spots": food_spots},
        "constraints": {"activity": knobs},
        "changes": changes,
        "log": [f"[Activity] {len(pois)} places from {source}; weather: "
                f"{weather[0]['source'] if weather else 'unavailable'}"
                f"{'; ' + str(len(food_spots)) + ' places to eat' if food_spots else ''}"
                f"{'; rain likely on ' + ', '.join(rainy) if rainy else ''}"
                f"{'; ' + '; '.join(notes) if notes else ''}"],
    }
