"""Open-Meteo: forecast for the next 16 days, otherwise last year's observed
weather for the same dates as a climate estimate."""
import logging
from datetime import date, timedelta

from ..http import get_json

log = logging.getLogger(__name__)
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum"


def _shift_year(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def daily_weather(lat: float, lon: float, start: date, end: date) -> list[dict]:
    today = date.today()
    try:
        if end <= today + timedelta(days=15):
            res = get_json("https://api.open-meteo.com/v1/forecast", {
                "latitude": lat, "longitude": lon, "timezone": "auto",
                "daily": DAILY + ",precipitation_probability_max",
                "start_date": start.isoformat(), "end_date": end.isoformat()})
            source, offset = "forecast", 0
        else:
            res = get_json("https://archive-api.open-meteo.com/v1/archive", {
                "latitude": lat, "longitude": lon, "timezone": "auto", "daily": DAILY,
                "start_date": _shift_year(start, -1).isoformat(), "end_date": _shift_year(end, -1).isoformat()})
            source, offset = "last year (climate estimate)", 1
        d = res["daily"]
        out = []
        for i, day in enumerate(d["time"]):
            out.append({
                "date": _shift_year(date.fromisoformat(day), offset).isoformat(),
                "tmax": d["temperature_2m_max"][i],
                "tmin": d["temperature_2m_min"][i],
                "precip_mm": d["precipitation_sum"][i] or 0,
                "precip_prob": (d.get("precipitation_probability_max") or [None] * len(d["time"]))[i],
                "source": source,
            })
        return out
    except Exception as e:  # noqa: BLE001
        log.info("Open-Meteo failed: %s", e)
        return []


def is_rainy(day: dict) -> bool:
    prob = day.get("precip_prob")
    return (prob is not None and prob >= 60) or (day.get("precip_mm") or 0) >= 5
