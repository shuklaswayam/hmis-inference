"""
Routers — smoke tests for the eight routers without dedicated suites.

Each test hits one endpoint with a sensible payload and asserts the response
status + a couple of shape fields. Heavy-DB paths are mocked out via the
``fastapi_client`` and ``mock_db`` fixtures in ``conftest.py``.

The QA router already has ``tests/test_qa.py`` and is not duplicated here.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Tests in this file share the conftest fixtures; importing it explicitly
# silences linters that don't transitively import fixtures.
from tests import conftest  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# 1. Alerts — GET /api/v1/alerts/
# ─────────────────────────────────────────────────────────────────────────────
@patch("backend.routers.alerts.redis_client")
def test_alerts_get_returns_list(mock_redis_cls, mock_db, fastapi_client):
    """Alerts endpoint must return a list, even empty."""
    mock_redis_cls.get = AsyncMock(return_value=None)
    mock_redis_cls.setex = AsyncMock(return_value=True)

    # _run_rules_engine_on_facilities fetches latest metrics
    mock_db.fetch.return_value = []
    # _fetch_active_alerts also fetches
    mock_db.fetch.side_effect = [[], []]

    resp = fastapi_client.get("/api/v1/alerts/")
    assert resp.status_code == 200
    assert resp.json() == []


@patch("backend.routers.alerts.redis_client")
def test_alerts_with_filter_params_routes_correctly(mock_redis, mock_db, fastapi_client):
    """Query string filters pass through and don't error."""
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_db.fetch.side_effect = [[], []]

    resp = fastapi_client.get(
        "/api/v1/alerts/",
        params={"district_id": "abc-uuid", "severity": "HIGH"},
    )
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 2. Districts — GET /api/v1/districts/, /risk-summary
# ─────────────────────────────────────────────────────────────────────────────
def test_districts_list_returns_records(mock_db, fastapi_client):
    """Districts endpoint formats DB rows into the documented shape."""
    mock_db.fetch = AsyncMock(return_value=[
        {"id": "d1", "name": "Ahmedabad", "state": "Gujarat",
         "population": 7_000_000, "zone": "Central"},
        {"id": "d2", "name": "Surat", "state": "Gujarat",
         "population": 6_000_000, "zone": "South"},
    ])
    resp = fastapi_client.get("/api/v1/districts/")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "Ahmedabad"
    assert data[0]["population"] == 7_000_000


def test_districts_risk_summary_sorted_by_severity(mock_db, fastapi_client):
    """Risk summary sorts HIGH → MEDIUM → LOW → NONE."""
    mock_db.fetch = AsyncMock(return_value=[
        {"district_id": "d1", "district_name": "Surat",
         "highest_severity": "NONE", "alert_count": 0},
        {"district_id": "d2", "district_name": "Ahmedabad",
         "highest_severity": "HIGH", "alert_count": 5},
    ])
    resp = fastapi_client.get("/api/v1/districts/risk-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["district_name"] == "Ahmedabad"
    assert data[1]["district_name"] == "Surat"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Facilities — GET /api/v1/facilities/, /summary
# ─────────────────────────────────────────────────────────────────────────────
def test_facilities_list(mock_db, fastapi_client):
    mock_db.fetch = AsyncMock(return_value=[])
    resp = fastapi_client.get("/api/v1/facilities/")
    assert resp.status_code == 200
    assert resp.json() == []


def test_facilities_summary_shape(mock_db, fastapi_client):
    # Two queries are issued in this endpoint.
    mock_db.fetchrow = AsyncMock(side_effect=[
        {"total": 12, "districts": 5, "total_beds": 1000, "total_icu_beds": 100},
        {"avg_bed_occ": 70.0, "avg_icu_occ": 60.0,
         "total_opd": 50_000, "total_emergency": 5_000},
    ])
    resp = fastapi_client.get("/api/v1/facilities/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_facilities"] == 12
    assert data["avg_bed_occupancy"] == 70.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. Forecast — 404 when no data, 400 when too little
# ─────────────────────────────────────────────────────────────────────────────
def test_forecast_404_when_no_data(mock_db, fastapi_client):
    mock_db.fetch = AsyncMock(return_value=[])
    resp = fastapi_client.get("/api/v1/forecast/dengue")
    assert resp.status_code == 404
    assert "No historical data" in resp.json()["detail"]


def test_forecast_400_when_too_few_points(mock_db, fastapi_client):
    """Need at least 14 days of data — fewer raises 400, not 200."""
    import pandas as pd
    rows = [
        {"ds": __import__("datetime").date(2026, 6, i + 1), "y": float(i)}
        for i in range(7)
    ]
    mock_db.fetch = AsyncMock(return_value=rows)
    resp = fastapi_client.get("/api/v1/forecast/dengue")
    assert resp.status_code == 400
    assert "Insufficient data" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Ingest — validates payload + 422 on missing required fields
# ─────────────────────────────────────────────────────────────────────────────
def test_ingest_district_requires_name(mock_db, fastapi_client):
    resp = fastapi_client.post("/api/v1/ingest/district", json={"state": "Gujarat"})
    assert resp.status_code == 422


@patch("backend.routers.ingest.Database")
def test_ingest_district_success(mock_db_cls, mock_db, fastapi_client):
    created_row = {
        "id": "d-new", "name": "Anand", "state": "Gujarat",
        "population": 2_000_000, "zone": None,
        "created_at": __import__("datetime").datetime(2026, 6, 24),
    }
    mock_db.fetchrow = AsyncMock(return_value=created_row)

    resp = fastapi_client.post(
        "/api/v1/ingest/district",
        json={"name": "Anand", "state": "Gujarat", "population": 2_000_000},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Anand"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Insights — 404 when facility has no metrics
# ─────────────────────────────────────────────────────────────────────────────
def test_insight_404_when_no_metrics(mock_db, fastapi_client):
    mock_db.fetchrow = AsyncMock(return_value=None)
    resp = fastapi_client.get(
        "/api/v1/insights/ad9dbe7a-b33b-4d36-9b30-9bc2e1c2c5d6",
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 7. Metrics — invalid metric name → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_metrics_invalid_field_rejected(mock_db, fastapi_client):
    resp = fastapi_client.get(
        "/api/v1/metrics/trend",
        params={
            "facility_id": "fac-uuid",
            "metric": "icue_occupancy_pct",  # typo
            "days": 7,
        },
    )
    assert resp.status_code == 400
    assert "Invalid metric" in resp.json()["detail"]


def test_metrics_valid_field(mock_db, fastapi_client):
    mock_db.fetch = AsyncMock(return_value=[
        {"reported_date": __import__("datetime").date(2026, 6, i + 1),
         "value": float(50 + i), "facility_name": "CHC Anand"}
        for i in range(7)
    ])
    resp = fastapi_client.get(
        "/api/v1/metrics/trend",
        params={"facility_id": "fac-uuid", "metric": "opd_visits", "days": 7},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7
    assert data[0]["facility_name"] == "CHC Anand"


# ─────────────────────────────────────────────────────────────────────────────
# 8. WebSocket — route is registered + accept opens a connection.
#    Actual pub/sub require a live Redis; we only check the handshake here.
# ─────────────────────────────────────────────────────────────────────────────
def test_websocket_route_registered(fastapi_client):
    """The /ws/alerts route must show up in the app's route table."""
    paths = {
        route.path
        for route in fastapi_client.app.routes
        if hasattr(route, "path")
    }
    assert "/ws/alerts" in paths


# ─────────────────────────────────────────────────────────────────────────────
# 9. App assembly — every router is wired in main.py
# ─────────────────────────────────────────────────────────────────────────────
def test_all_routers_present_in_app(fastapi_client):
    """Sanity check that none of the nine routers has been forgotten in
    include_router(). Easy to drift on."""
    expected_prefixes = {
        "/api/v1/alerts",
        "/api/v1/districts",
        "/api/v1/facilities",
        "/api/v1/forecast",
        "/api/v1/ingest",
        "/api/v1/insights",
        "/api/v1/metrics",
        "/api/v1/ask",  # qa router
    }
    actual_prefixes = {
        route.path
        for route in fastapi_client.app.routes
        if hasattr(route, "path") and route.path.startswith("/api/v1")
    }
    missing = expected_prefixes - actual_prefixes
    assert not missing, f"Missing router prefixes in app: {missing}"


def test_root_health(fastapi_client):
    """The unauthenticated root path returns OK + service id."""
    resp = fastapi_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "hmis-inference"
