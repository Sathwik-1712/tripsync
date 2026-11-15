"""Cached HTTP helpers shared by every tool. All responses are cached on disk
so repeated test runs and demos don't hit free-tier rate limits."""
import threading
import time
from datetime import timedelta

import requests_cache

from . import trace
from .config import CACHE_DIR, USER_AGENT, offline


class OfflineError(RuntimeError):
    pass


_session = None
_lock = threading.Lock()
_last_call: dict[str, float] = {}


def session() -> requests_cache.CachedSession:
    global _session
    if _session is None:
        _session = requests_cache.CachedSession(
            str(CACHE_DIR / "http"),
            backend="sqlite",
            expire_after=timedelta(days=1),
            allowable_methods=("GET", "POST"),
            stale_if_error=True,
        )
        _session.headers["User-Agent"] = USER_AGENT
    return _session


def throttle(key: str, min_interval: float) -> None:
    """Enforce a minimum gap between calls to one host (Nominatim: 1 req/sec)."""
    with _lock:
        wait = _last_call.get(key, 0) + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[key] = time.monotonic()


def _what(url: str, params: dict | None) -> str:
    """A short, key-free description of a request for the trace (never API keys)."""
    path = url.split("://", 1)[-1].split("?", 1)[0]
    path = path if len(path) <= 70 else path[:67] + "..."
    shown = {k: v for k, v in (params or {}).items() if "key" not in k.lower() and len(str(v)) < 40}
    return path + (f" ({', '.join(f'{k}={v}' for k, v in list(shown.items())[:4])})" if shown else "")


def get_json(url: str, params: dict | None = None, timeout: float = 20, throttle_key: str | None = None,
             min_interval: float = 1.0, headers: dict | None = None, expire_after: timedelta | None = None):
    if offline():
        raise OfflineError(url)
    if throttle_key:
        throttle(throttle_key, min_interval)
    kw = {"expire_after": expire_after} if expire_after else {}
    with trace.call(trace.service_name(url), _what(url, params)) as info:
        r = session().get(url, params=params, timeout=timeout, headers=headers, **kw)
        info["cached"] = bool(getattr(r, "from_cache", False))
        r.raise_for_status()
        return r.json()


def post_json(url: str, data: dict | None = None, timeout: float = 60, json: dict | None = None,
              headers: dict | None = None, expire_after: timedelta | None = None):
    """Form-encoded `data` (Overpass) or a JSON body (LiteAPI). `expire_after` overrides the 1-day cache."""
    if offline():
        raise OfflineError(url)
    kw = {"expire_after": expire_after} if expire_after else {}
    with trace.call(trace.service_name(url), _what(url, None)) as info:
        r = session().post(url, data=data, json=json, timeout=timeout, headers=headers, **kw)
        info["cached"] = bool(getattr(r, "from_cache", False))
        r.raise_for_status()
        return r.json()
