"""Points of interest from OpenStreetMap (Overpass), destination text from
Wikivoyage, and a bundled sights CSV for when both are unreachable."""
import csv
import logging
import re
import time
from datetime import timedelta

from ..config import DATA_DIR
from ..http import get_json, post_json

log = logging.getLogger(__name__)
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
                 "https://overpass.kumi.systems/api/interpreter"]
_overpass_down_until = 0.0

# kind -> (indoor, typical entry fee per person in INR, typical visit minutes). Fees are estimates.
KINDS = {
    "museum": (True, 100, 120), "gallery": (True, 50, 75), "palace": (True, 250, 120),
    "fort": (False, 150, 120), "monument": (False, 50, 60), "memorial": (False, 0, 30),
    "archaeological_site": (False, 100, 90), "temple": (True, 0, 60), "viewpoint": (False, 0, 40),
    "park": (False, 20, 60), "garden": (False, 30, 60), "nature_reserve": (False, 200, 150),
    "beach": (False, 0, 120), "waterfall": (False, 0, 90), "zoo": (False, 100, 150),
    "aquarium": (True, 300, 90), "theme_park": (False, 1200, 240), "attraction": (False, 50, 60),
    "marketplace": (False, 0, 90), "mall": (True, 0, 90), "cafe": (True, 350, 60),
    "nightlife": (True, 800, 120),
}

INTEREST_KINDS = {
    "history": {"fort", "palace", "monument", "memorial", "archaeological_site", "museum"},
    "culture": {"temple", "palace", "gallery", "museum", "marketplace"},
    "nature": {"park", "garden", "nature_reserve", "viewpoint", "waterfall", "zoo", "beach"},
    "beach": {"beach"},
    "food": {"cafe", "marketplace"},
    "shopping": {"marketplace", "mall"},
    "museums": {"museum", "gallery"},
    "nightlife": {"nightlife"},
    "adventure": {"theme_park", "nature_reserve", "waterfall", "viewpoint"},
}


def classify(tags: dict) -> str | None:
    t, h, a = tags.get("tourism"), tags.get("historic"), tags.get("amenity")
    if t in ("museum", "gallery", "zoo", "aquarium", "theme_park", "viewpoint"):
        return t
    if h in ("fort", "castle"):
        return "fort"
    if h == "palace" or tags.get("castle_type") == "palace":
        return "palace"
    if h in ("monument", "memorial", "archaeological_site", "ruins", "tomb"):
        return {"ruins": "archaeological_site", "tomb": "monument"}.get(h, h)
    if a == "place_of_worship":
        return "temple"
    if tags.get("natural") == "beach":
        return "beach"
    if tags.get("waterway") == "waterfall" or tags.get("natural") == "waterfall":
        return "waterfall"
    if tags.get("leisure") in ("park", "garden", "nature_reserve"):
        return tags["leisure"]
    if a == "marketplace":
        return "marketplace"
    if tags.get("shop") == "mall":
        return "mall"
    if a == "cafe":
        return "cafe"
    if a in ("bar", "pub", "nightclub"):
        return "nightlife"
    if t == "attraction":
        return "attraction"
    return None


def _query(lat: float, lon: float, radius_m: int, interests: list[str]) -> str:
    near = f"(around:{radius_m},{lat},{lon})"
    near_small = f"(around:{radius_m // 3},{lat},{lon})"
    parts = [
        f'nwr["tourism"~"^(attraction|museum|gallery|viewpoint|zoo|aquarium|theme_park)$"]["name"]{near};',
        f'nwr["historic"~"^(fort|castle|palace|monument|memorial|archaeological_site|ruins|tomb)$"]["name"]{near};',
        f'nwr["amenity"="place_of_worship"]["wikidata"]{near};',
        f'nwr["leisure"~"^(park|garden|nature_reserve)$"]["wikidata"]{near};',
        f'nwr["natural"="beach"]["name"]{near};',
        f'nwr["waterway"="waterfall"]["name"]{near};',
        f'nwr["amenity"="marketplace"]["name"]{near};',
        f'nwr["shop"="mall"]["name"]{near_small};',
    ]
    if "food" in interests:
        parts.append(f'nwr["amenity"="cafe"]["name"]{near_small};')
    if "nightlife" in interests:
        parts.append(f'nwr["amenity"~"^(bar|pub|nightclub)$"]["name"]{near_small};')
    return "[out:json][timeout:40];(" + "".join(parts) + ");out center tags;"


def _score(kind: str, tags: dict, interests: list[str]) -> float:
    s = 0.0
    if tags.get("wikidata"):
        s += 3
    if tags.get("wikipedia"):
        s += 2
    if tags.get("tourism") == "attraction":
        s += 1
    if kind in ("museum", "palace", "fort", "beach", "archaeological_site"):
        s += 1
    if kind == "memorial" and not tags.get("wikidata"):
        s -= 2
    if any(kind in INTEREST_KINDS.get(i, ()) for i in interests):
        s += 3
    return s


def _poi(name: str, kind: str, lat: float, lon: float, score: float, source: str, tags: dict | None = None) -> dict:
    indoor, fee, minutes = KINDS[kind]
    tags = tags or {}
    return {
        "id": f"{name.lower()}@{lat:.4f},{lon:.4f}",
        "name": name, "kind": kind, "lat": lat, "lon": lon,
        "indoor": indoor, "fee": fee, "minutes": minutes, "score": score, "source": source,
        "opening_hours": tags.get("opening_hours"),
        "wikipedia": tags.get("wikipedia"),
        "description": (tags.get("description") or "")[:240] or None,
        "fee_known": "fee" in tags or "charge" in tags,
    }


def overpass(query: str) -> list[dict] | None:
    """Try each public mirror; if all fail, skip Overpass for 10 minutes so the
    graph doesn't stall on every rerun (public servers are often overloaded)."""
    global _overpass_down_until
    if time.monotonic() < _overpass_down_until:
        return None
    deadline = time.monotonic() + 45  # total wait across all mirrors; the main server often takes ~35 s
    for url in OVERPASS_URLS:
        left = deadline - time.monotonic()
        if left < 3:
            break
        try:
            # Sights rarely change, so keep answers for a month: only the first trip to a city waits.
            return post_json(url, {"data": query}, timeout=min(40, left),
                             expire_after=timedelta(days=30))["elements"]
        except Exception as e:  # noqa: BLE001
            log.info("Overpass %s failed: %s", url, e)
    _overpass_down_until = time.monotonic() + 600
    return None


def fetch_pois(lat: float, lon: float, radius_km: int, interests: list[str]) -> list[dict]:
    elements = overpass(_query(lat, lon, radius_km * 1000, interests))
    if elements is None:
        return []
    seen, out = set(), []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        kind = classify(tags)
        c = el.get("center") or el
        if not name or not kind or "lat" not in c or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(_poi(name, kind, c["lat"], c["lon"], _score(kind, tags, interests), "OpenStreetMap", tags))
    return sorted(out, key=lambda p: -p["score"])


# Wikivoyage listing templates: {{see | name=... | lat=... | long=... | hours=... | price=... }}
_LISTING = re.compile(r"\{\{\s*(see|do|eat|drink|buy|sleep|listing)\s*\|(.*?)\}\}", re.S | re.I)
_NAME_KINDS = [  # first match wins
    (r"\b(fort|qila|garh|kila|durg)\b|fort$", "fort"), (r"palace|mahal\b|haveli|niwas|vilas", "palace"),
    (r"museum|planetarium|science cent", "museum"), (r"galler", "gallery"),
    (r"temple|mandir|church|cathedral|basilica|masjid|mosque|dargah|gurudwara|gurdwara|monastery|gompa|stupa|"
     r"synagogue|ashram|ghat\b", "temple"),
    (r"beach", "beach"), (r"falls?\b|waterfall", "waterfall"), (r"\bzoo\b|zoological", "zoo"),
    (r"garden|\bbagh\b", "garden"), (r"\bpark\b|lake|sanctuary|national park|reserve", "park"),
    (r"market|bazaa?r|chowk", "marketplace"), (r"\bmall\b", "mall"),
    (r"view ?point|\bpoint\b|\bpeak\b|\bhill\b|top\b", "viewpoint"),
    (r"tomb|maqbara|memorial|chhatri|cenotaph|samadhi", "memorial"),
    (r"stepwell|baori|baoli|tower|minar|gate|darwaza|monument", "monument"), (r"caves?|ruins", "archaeological_site"),
]


# Only the See/Do sections hold sights and Eat holds restaurants. The same listing template is also used
# for hospitals ("Stay healthy"), consulates ("Cope"), hotels ("Sleep") and so on, which must be skipped.
SIGHT_SECTIONS, EAT_SECTIONS = {"see", "do"}, {"eat"}
NOT_A_SIGHT = re.compile(
    r"hospital|clinic|consulate|embassy|high commission|police|\bbank\b|\batm\b|pharmacy|chemist|"
    r"\bairport\b|railway station|bus (stand|station)|\bhotel\b|hostel|guest ?house|post office|office\b", re.I)


def _listings_by_section(text: str) -> list[tuple[str, str, str]]:
    """(template, body, top-level section) for each listing, e.g. ("see", "name=Amber Fort | ...", "see")."""
    out, pos, section = [], 0, ""
    heads = [(m.start(), m.group(2).strip().lower()) for m in re.finditer(r"^(==)\s*([^=].*?)\s*==\s*$", text, re.M)]
    for m in _LISTING.finditer(text):
        while pos < len(heads) and heads[pos][0] < m.start():
            section = heads[pos][1]
            pos += 1
        out.append((m.group(1), m.group(2), section))
    return out


def _listing_role(template: str, section: str) -> str | None:
    """'sight', 'eat' or None. Typed templates ({{see}}, {{eat}}) are trusted anywhere except a few sections;
    the generic {{listing}} counts only inside See/Do/Eat."""
    if section in ("sleep", "connect", "cope", "stay healthy", "stay safe", "get in", "get around", "buy", "drink"):
        return None
    if template in ("see", "do") or (template == "listing" and section in SIGHT_SECTIONS):
        return "sight"
    if template == "eat" or (template == "listing" and section in EAT_SECTIONS):
        return "eat"
    return None


def _field(body: str, name: str) -> str:
    m = re.search(rf"\|\s*{name}\s*=\s*([^|]*)", "|" + body)
    return re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", m.group(1)).strip() if m else ""


def _description(body: str) -> str | None:
    """The listing's own text, cleaned of wiki markup and cut to a sentence or two."""
    plain = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", body)
    m = re.search(r"\|\s*content\s*=\s*(.*)", "|" + plain, re.S)
    if not m:
        return None
    text = re.sub(r"\{\{[^}]*\}\}|<[^>]+>|'{2,}|\[https?://\S+\s*([^\]]*)\]", lambda x: x.group(1) or "", m.group(1))
    text = re.split(r"\|\s*\w+\s*=", text)[0].strip()
    if len(text) > 220:
        cut = text.rfind(". ", 0, 220)
        text = text[:cut + 1] if cut > 60 else text[:217].rstrip() + "…"
    return text.replace("..", ".") or None


def _kind_from_name(name: str, template: str) -> str:
    low = name.lower()
    hit = next((k for pat, k in _NAME_KINDS if re.search(pat, low)), None)
    return hit or ("attraction" if template != "do" else "attraction")


_TEXT_KINDS = {"temple", "fort", "palace", "museum", "waterfall", "garden", "memorial"}


def _kind_from_text(text: str) -> str | None:
    """Kind from the start of a description; only unambiguous kinds, since later words often describe
    the surroundings ("next to Miramar Beach")."""
    low = text[:90].lower()
    return next((k for pat, k in _NAME_KINDS if k in _TEXT_KINDS and re.search(pat, low)), None)


def _fee(price: str) -> int | None:
    """First rupee amount in a Wikivoyage price, e.g. '₹200 Indians, ₹1000 foreigners' -> 200."""
    m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", price, re.I)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0 if re.search(r"\bfree\b", price, re.I) else None


# Region-style articles keep their listings on town/district pages instead.
WIKIVOYAGE_PAGES = {
    "Goa": ["Panaji", "Old Goa", "Anjuna"], "Mumbai": ["Mumbai/South Mumbai", "Mumbai/Fort"],
    "Kochi": ["Kochi/Ernakulam"], "Delhi": ["Delhi", "Delhi/Old Delhi"],
    "Bengaluru": ["Bangalore/Pete", "Bangalore/South"],
    "Kolkata": ["Kolkata/Chowringhee-Park Street", "Kolkata/BBD Bagh", "Kolkata/Burrabazar-Jorasanko"],
    "Chennai": ["Chennai/Central", "Chennai/South"],
    "Hyderabad": ["Hyderabad/Old City", "Hyderabad/Golconda", "Hyderabad/Hussain Sagar"],
}


def _wikitext(page: str) -> str:
    try:
        res = get_json("https://en.wikivoyage.org/w/api.php", {
            "action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1},
            timeout=20, expire_after=timedelta(days=30))
        return res["parse"]["wikitext"]["*"]
    except Exception as e:  # noqa: BLE001
        log.info("Wikivoyage listings failed for %s: %s", page, e)
        return ""


def wikivoyage_listings(city: str, interests: list[str]) -> tuple[list[dict], list[dict]]:
    """Sights and restaurants from the city's Wikivoyage article(s) (CC BY-SA). Only listings with coordinates."""
    text = "\n".join(_wikitext(page) for page in WIKIVOYAGE_PAGES.get(city, [city]))
    sights, eats, seen = [], [], set()
    for template, body, section in _listings_by_section(text):
        kind_of = _listing_role(template.lower(), section)
        name, lat, lon = _field(body, "name"), _field(body, "lat"), _field(body, "long")
        try:
            lat, lon = float(lat), float(lon)
        except ValueError:
            continue
        if not kind_of or not name or name.lower() in seen or NOT_A_SIGHT.search(name):
            continue
        seen.add(name.lower())
        if kind_of == "eat":
            eats.append({"id": f"eat:{name.lower()}", "name": name, "lat": lat, "lon": lon,
                         "price": _field(body, "price")[:80] or None, "description": _description(body),
                         "hours": _field(body, "hours")[:80] or None, "source": "Wikivoyage"})
            continue
        desc = _description(body)
        kind = _kind_from_name(name, template.lower())
        if kind == "attraction" and desc:  # e.g. "Galtaji": the name says nothing, the text says "temple"
            kind = _kind_from_text(desc) or kind
        tags = {"wikidata": _field(body, "wikidata") or None}
        poi = _poi(name, kind, lat, lon, _score(kind, tags, interests) + 1, "Wikivoyage", tags)
        if (fee := _fee(_field(body, "price"))) is not None:
            poi["fee"], poi["fee_known"] = fee, True
        poi["description"] = desc
        poi["hours_text"] = _field(body, "hours")[:80] or None
        sights.append(poi)
    return sorted(sights, key=lambda p: -p["score"]), eats


def fallback_pois(city: str, interests: list[str]) -> list[dict]:
    out = []
    with open(DATA_DIR / "sights.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["city"].lower() == city.lower():
                kind = row["kind"]
                out.append(_poi(row["name"], kind, float(row["lat"]), float(row["lon"]),
                                _score(kind, {"wikidata": "y"}, interests), "bundled sights list"))
    return sorted(out, key=lambda p: -p["score"])


def destination_summary(city: str) -> str:
    try:
        res = get_json("https://en.wikivoyage.org/w/api.php", {
            "action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1,
            "titles": city, "format": "json", "redirects": 1})
        page = next(iter(res["query"]["pages"].values()))
        return (page.get("extract") or "").strip()[:900]
    except Exception as e:  # noqa: BLE001
        log.info("Wikivoyage failed: %s", e)
        return ""


def destination_image(city: str) -> str | None:
    """Lead photo of the city's Wikipedia article (Wikimedia Commons), if any."""
    try:
        res = get_json("https://en.wikipedia.org/w/api.php", {
            "action": "query", "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1400,
            "titles": city, "format": "json", "redirects": 1})
        page = next(iter(res["query"]["pages"].values()))
        return (page.get("thumbnail") or {}).get("source")
    except Exception as e:  # noqa: BLE001
        log.info("Wikipedia image failed: %s", e)
        return None
