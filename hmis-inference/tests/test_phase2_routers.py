"""
Integration tests for Phase-2 routers:
  - GET /api/v1/inference/audit
  - GET /api/v1/inference/audit/{trace_id}
  - GET /api/v1/inference/drilldown/facility/{facility_id}
  - GET /api/v1/inference/drilldown/district

Mirrors the existing fastapi_client fixture in conftest.py — every
DB-touching module gets patched at import time.
"""
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(mock_db, mock_redis):
    # Force-import module-level so they exist in sys.modules before we
    # patch the symbol.
    import backend.inference.cache  # noqa
    import backend.inference.store  # noqa
    import backend.routers.audit  # noqa
    import backend.routers.drilldown  # noqa
    import backend.routers.facilities  # noqa
    import backend.routers.metrics  # noqa

    # Only patch modules that *bind* Database as a local symbol.
    # routers.audit and routers.drilldown import via store / direct;
    # patching the inner modules is sufficient.
    router_modules = (
        "backend.main",
        "backend.database",
        "backend.inference.audit",
        "backend.inference.outbreak_risk",
        "backend.inference.hospital_pressure",
        "backend.inference.priority_rank",
        "backend.inference.store",
        "backend.routers.drilldown",   # imports Database directly
        "backend.routers.facilities",
        "backend.routers.metrics",
    )
    with ExitStack() as stack:
        for m in router_modules:
            stack.enter_context(patch(f"{m}.Database", mock_db))
        stack.enter_context(
            patch("backend.inference.cache.get_client", return_value=mock_redis)
        )
        from fastapi.testclient import TestClient
        from backend.main import app
        with patch("backend.database.Database.initialize", AsyncMock()), \
             patch("backend.database.Database.close", AsyncMock()), \
             patch("backend.database.Database.run_migrations", AsyncMock(return_value=[])):
            with TestClient(app) as c:
                yield c


def _audit_row():
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "workstream": "outbreak_risk",
        "trace_id": "11111111-1111-1111-1111-111111111111",
        "district_id": None,
        "facility_id": None,
        "user_id": None,
        "severity": "HIGH",
        "confidence": 0.83,
        "generated_at": datetime(2026, 6, 27, 18, 14, 0),
        "expires_at":  datetime(2026, 6, 27, 18, 29, 0),
        "request":  {"district_id": None},
        "response": {"signals": [], "count": 0},
    }


def test_audit_list_returns_envelope(client, mock_db):
    mock_db.fetch = AsyncMock(return_value=[_audit_row()])
    res = client.get("/api/v1/inference/audit/")
    assert res.status_code == 200
    body = res.json()
    assert body["window"] == "24h"
    assert body["count"] == 1
    assert body["rows"][0]["workstream"] == "outbreak_risk"


def test_audit_list_filters_by_workstream(client, mock_db):
    mock_db.fetch = AsyncMock(return_value=[_audit_row()])
    res = client.get(
        "/api/v1/inference/audit/", params={"workstream": "outbreak_risk"}
    )
    assert res.status_code == 200


def test_audit_detail_returns_404_when_missing(client, mock_db):
    mock_db.fetchrow = AsyncMock(return_value=None)
    res = client.get(
        "/api/v1/inference/audit/22222222-2222-2222-2222-222222222222"
    )
    assert res.status_code == 404


def test_audit_detail_returns_row_when_present(client, mock_db):
    mock_db.fetchrow = AsyncMock(return_value=_audit_row())
    # The audit detail endpoint also calls list_audit_rows — patch both.
    mock_db.fetch = AsyncMock(return_value=[_audit_row()])
    res = client.get(
        "/api/v1/inference/audit/11111111-1111-1111-1111-111111111111"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["row"]["workstream"] == "outbreak_risk"


def test_drilldown_facility_404(client, mock_db):
    mock_db.fetchrow = AsyncMock(return_value=None)
    res = client.get(
        "/api/v1/inference/drilldown/facility/33333333-3333-3333-3333-333333333333"
    )
    assert res.status_code == 404


def test_drilldown_district_requires_disease_param(client, mock_db):
    """Without a ``disease`` query param, the request should fail with
    400 (handler validation) — not propagate to a successful 200."""
    mock_db.fetchrow = AsyncMock(return_value={"id": "55555555-5555-5555-5555-555555555555", "name": "Ahmedabad"})
    res = client.get(
        "/api/v1/inference/drilldown/district",
        params={"district_id": "55555555-5555-5555-5555-555555555555"},
    )
    assert res.status_code == 400


def test_drilldown_district_404_when_district_missing(client, mock_db):
    """A valid UUID that doesn't exist anywhere should 404."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    res = client.get(
        "/api/v1/inference/drilldown/district",
        params={
            "district_id": "55555555-5555-5555-5555-555555555555",
            "disease": "Dengue",
        },
    )
    assert res.status_code == 404
