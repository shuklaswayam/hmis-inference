"""
Shared pytest fixtures for the HMIS Inference backend test suite.

The backend talks to Postgres via asyncpg + Redis. Pure-Python modules
(ml/, rag/, llm/, schemas/, rules_engine) can be imported directly; modules
that touch ``Database``, redis, or LLM clients get patched in their own tests.
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make ``backend.*`` importable the same way the running app does.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Pytest sets this automatically; importing backend later can short-circuit on it.
os.environ.setdefault("DATABASE_URL", "postgresql://hmis:hmis_password@localhost:5432/hmis")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


# ─────────────────────────────────────────────────────────────────────────────
# Event loop fixture — any async test asks for ``event_loop`` and gets one
# scoped to the function so asyncpg pool teardown doesn't leak between tests.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic model factories — kept tiny, used in schemas + tests/routers tests.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def make_district_create():
    def _make(**overrides):
        payload = {
            "name": "Anand",
            "state": "Gujarat",
            "population": 2_000_000,
            "zone": "Central",
        }
        payload.update(overrides)
        return payload
    return _make


@pytest.fixture
def make_facility_create(make_district_create):
    def _make(**overrides):
        payload = {
            "district_id": str(uuid.uuid4()),
            "name": "Civil Hospital Anand",
            "facility_type": "District Hospital",
            "beds_total": 100,
            "icu_beds": 10,
            "latitude": 22.5535,
            "longitude": 72.9345,
        }
        payload.update(overrides)
        return payload
    return _make


@pytest.fixture
def make_facility_metrics_create(make_facility_create):
    def _make(**overrides):
        payload = {
            **make_facility_create(),
            "reported_date": "2026-06-24",
            "opd_visits": 240,
            "icu_occupancy_pct": 72.0,
            "bed_occupancy_pct": 80.0,
            "emergency_visits": 45,
            "maternal_deaths": 0,
            "deliveries": 12,
        }
        # Pydantic district_id is the only field from make_facility_create
        # that FacilityMetricsCreate doesn't take.
        payload.pop("name", None)
        payload.pop("facility_type", None)
        payload.pop("beds_total", None)
        payload.pop("icu_beds", None)
        payload.pop("latitude", None)
        payload.pop("longitude", None)
        payload.update(overrides)
        return payload
    return _make


# ─────────────────────────────────────────────────────────────────────────────
# Async-DB + Redis mongos — most routers call ``Database.fetch`` somehow.
# Patching saves us from standing up real Postgres in the suite.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def mock_db():
    """Patch backend.database.Database to return canned async mocks."""
    db = MagicMock()
    db.initialize = AsyncMock()
    db.close = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    db.fetchrow = AsyncMock(return_value=None)
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value="")
    return db


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock(return_value=True)
    r.publish = AsyncMock(return_value=1)
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Test app factory — builds a TestClient with backend.main.Database patched
# so import-time side-effects don't hit Postgres. Mirrors test_qa.py.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fastapi_client(mock_db, mock_redis):
    from unittest.mock import patch

    with patch("backend.main.Database", mock_db):
        with patch("backend.routers.alerts.redis_client", mock_redis):
            with patch("backend.routers.qa.redis_client", mock_redis):
                from fastapi.testclient import TestClient
                from backend.main import app
                yield TestClient(app)
