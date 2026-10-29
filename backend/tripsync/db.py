"""TripSync's own travel database (SQLite, stdlib only).

Unlike the HTTP cache, which keeps raw replies by URL and throws them away, this keeps cleaned, queryable
records that every trip can reuse:

  places        sights and restaurants, merged across sources, with how often travellers pick or skip them
  hotels        hotel details; hotel_prices keeps one row per price seen
  fares         flight/train/bus prices seen per route and travel month
  routes        road distance and time between two points (OSRM), so routes aren't fetched twice
  trips         each finished plan (no names or emails) and the places the traveller picked

Stored prices are observations for estimates and trends. They are never shown as live prices.
Set TRIPSYNC_DB=:memory: for a throwaway database (tests do)."""
import json
import os
import sqlite3
import statistics
import threading
from datetime import date, timedelta

from .config import CACHE_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY, city TEXT NOT NULL, name TEXT NOT NULL, kind TEXT, role TEXT DEFAULT 'sight',
    lat REAL, lon REAL, description TEXT, fee INTEGER, fee_known INTEGER, minutes INTEGER, indoor INTEGER,
    hours TEXT, price TEXT, score REAL, source TEXT, first_seen TEXT, last_seen TEXT,
    must_count INTEGER DEFAULT 0, add_count INTEGER DEFAULT 0, skip_count INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS places_city ON places(city, role);
CREATE TABLE IF NOT EXISTS hotels (
    id TEXT PRIMARY KEY, city TEXT, name TEXT, kind TEXT, lat REAL, lon REAL, address TEXT, rating REAL,
    rating_scale INTEGER, reviews INTEGER, stars REAL, amenities TEXT, source TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS hotel_prices (
    hotel_id TEXT, city TEXT, tier TEXT, seen_on TEXT, check_in TEXT, nights INTEGER, rooms INTEGER,
    nightly INTEGER, refundable TEXT, source TEXT,
    UNIQUE (hotel_id, seen_on, check_in, nights, rooms));
CREATE INDEX IF NOT EXISTS hotel_prices_city ON hotel_prices(city, tier, seen_on);
CREATE TABLE IF NOT EXISTS fares (
    origin TEXT, destination TEXT, mode TEXT, seen_on TEXT, travel_date TEXT, carrier TEXT, flights TEXT,
    price_pp INTEGER, source TEXT,
    UNIQUE (origin, destination, mode, seen_on, travel_date, carrier, flights));
CREATE INDEX IF NOT EXISTS fares_route ON fares(origin, destination, mode, travel_date);
CREATE TABLE IF NOT EXISTS routes (
    a_lat REAL, a_lon REAL, b_lat REAL, b_lon REAL, km REAL, minutes REAL, source TEXT, seen_on TEXT,
    PRIMARY KEY (a_lat, a_lon, b_lat, b_lon));
CREATE TABLE IF NOT EXISTS trips (
    thread_id TEXT PRIMARY KEY, created TEXT, origin TEXT, destination TEXT, start_date TEXT, end_date TEXT,
    travellers INTEGER, budget INTEGER, priority TEXT, stay_id TEXT, transport_id TEXT, total INTEGER,
    within_budget INTEGER, changes TEXT);
CREATE TABLE IF NOT EXISTS trip_picks (thread_id TEXT, place_id TEXT, mark TEXT, PRIMARY KEY (thread_id, place_id));
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def connect() -> sqlite3.Connection:
    """One shared connection (the graph runs agents on threads). Created with the schema on first use."""
    global _conn
    with _lock:
        if _conn is None:
            path = os.getenv("TRIPSYNC_DB") or str(CACHE_DIR / "tripsync.db")
            _conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            if path != ":memory:":
                _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
        return _conn


def reset() -> None:
    """Drop the connection (tests switch to a fresh in-memory database)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None


def _write(sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    db = connect()
    with _lock:
        db.executemany(sql, rows)


def _today() -> str:
    return date.today().isoformat()


# ---------- places ----------

def save_places(city: str, places: list[dict], role: str = "sight") -> None:
    today = _today()
    _write("""INSERT INTO places (id, city, name, kind, role, lat, lon, description, fee, fee_known, minutes, indoor,
                                  hours, price, score, source, first_seen, last_seen)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET name=excluded.name, kind=excluded.kind, lat=excluded.lat,
                lon=excluded.lon, description=COALESCE(excluded.description, places.description),
                fee=excluded.fee, fee_known=excluded.fee_known, minutes=excluded.minutes, indoor=excluded.indoor,
                hours=COALESCE(excluded.hours, places.hours), price=COALESCE(excluded.price, places.price),
                score=excluded.score, source=excluded.source, last_seen=excluded.last_seen""",
           [(p["id"], city, p["name"], p.get("kind"), role, p["lat"], p["lon"], p.get("description"), p.get("fee"),
             int(bool(p.get("fee_known"))), p.get("minutes"), int(bool(p.get("indoor"))),
             p.get("opening_hours") or p.get("hours_text") or p.get("hours"), p.get("price"), p.get("score"),
             p.get("source"),
             today, today) for p in places if p.get("id")])


def places_for(city: str, role: str = "sight", max_age_days: int = 180, source_like: str = "%") -> list[dict]:
    since = (date.today() - timedelta(days=max_age_days)).isoformat()
    rows = connect().execute("SELECT * FROM places WHERE city=? AND role=? AND last_seen>=? AND source LIKE ?",
                             (city, role, since, source_like)).fetchall()
    return [dict(r) for r in rows]


def record_picks(thread_id: str, marks: dict) -> None:
    """Remember what this trip's traveller picked; counts feed the ranking of places for later trips."""
    db = connect()
    with _lock:
        old = dict(db.execute("SELECT place_id, mark FROM trip_picks WHERE thread_id=?", (thread_id,)).fetchall())
        for pid, mark in old.items():  # a re-edited selection replaces the previous one
            if mark in ("must", "add", "skip"):
                db.execute(f"UPDATE places SET {mark}_count = MAX(0, {mark}_count - 1) WHERE id=?", (pid,))
        db.execute("DELETE FROM trip_picks WHERE thread_id=?", (thread_id,))
        for pid, mark in marks.items():
            db.execute("INSERT INTO trip_picks VALUES (?,?,?)", (thread_id, pid, mark))
            if mark in ("must", "add", "skip"):
                db.execute(f"UPDATE places SET {mark}_count = {mark}_count + 1 WHERE id=?", (pid,))


def pick_counts(city: str) -> dict:
    rows = connect().execute("SELECT id, must_count, add_count, skip_count FROM places WHERE city=?", (city,))
    return {r["id"]: (r["must_count"], r["add_count"], r["skip_count"]) for r in rows}


# ---------- hotels ----------

def save_hotels(city: str, check_in: date, options: list[dict]) -> None:
    today = _today()
    live = [o for o in options if not o.get("estimate")]
    _write("""INSERT INTO hotels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET lat=excluded.lat, lon=excluded.lon, address=excluded.address,
                rating=excluded.rating, reviews=excluded.reviews, stars=excluded.stars,
                amenities=excluded.amenities, last_seen=excluded.last_seen""",
           [(o["id"], city, o["name"], o.get("kind"), o.get("lat"), o.get("lon"), o.get("address"), o.get("rating"),
             o.get("rating_scale"), o.get("reviews"), o.get("stars"), json.dumps(o.get("amenities") or []),
             o["source"], today) for o in live])
    _write("INSERT OR IGNORE INTO hotel_prices VALUES (?,?,?,?,?,?,?,?,?,?)",
           [(o["id"], city, o["tier"], today, check_in.isoformat(), o["nights"], o["rooms"], o["nightly"],
             o.get("cancellation"), o["source"]) for o in live])


def hotel_price_stats(city: str, tier: str, days: int = 60) -> dict | None:
    """Median nightly room price seen for this city and tier recently, if there are enough prices."""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = connect().execute("SELECT nightly, seen_on FROM hotel_prices WHERE city=? AND tier=? AND seen_on>=?",
                             (city, tier, since)).fetchall()
    if len(rows) < 5:
        return None
    return {"median": int(statistics.median(r["nightly"] for r in rows)), "n": len(rows),
            "since": min(r["seen_on"] for r in rows)}


# ---------- fares ----------

def save_fares(origin: str, dest: str, travel_date: date, options: list[dict]) -> None:
    today = _today()
    _write("INSERT OR IGNORE INTO fares VALUES (?,?,?,?,?,?,?,?,?)",
           [(origin, dest, o["mode"], today, travel_date.isoformat(), o.get("label"),
             "+".join((o.get("out") or {}).get("flights") or []), o["price_pp"], o["source"])
            for o in options if o.get("live")])


def fare_stats(origin: str, dest: str, mode: str, travel_date: date) -> dict | None:
    """Median one-way fare per person seen for this route and mode, for travel in the same month."""
    month = travel_date.strftime("%Y-%m")
    rows = connect().execute("SELECT price_pp FROM fares WHERE origin=? AND destination=? AND mode=? "
                             "AND substr(travel_date,1,7)=?", (origin, dest, mode, month)).fetchall()
    if len(rows) < 5:
        return None
    return {"median": int(statistics.median(r["price_pp"] for r in rows)), "n": len(rows)}


# ---------- routes ----------

def _key(p: tuple) -> tuple:
    return round(p[0], 4), round(p[1], 4)


def get_routes(pairs: list[tuple[tuple, tuple]], max_age_days: int = 90) -> dict:
    """{(a, b): (km, minutes, source)} for the pairs already known."""
    if not pairs:
        return {}
    since = (date.today() - timedelta(days=max_age_days)).isoformat()
    db, out = connect(), {}
    for a, b in pairs:
        r = db.execute("SELECT km, minutes, source FROM routes WHERE a_lat=? AND a_lon=? AND b_lat=? AND b_lon=? "
                       "AND seen_on>=?", (*_key(a), *_key(b), since)).fetchone()
        if r:
            out[(a, b)] = (r["km"], r["minutes"], r["source"])
    return out


def save_routes(rows: list[tuple[tuple, tuple, float, float, str]]) -> None:
    today = _today()
    _write("INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?,?,?)",
           [(*_key(a), *_key(b), km, minutes, source, today) for a, b, km, minutes, source in rows])


# ---------- trips ----------

def save_trip(thread_id: str, state: dict) -> None:
    req, costs = state["request"], state["costs"]
    _write("INSERT OR REPLACE INTO trips VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
           [(thread_id, _today(), req["origin"], req["destination"], req["start_date"], req["end_date"],
             req["travellers"], req["budget_inr"], req.get("priority"), state["stay"]["choice"].get("id"),
             state["transport"]["choice"].get("id"), costs["total"], int(costs["total"] <= costs["budget"]),
             json.dumps(state.get("changes") or []))])


def stats() -> dict:
    db = connect()
    return {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("places", "hotels", "hotel_prices", "fares", "routes", "trips", "trip_picks")}
