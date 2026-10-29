"""Accommodation options. Fallback chain from the design sheet:
LiteAPI (key) -> SerpApi Google Hotels -> Overpass names + static price table."""
import logging
import math
import os
import re
from datetime import date, timedelta
from functools import lru_cache
from urllib.parse import quote

from .. import db
from ..http import get_json, post_json
from .geo import city_info
from .places import overpass

log = logging.getLogger(__name__)
TIERS = ["budget", "mid", "premium"]
LITEAPI = "https://api.liteapi.travel/v3.0"


def _tier(nightly: float, info: dict) -> str:
    return ("budget" if nightly <= info["stay_budget"] * 1.3
            else "premium" if nightly >= info["stay_premium"] * 0.7 else "mid")


# LiteAPI hotelTypeId -> the property types we show.
HOTEL_TYPES = {201: "apartment", 203: "hostel", 204: "hotel", 205: "hotel", 206: "resort", 207: "apartment",
               208: "homestay", 210: "homestay", 212: "resort", 213: "villa", 216: "homestay", 218: "hotel",
               219: "apartment", 220: "villa", 221: "resort", 222: "homestay", 229: "apartment", 230: "villa",
               231: "hotel", 233: "resort", 250: "villa", 264: "hostel", 265: "houseboat", 274: "resort", 278: "hotel"}
# Amenities worth showing, in this order, matched against LiteAPI facility names.
AMENITIES = ["pool", "free wifi|wifi", "breakfast", "air conditioning", "parking", "restaurant", "spa",
             "fitness|gym", "airport shuttle", "beach"]


def property_type(name: str, fallback: str = "hotel") -> str:
    n = name.lower()
    for kind, pat in (("hostel", r"hostel|backpacker"), ("resort", r"resort|retreat"),
                      ("homestay", r"homestay|home stay|guest ?house|b ?& ?b|bed and breakfast"),
                      ("villa", r"\bvilla"), ("apartment", r"apartment|serviced|suites? by")):
        if re.search(pat, n):
            return kind
    return fallback


def booking_search(name: str, city: str) -> str:
    """A Google Hotels search for this property: live prices and booking sites."""
    return f"https://www.google.com/travel/hotels?q={quote(f'{name} {city}')}"


@lru_cache
def _facility_names(key: str) -> dict:
    try:
        rows = get_json(f"{LITEAPI}/data/facilities", headers={"X-API-Key": key, "accept": "application/json"},
                        timeout=30, expire_after=timedelta(days=30)).get("data") or []
    except Exception:  # noqa: BLE001
        return {}
    return {r["facility_id"]: r["facility"] for r in rows if r.get("facility_id")}


def _amenities(ids, key: str) -> list[str]:
    names = [n.lower() for n in (_facility_names(key).get(i) for i in (ids or [])) if n]
    return [pat.split("|")[0].replace("free ", "").title() for pat in AMENITIES
            if any(re.search(pat, n) for n in names)][:6]


def _num(v):
    try:
        return float(v) if v not in (None, "", "None") else None
    except (TypeError, ValueError):
        return None


def _liteapi(city: str, check_in: date, check_out: date, travellers: int) -> list[dict]:
    """LiteAPI (sandbox or live key): hotel list for the city, then live rates for those hotels."""
    key = os.getenv("LITEAPI_API_KEY")
    if not key:
        return []
    headers, info = {"X-API-Key": key, "accept": "application/json"}, city_info(city)
    rooms = math.ceil(travellers / 2)
    try:
        hotels = get_json(f"{LITEAPI}/data/hotels", {"countryCode": "IN", "cityName": city, "limit": 40},
                          headers=headers, timeout=30).get("data") or []
        by_id = {h["id"]: h for h in hotels if h.get("id")}
        if not by_id:
            return []
        res = post_json(f"{LITEAPI}/hotels/rates", headers=headers, timeout=45, json={
            "hotelIds": list(by_id), "checkin": check_in.isoformat(), "checkout": check_out.isoformat(),
            "currency": "INR", "guestNationality": "IN", "maxRatesPerHotel": 1,
            "occupancies": [{"adults": min(2, travellers - 2 * r)} for r in range(rooms)]})
    except Exception as e:  # noqa: BLE001
        log.info("LiteAPI failed: %s", e)
        return []
    nights, out = max(1, (check_out - check_in).days), []
    for h in res.get("data") or []:
        offers = [rt for rt in h.get("roomTypes") or [] if (rt.get("offerRetailRate") or {}).get("amount")]
        meta = by_id.get(h.get("hotelId"))
        if not offers or not meta:
            continue
        best = min(offers, key=lambda rt: rt["offerRetailRate"]["amount"])
        rate = (best.get("rates") or [{}])[0]
        refundable = ((rate.get("cancellationPolicies") or {}).get("refundableTag"))
        nightly = int(best["offerRetailRate"]["amount"] / nights / rooms)  # rate covers every room, whole stay
        out.append({"name": meta["name"], "tier": _tier(nightly, info), "nightly": nightly,
                    "lat": _num(meta.get("latitude")), "lon": _num(meta.get("longitude")),
                    "rating": _num(meta.get("rating")), "rating_scale": 10,
                    "reviews": int(_num(meta.get("reviewCount")) or 0) or None, "stars": _num(meta.get("stars")),
                    "address": meta.get("address"),
                    "kind": HOTEL_TYPES.get(int(_num(meta.get("hotelTypeId")) or 0)) or property_type(meta["name"]),
                    "amenities": _amenities(meta.get("facilityIds"), key),
                    "cancellation": {"RFN": "Free cancellation until shortly before check-in",
                                     "NRFN": "Non-refundable"}.get(refundable),
                    "room": rate.get("name"), "board": rate.get("boardName"), "source": "LiteAPI"})
    return out


def _serpapi_hotels(city: str, check_in: date, check_out: date, travellers: int) -> list[dict]:
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        return []
    try:
        res = get_json("https://serpapi.com/search.json", {
            "engine": "google_hotels", "q": f"hotels in {city}", "check_in_date": check_in.isoformat(),
            "check_out_date": check_out.isoformat(), "adults": travellers, "currency": "INR",
            "gl": "in", "hl": "en", "api_key": key}, timeout=30)
    except Exception as e:  # noqa: BLE001
        log.info("SerpApi hotels failed: %s", e)
        return []
    info = city_info(city)
    out = []
    for p in res.get("properties", [])[:15]:
        nightly = (p.get("rate_per_night") or {}).get("extracted_lowest")
        gps = p.get("gps_coordinates") or {}
        if not nightly:
            continue
        tier = _tier(nightly, info)
        kind = "apartment" if p.get("type") == "vacation rental" else property_type(p["name"])
        out.append({"name": p["name"], "tier": tier, "nightly": int(nightly), "lat": gps.get("latitude"),
                    "lon": gps.get("longitude"), "rating": p.get("overall_rating"), "rating_scale": 5,
                    "reviews": p.get("reviews"), "stars": p.get("extracted_hotel_class"), "kind": kind,
                    "amenities": (p.get("amenities") or [])[:6], "booking_url": p.get("link"),
                    "source": "SerpApi Google Hotels"})
    return out


def _osm_hotels(city: str, lat: float, lon: float) -> list[dict]:
    q = (f'[out:json][timeout:30];nwr["tourism"~"^(hotel|guest_house|hostel)$"]["name"]'
         f"(around:4000,{lat},{lon});out center tags 150;")
    elements = overpass(q)
    if elements is None:
        return []
    info, out = city_info(city), []
    for el in elements:
        tags, c = el.get("tags", {}), el.get("center") or el
        try:
            stars = int(tags.get("stars", "0")[0])
        except ValueError:
            stars = 0
        tier = ("budget" if tags["tourism"] in ("hostel", "guest_house")
                else "premium" if stars >= 4 else "mid")
        out.append({"name": tags["name"], "tier": tier, "nightly": info[f"stay_{tier}"], "lat": c.get("lat"),
                    "lon": c.get("lon"), "rating": None, "stars": stars or None,
                    "kind": {"hostel": "hostel", "guest_house": "homestay"}.get(tags["tourism"],
                                                                               property_type(tags["name"])),
                    "source": "OpenStreetMap + price table (estimate)", "estimate": True,
                    "_rank": stars + (3 if tags.get("wikidata") else 0) + (1 if tags.get("website") else 0)})
    out.sort(key=lambda h: -h.pop("_rank"))
    # Keep a handful per tier.
    return [h for t in TIERS for h in [x for x in out if x["tier"] == t][:4]]


def _generic(city: str, lat: float, lon: float) -> list[dict]:
    info = city_info(city)
    names = {"budget": "Budget guesthouse", "mid": "Mid-range hotel", "premium": "Premium hotel"}
    return [{"name": f"{names[t]} near {city} centre", "tier": t, "nightly": info[f"stay_{t}"], "lat": lat,
             "lon": lon, "rating": None, "kind": "hostel" if t == "budget" else "hotel", "generic": True,
             "estimate": True, "source": "price table (estimate)"} for t in TIERS]


def stay_options(city: str, lat: float, lon: float, check_in: date, check_out: date, travellers: int,
                 live: bool = True) -> list[dict]:
    opts = []
    if live:
        opts = _liteapi(city, check_in, check_out, travellers) or _serpapi_hotels(city, check_in, check_out, travellers)
    if not opts and live:
        opts = _osm_hotels(city, lat, lon)
    # Always make sure every tier has at least one option to fall back to.
    have = {o["tier"] for o in opts}
    opts += [g for g in _generic(city, lat, lon) if g["tier"] not in have]
    nights = max(1, (check_out - check_in).days)
    rooms = math.ceil(travellers / 2)
    for o in opts:
        o.update(nights=nights, rooms=rooms, total=int(o["nightly"] * rooms * nights))
        o.setdefault("estimate", False)
        o.setdefault("kind", property_type(o["name"]))
        o["id"] = f"{o['source']}|{o['name']}"
        if not o.get("generic"):
            o.setdefault("booking_url", booking_search(o["name"], city))
    if live:
        db.save_hotels(city, check_in, opts)
    return opts
