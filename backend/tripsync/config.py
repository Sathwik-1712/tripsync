import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CHECKPOINT_DB = CACHE_DIR / "checkpoints.sqlite"

# OSM services ask for an identifying User-Agent with a contact. Overpass rejects (406) the
# untouched placeholder from .env.example, so that counts as unset.
_ua = os.getenv("TRIPSYNC_USER_AGENT") or ""
USER_AGENT = _ua if _ua and "example.com" not in _ua else "TripSync-student-project/0.1"

# Critic -> replanning rounds before we stop and ask the user.
MAX_ROUNDS = 3
MAX_TRIP_DAYS = 14

# Share of the budget held back as a safety buffer (Budget Agent).
BUFFER_SHARE = 0.10


def offline() -> bool:
    """Read on every call so tests can flip it with monkeypatch."""
    return os.getenv("TRIPSYNC_OFFLINE") == "1"
