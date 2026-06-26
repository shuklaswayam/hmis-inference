"""Integration tests for /api/v1/ask endpoint."""
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_client():
    """Build a TestClient with database + redis mocked out.

    Mirrors tests/conftest.py::fastapi_client — patch every router module
    that imports ``Database`` or ``redis_client`` because ``from backend.X
    import Y`` captures the symbol at import time and won't reflect a
    single-module patch.
    """
    from contextlib import ExitStack

    with ExitStack() as stack:
        for module in (
            "backend.main",
            "backend.database",
            "backend.routers.alerts",
            "backend.routers.qa",
        ):
            stack.enter_context(patch(f"{module}.Database"))
        stack.enter_context(patch("backend.routers.alerts.redis_client"))
        stack.enter_context(patch("backend.routers.qa.redis_client"))
        from backend.main import app
        return TestClient(app)


def _cache_key(query: str, district_id: str | None) -> str:
    raw = f"{query}:{district_id}"
    return f"qa:{hashlib.sha256(raw.encode()).hexdigest()}"


@patch("backend.routers.qa.Database")
@patch("backend.routers.qa.redis_client")
@patch("backend.routers.qa.llm")
@patch("backend.routers.qa.rag")
def test_ask_success(mock_rag, mock_llm, mock_redis, mock_db):
    mock_rag.retrieve.return_value = [
        "[dengue_guidelines.pdf]: Dengue outbreak response requires rapid response teams.",
    ]
    mock_llm.synthesize.return_value = {
        "what_is_happening": "High OPD visits suggest seasonal surge.",
        "why_it_happening": "Monsoon season increases vector-borne diseases.",
        "recommended_action": "Deploy additional staff and extend OPD hours.",
    }
    mock_redis.get.return_value = None
    mock_redis.setex = MagicMock()
    mock_db.fetch = AsyncMock(return_value=[
        {"district_name": "Surat", "state": "Gujarat", "population": 5000000,
         "facility_count": 50, "total_opd": 10000, "total_emergency": 500,
         "total_maternal_deaths": 3, "total_deliveries": 200,
         "avg_bed_occupancy": 75.0, "avg_icu_occupancy": 80.0}
    ])

    client = _make_client()
    response = client.post(
        "/api/v1/ask",
        json={"query": "Why are OPD visits high in Surat?", "district_id": "cadc66f3-2937-4015-84d8-4b51981e696e"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Why are OPD visits high in Surat?"
    assert data["district_id"] == "cadc66f3-2937-4015-84d8-4b51981e696e"
    assert "answer" in data
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) >= 1
    assert "timestamp" in data


@patch("backend.routers.qa.redis_client")
@patch("backend.routers.qa.llm")
@patch("backend.routers.qa.rag")
def test_ask_no_district(mock_rag, mock_llm, mock_redis):
    mock_rag.retrieve.return_value = [
        "[dengue_guidelines.pdf]: Dengue guidelines for diagnosis and treatment.",
    ]
    mock_llm.synthesize.return_value = {
        "what_is_happening": "Dengue guidelines cover diagnosis, treatment, and prevention.",
        "why_it_happening": "WHO recommends early detection.",
        "recommended_action": "Follow WHO dengue management protocols.",
    }
    mock_redis.get.return_value = None
    mock_redis.setex = MagicMock()

    client = _make_client()
    response = client.post(
        "/api/v1/ask",
        json={"query": "What are the dengue guidelines?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "What are the dengue guidelines?"
    assert data["district_id"] is None
    assert "answer" in data
    assert "sources" in data


@patch("backend.routers.qa.redis_client")
@patch("backend.routers.qa.Database")
@patch("backend.routers.qa.llm")
@patch("backend.routers.qa.rag")
def test_ask_irrelevant_query(mock_rag, mock_llm, mock_db_qa, mock_redis):
    """Out-of-corpus question — RAG returns nothing, no DB analytics needed."""
    mock_rag.retrieve.return_value = []
    mock_llm.synthesize.return_value = {
        "what_is_happening": "I don't have relevant health policy data to answer this question.",
        "why_it_happening": "The policy documents only cover Indian public health topics.",
        "recommended_action": "Please ask about dengue, malaria, maternal health, or immunization.",
    }
    mock_redis.get.return_value = None
    mock_redis.setex = MagicMock()
    # The ask endpoint calls _fetch_recent_alerts() unconditionally — mock it
    # out so the test doesn't fall through to a real Postgres call (the
    # previous decorator-based mock set only papered over llm/rag/redis).
    mock_db_qa.fetch = AsyncMock(return_value=[])

    client = _make_client()
    response = client.post(
        "/api/v1/ask",
        json={"query": "What is the capital of France?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "What is the capital of France?"
    assert "I don't have relevant health policy data" in data["answer"]


@patch("backend.routers.qa.redis_client")
@patch("backend.routers.qa.llm")
@patch("backend.routers.qa.rag")
def test_ask_uses_cache(mock_rag, mock_llm, mock_redis):
    cached = {
        "question": "Cached question?",
        "answer": "Cached answer.",
        "sources": ["cached.pdf"],
        "district_id": None,
        "timestamp": "2026-01-01T00:00:00",
    }
    mock_redis.get.return_value = json.dumps(cached)

    client = _make_client()
    response = client.post(
        "/api/v1/ask",
        json={"query": "Cached question?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Cached answer."
    mock_rag.retrieve.assert_not_called()
    mock_llm.synthesize.assert_not_called()
