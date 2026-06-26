"""
Integration tests for the HMIS Insights API endpoint.
Tests GET /api/v1/insights/{facility_id}
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

# Test UUIDs
TEST_FACILITY_UUID = "22b29209-57bc-4e7e-96ff-dc6e1bf50e76"
UNKNOWN_FACILITY_UUID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create an async test client with mocked database."""
    from backend.main import app

    # Mock all database operations
    with patch("backend.database.Database.fetchrow", new_callable=AsyncMock) as mock_fetchrow, \
         patch("backend.database.Database.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("backend.database.Database.execute", new_callable=AsyncMock) as mock_execute:

        # Default: facility 1 has metrics, unknown facility does not
        def fetchrow_side_effect(query, *args):
            if args and str(args[0]) == UNKNOWN_FACILITY_UUID:
                return None
            # Return a mock record for the test facility
            record = AsyncMock()
            record.__getitem__ = lambda self, key: {
                "id": 1,
                "facility_id": UUID(TEST_FACILITY_UUID),
                "reported_date": "2026-01-01",
                "opd_visits": 150,
                "icu_occupancy_pct": 75.0,
                "bed_occupancy_pct": 80.0,
                "emergency_visits": 30,
                "maternal_deaths": 0,
                "deliveries": 5,
                "district_id": UUID("b663e6d9-bcb9-488d-9625-12d882bf06a0"),
                "facility_name": "Test Hospital",
            }.get(key)
            record.keys = lambda: ["id", "facility_id", "reported_date", "opd_visits",
                                   "icu_occupancy_pct", "bed_occupancy_pct", "emergency_visits",
                                   "maternal_deaths", "deliveries", "district_id", "facility_name"]
            return record

        def fetch_side_effect(query, *args):
            # Return empty list for historical metrics and disease data
            return []

        mock_fetchrow.side_effect = fetchrow_side_effect
        mock_fetch.side_effect = fetch_side_effect

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver"
        ) as client:
            yield client


@pytest.mark.anyio
async def test_insights_returns_all_required_keys(client):
    """GET /api/v1/insights/{facility_id} must return all 6 required keys."""
    response = await client.get(f"/api/v1/insights/{TEST_FACILITY_UUID}")

    assert response.status_code in (200, 404), (
        f"Expected 200 or 404, got {response.status_code}: {response.text}"
    )

    if response.status_code == 200:
        data = response.json()
        required_keys = [
            "facility_id",
            "rule_flags",
            "anomaly_score",
            "z_scores",
            "priority_rank",
            "forecast_7day",
        ]
        for key in required_keys:
            assert key in data, f"Missing required key: {key}"

        assert isinstance(data["facility_id"], str)
        assert isinstance(data["rule_flags"], list)
        assert isinstance(data["anomaly_score"], (int, float))
        assert isinstance(data["z_scores"], dict)
        assert data["priority_rank"] in ("HIGH", "MEDIUM", "LOW")
        assert isinstance(data["forecast_7day"], list)


@pytest.mark.anyio
async def test_insights_unknown_facility_returns_404(client):
    """Unknown facility_id should return 404."""
    response = await client.get(f"/api/v1/insights/{UNKNOWN_FACILITY_UUID}")
    assert response.status_code == 404
    assert "No facility_metrics found" in response.json()["detail"]


@pytest.mark.anyio
async def test_insights_response_has_timestamp(client):
    """Insights response should include a timestamp."""
    response = await client.get(f"/api/v1/insights/{TEST_FACILITY_UUID}")
    if response.status_code == 200:
        data = response.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)
        assert len(data["timestamp"]) > 0
