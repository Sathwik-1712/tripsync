import os
import sys
from pathlib import Path

os.environ["TRIPSYNC_OFFLINE"] = "1"  # no network, no LLM: deterministic tests
os.environ["TRIPSYNC_DB"] = ":memory:"  # a fresh, throwaway travel database per test run
os.environ["LANGSMITH_TRACING"] = os.environ["LANGCHAIN_TRACING_V2"] = "false"  # don't upload test runs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    """Every test starts with an empty in-memory travel database."""
    from tripsync import db
    db.reset()
    yield
    db.reset()
