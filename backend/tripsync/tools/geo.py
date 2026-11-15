"""Geocoding (Nominatim), city reference data, and travel-time estimates (OSRM)."""
import csv
import logging
import math
import re
from functools import lru_cache

from .. import trace
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


def _osrm(points: list, sources: list[int], destinations: list[int]) -> dict:
    """{(a, b): (km, minutes)} from one OSRM table call, saved for reuse. Pairs OSRM can't route (null,
    e.g. no road to an island) are left out, so callers estimate them rather than read them as 0 km."""
    from .. import db
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    res = get_json(f"https://router.project-osrm.org/table/v1/driving/{coords}",
                   {"annotations": "duration,distance", "sources": ";".join(map(str, sources)),
                    "destinations": ";".join(map(str, destinations))}, timeout=20)
    if res.get("code") != "Ok":
        raise ValueError(res.get("code"))
    out = {}
    for i, si in enumerate(sources):
        for j, dj in enumerate(destinations):
            sec, metres = res["durations"][i][j], res["distances"][i][j]
            if si != dj and sec is not None and metres is not None:
                out[(points[si], points[dj])] = (metres / 1000, sec / 60)
    db.save_routes([(a, b, km, minutes, "OSRM") for (a, b), (km, minutes) in out.items()])
    return out


def _estimate(a, b) -> tuple[float, float]:
    return haversine_km(a, b) * 1.4, _estimate_minutes(a, b)


def _cover(missing: list[tuple]) -> list:
    """A few points that touch every missing pair (greedy), so only their rows and columns are fetched."""
    left, out = set(missing), []
    while left:
        counts: dict = {}
        for a, b in left:
            counts[a] = counts.get(a, 0) + 1
            counts[b] = counts.get(b, 0) + 1
        best = max(counts, key=counts.get)
        out.append(best)
        left = {(a, b) for a, b in left if best not in (a, b)}
    return out


def travel_table(points: list[tuple[float, float]]) -> tuple[list[list[float]], list[list[float]], str]:
    """Pairwise driving minutes and road kilometres. Saved routes first; only the missing ones come from the
    OSRM public demo server (and are saved); anything still unknown is a straight-line estimate (x1.4)."""
    from .. import db
    if len(points) < 2:
        return [[0.0]], [[0.0]], "n/a"
    pairs = [(a, b) for a in points for b in points if a != b]
    known = {k: v[:2] for k, v in db.get_routes(pairs).items()}
    missing = [pq for pq in pairs if pq not in known]
    if known:
        trace.record("TripSync database", f"{len(known)} of {len(pairs)} road routes already saved", cached=True,
                     kind="db")
    if missing:
        idx = {pt: i for i, pt in enumerate(points)}
        new = sorted({idx[pt] for pt in _cover(missing)})
        everyone = list(range(len(points)))
        try:
            if 2 * len(new) >= len(points):  # mostly new: one full table
                known |= _osrm(points, everyone, everyone)
            else:  # a few new points: just their rows and columns
                known |= _osrm(points, new, everyone)
                known |= _osrm(points, everyone, new)
        except Exception as e:  # noqa: BLE001
            log.info("OSRM failed: %s", e)
    estimated = [pq for pq in pairs if pq not in known]
    if estimated:
        trace.record("Straight-line estimate", f"{len(estimated)} routes OSRM couldn't give (x1.4 road factor)",
                     kind="estimate")
    known |= {(a, b): _estimate(a, b) for a, b in estimated}
    km = [[0.0 if a == b else known[(a, b)][0] for b in points] for a in points]
    minutes = [[0.0 if a == b else known[(a, b)][1] for b in points] for a in points]
    return minutes, km, "estimate" if estimated else "OSRM"


def travel_matrix(points: list[tuple[float, float]]) -> tuple[list[list[float]], str]:
    """Pairwise driving minutes (see travel_table)."""
    minutes, _, source = travel_table(points)
    return minutes, source


def travel_from(origin: tuple[float, float], points: list[tuple[float, float]]) -> tuple[list[tuple], str]:
    """Road (km, minutes) from one point to each of many, e.g. a hotel to every candidate place. Saved routes
    first, then one OSRM table call with the origin as the only source; straight-line estimate otherwise."""
    from .. import db
    if not points:
        return [], "n/a"
    known = {k: v[:2] for k, v in db.get_routes([(origin, p) for p in points if p != origin]).items()}
    missing = list(dict.fromkeys(p for p in points if p != origin and (origin, p) not in known))
    if known:
        trace.record("TripSync database", f"{len(known)} routes from this point already saved", cached=True,
                     kind="db")
    if missing:
        try:
            known |= _osrm([origin] + missing, [0], list(range(1, len(missing) + 1)))
        except Exception as e:  # noqa: BLE001
            log.info("OSRM failed: %s", e)
    estimated = [p for p in points if p != origin and (origin, p) not in known]
    known |= {(origin, p): _estimate(origin, p) for p in estimated}
    known[(origin, origin)] = (0.0, 0.0)
    return [known[(origin, p)] for p in points], "estimate" if estimated else "OSRM"
