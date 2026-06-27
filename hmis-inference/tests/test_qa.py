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


class _FakeChunk:
    """Stand-in for backend.rag.retriever.RetrievedChunk with text + source + prefix."""

    def __init__(self, source: str, prefix: str, distance: float = 0.5):
        self.source = source
        self.prefix = prefix
        self.distance = distance


def _attach_rag_returns(mock_rag, chunks):
    """Wire mock RAG to return ``chunks`` and supply a sane mean distance."""
    mock_rag.retrieve.return_value = chunks
    # mean_distance is consumed by ``_confidence_from_chunks`` (qa.py:325)
    # and by the no-answer fallback gate (qa.py:442). Returning a finite
    # number keeps the test on the "happy path" or refusal path depending
    # on what's needed.
    mock_rag.mean_distance.return_value = (
        sum(c.distance for c in chunks) / len(chunks) if chunks else 0.0
    )
    # NO_ANSWER_AVG_DISTANCE is consulted alongside mean_distance. The
    # default in retriever.py is 1.2; any chunks with distance < 1.2
    # land in the happy path. Mock it explicitly so the tests are
    # independent of constant tuning in the source.
    from backend.rag import retriever as _ret
    mock_rag.NO_ANSWER_AVG_DISTANCE = getattr(
        _ret, "NO_ANSWER_AVG_DISTANCE", 1.2
    )


@patch("backend.routers.qa.Database")
@patch("backend.routers.qa.redis_client")
@patch("backend.routers.qa.llm")
@patch("backend.routers.qa.rag")
def test_ask_success(mock_rag, mock_llm, mock_redis, mock_db):
    _attach_rag_returns(
        mock_rag,
        [
            _FakeChunk(
                source="dengue_guidelines.pdf",
                prefix="[dengue_guidelines.pdf]: Dengue outbreak response requires rapid response teams.",
            )
        ],
    )
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
    _attach_rag_returns(
        mock_rag,
        [
            _FakeChunk(
                source="dengue_guidelines.pdf",
                prefix="[dengue_guidelines.pdf]: Dengue guidelines for diagnosis and treatment.",
            )
        ],
    )
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
    """Out-of-corpus question — RAG returns empty so the endpoint short-circuits
    to its refusal branch (lines 432–447 of qa.py) without ever calling the LLM."""
    _attach_rag_returns(mock_rag, [])  # empty retrieval → no-answer path

    mock_redis.get.return_value = None
    mock_redis.setex = MagicMock()

    client = _make_client()
    response = client.post(
        "/api/v1/ask",
        json={"query": "What is the capital of France?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "What is the capital of France?"
    # The new refusal text (qa.py lines 433–438) — the LLM is not invoked.
    assert "I don't have enough information" in data["answer"]
    assert data["refused"] is True
    assert data["confidence"] == "low"


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
