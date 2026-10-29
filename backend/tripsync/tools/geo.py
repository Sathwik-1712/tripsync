"""Geocoding (Nominatim), city reference data, and travel-time estimates (OSRM)."""
import csv
import logging
import math
import re
from functools import lru_cache

from ..config import DATA_DIR
from ..http import get_json

log = logging.getLogger(__name__)


@lru_cache
def cities() -> dict[str, dict]:
    out = {}
    with open(DATA_DIR / "cities.csv", newline="") as f:
        for row in csv.DictReader(f):
            for k in ("lat", "lon", "airport_lat", "airport_lon"):
                row[k] = float(row[k]) if row[k] else None
            for k in ("has_airport", "radius_km", "food_budget", "food_mid", "food_premium", "local_per_day",
                      "stay_budget", "stay_mid", "stay_premium"):
                row[k] = int(row[k])
            out[row["city"].lower()] = row
    return out


@lru_cache
def _alias_index() -> list[tuple[str, str]]:
    """(alias, canonical) pairs, longest alias first so 'new delhi' beats 'delhi'."""
    pairs = []
    for key, row in cities().items():
        if key == "_default":
            continue
        pairs.append((key, row["city"]))
        pairs += [(a.strip().lower(), row["city"]) for a in row["aliases"].split("|") if a.strip()]
    return sorted(pairs, key=lambda p: -len(p[0]))


def find_cities(text: str) -> list[tuple[int, str]]:
    """All known cities mentioned in text, as (position, canonical name)."""
    low = text.lower()
    found, taken = [], []
    for alias, city in _alias_index():
        for m in re.finditer(rf"\b{re.escape(alias)}\b", low):
            if any(s < m.end() and m.start() < e for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), city))
    return sorted(found)


def resolve_city(text: str) -> str | None:
    hits = find_cities(text)
    return hits[0][1] if hits else None


def city_info(city: str | None) -> dict:
    return cities().get((city or "").lower()) or cities()["_default"]


@lru_cache(maxsize=256)
def geocode(place: str) -> dict | None:
    """City table first (curated city-centre points; Nominatim returns e.g. the
    centroid of Goa *state*), then Nominatim with a proper UA and 1 req/sec."""
    row = cities().get((resolve_city(place) or place).lower())
    if row and row["lat"] is not None:
        return {"lat": row["lat"], "lon": row["lon"], "display": row["city"], "source": "city table"}
    try:
        res = get_json(
            "https://nominatim.openstreetmap.org/search",
            {"q": f"{place}, India", "format": "json", "limit": 1, "countrycodes": "in"},
            throttle_key="nominatim", min_interval=1.0,
        )
        if res:
            return {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]),
                    "display": res[0]["display_name"], "source": "Nominatim"}
    except Exception as e:  # noqa: BLE001 - any failure falls back
        log.info("Nominatim failed for %s: %s", place, e)
    return None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _estimate_minutes(a, b) -> float:
    # Straight line x1.4 for road winding, ~22 km/h average Indian city traffic.
    return haversine_km(a, b) * 1.4 / 22 * 60


def travel_table(points: list[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]], str]:
    """Pairwise driving minutes and road kilometres. Saved routes first, then the OSRM public demo server
    (results are saved); otherwise a straight-line estimate (x1.4 for road winding)."""
    from .. import db
    if len(points) < 2:
        return [[0.0]], [[0.0]], "n/a"
    pairs = [(a, b) for a in points for b in points if a != b]
    known = db.get_routes(pairs)
    if len(known) == len(pairs):
        km = [[0.0 if a == b else known[(a, b)][0] for b in points] for a in points]
        minutes = [[0.0 if a == b else known[(a, b)][1] for b in points] for a in points]
        return minutes, km, "OSRM"
    try:
        coords = ";".join(f"{lon},{lat}" for lat, lon in points)
        res = get_json(f"https://router.project-osrm.org/table/v1/driving/{coords}",
                       {"annotations": "duration,distance"}, timeout=15)
        if res.get("code") == "Ok":
            minutes = [[(d or 0) / 60 for d in row] for row in res["durations"]]
            km = [[(d or 0) / 1000 for d in row] for row in res["distances"]]
            db.save_routes([(a, b, km[i][j], minutes[i][j], "OSRM") for i, a in enumerate(points)
                            for j, b in enumerate(points) if i != j])
            return minutes, km, "OSRM"
    except Exception as e:  # noqa: BLE001
        log.info("OSRM failed: %s", e)
    return ([[_estimate_minutes(a, b) for b in points] for a in points],
            [[haversine_km(a, b) * 1.4 for b in points] for a in points], "estimate")


def travel_matrix(points: list[tuple[float, float]]) -> tuple[list[list[float]], str]:
    """Pairwise driving minutes (see travel_table)."""
    minutes, _, source = travel_table(points)
    return minutes, source


def travel_from(origin: tuple[float, float], points: list[tuple[float, float]]) -> tuple[list[tuple], str]:
    """Road (km, minutes) from one point to each of many, e.g. a hotel to every candidate place. Saved routes
    first, then one OSRM table call with the origin as the only source; straight-line estimate if that fails."""
    from .. import db
    if not points:
        return [], "n/a"
    known = db.get_routes([(origin, p) for p in points])
    missing = [p for p in points if (origin, p) not in known]
    source = "OSRM"
    if missing:
        try:
            coords = ";".join(f"{lon},{lat}" for lat, lon in [origin] + missing)
            res = get_json(f"https://router.project-osrm.org/table/v1/driving/{coords}",
                           {"annotations": "duration,distance", "sources": "0"}, timeout=20)
            if res.get("code") != "Ok":
                raise ValueError(res.get("code"))
            rows = [(origin, p, (res["distances"][0][i + 1] or 0) / 1000, (res["durations"][0][i + 1] or 0) / 60,
                     "OSRM") for i, p in enumerate(missing)]
            db.save_routes(rows)
            known |= {(a, b): (km, minutes, src) for a, b, km, minutes, src in rows}
        except Exception as e:  # noqa: BLE001
            log.info("OSRM failed: %s", e)
            source = "estimate"
            known |= {(origin, p): (haversine_km(origin, p) * 1.4, _estimate_minutes(origin, p), "estimate")
                      for p in missing}
    return [known[(origin, p)][:2] for p in points], source
