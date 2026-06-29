"""
Integration tests for the inference router.

Patches Database + Redis at every import site (mirrors conftest) and
hits the FastAPI app through TestClient, exercising the public contract:

    GET /api/v1/inference/outbreak-risk
    GET /api/v1/inference/hospital-pressure
    GET /api/v1/inference/priority-rank
    GET /api/v1/inference/policy-memo
    GET /api/v1/inference/health
"""
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(mock_db, mock_redis):
    router_modules = (
        "backend.main",
        "backend.database",
        "backend.inference.audit",
        "backend.inference.outbreak_risk",
        "backend.inference.hospital_pressure",
        "backend.inference.priority_rank",
        "backend.routers.facilities",
        "backend.routers.forecast",
        "backend.routers.metrics",
        "backend.routers.districts",
        "backend.routers.ingest",
    )
    with ExitStack() as stack:
        for m in router_modules:
            stack.enter_context(patch(f"{m}.Database", mock_db))
        stack.enter_context(
            patch("backend.inference.cache.get_client", return_value=mock_redis)
        )
        from fastapi.testclient import TestClient
        from backend.main import app

        # Force a benign startup without DB.
        with patch("backend.database.Database.initialize", AsyncMock()), \
             patch("backend.database.Database.close", AsyncMock()), \
             patch("backend.database.Database.run_migrations", AsyncMock(return_value=[])):
            with TestClient(app) as c:
                yield c


def test_inference_health_endpoint_is_public(client):
    res = client.get("/api/v1/inference/health")
    assert res.status_code == 200
    body = res.json()
    assert "outbreak_risk" in body["workstreams"]
    assert body["cache_ttl_seconds"] == 900


def test_outbreak_risk_endpoint_shape(client):
    res = client.get("/api/v1/inference/outbreak-risk")
    assert res.status_code == 200
    body = res.json()
    assert body["workstream"] == "outbreak_risk"
    assert "data" in body
    assert "generated_at" in body
    assert "expires_at" in body
    assert body["severity"] in (None, "LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_hospital_pressure_endpoint_shape(client):
    res = client.get("/api/v1/inference/hospital-pressure")
    assert res.status_code == 200
    body = res.json()
    assert body["workstream"] == "hospital_pressure"
    assert "data" in body


def test_priority_rank_endpoint_shape(client):
    res = client.get("/api/v1/inference/priority-rank")
    assert res.status_code == 200
    body = res.json()
    assert body["workstream"] == "priority_rank"
    assert "data" in body


def test_policy_memo_endpoint_shape(client):
    res = client.get("/api/v1/inference/policy-memo")
    assert res.status_code == 200
    body = res.json()
    assert body["workstream"] == "policy_memo"
    assert "headline" in body["data"]
    assert "body_md" in body["data"]
    assert "recommended_actions" in body["data"]


def test_force_refresh_bypasses_cache(client, mock_redis):
    mock_redis.get = AsyncMock(return_value='{"sentinel":"cached"}')
    res = client.get("/api/v1/inference/outbreak-risk?force_refresh=true")
    assert res.status_code == 200
    # On force_refresh, the loader runs again — cached value must NOT be in
    # the body. The mocked DB returns empty lists, so the body has 0 signals.
    body = res.json()
    # Ensure force_refresh path didn't return the sentinel
    assert body.get("data", {}).get("signals") == []


def test_inference_router_writes_audit_row(client, mock_db):
    """A successful call should write a row through backend.inference.audit."""
    res = client.get("/api/v1/inference/hospital-pressure")
    assert res.status_code == 200
    # mock_db.execute is called once for the audit insert.
    assert mock_db.execute.await_count >= 1


def test_root_endpoint_returns_ok(client):
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "hmis-inference"


def test_health_endpoint_lists_workstreams(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "outbreak_risk" in body["inference_workstreams"]
    assert "hospital_pressure" in body["inference_workstreams"]
    assert "priority_rank" in body["inference_workstreams"]
    assert "policy_memo" in body["inference_workstreams"]
