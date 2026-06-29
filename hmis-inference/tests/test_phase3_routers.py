"""
Phase-3 router integration tests:
  - GET /api/v1/inference/audit/digest
  - GET /api/v1/realtime/events (SSE)
  - GET /metrics (Prometheus-text)
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
    import backend.inference.cache  # noqa
    import backend.inference.store  # noqa
    import backend.inference.digest  # noqa
    import backend.routers.audit  # noqa
    import backend.routers.drilldown  # noqa
    import backend.routers.realtime  # noqa
    import backend.routers.metrics_route  # noqa
    import backend.routers.facilities  # noqa
    import backend.routers.metrics  # noqa

    router_modules = (
        "backend.main", "backend.database",
        "backend.inference.audit",
        "backend.inference.outbreak_risk",
        "backend.inference.hospital_pressure",
        "backend.inference.priority_rank",
        "backend.inference.store",
        "backend.routers.drilldown",
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


# ---------------------------------------------------------------------------
# Digest endpoint
# ---------------------------------------------------------------------------
def test_digest_markdown_returns_text(client, mock_db):
    """The digest endpoint default format is markdown."""
    mock_db.fetch = AsyncMock(return_value=[])
    res = client.get("/api/v1/inference/audit/digest", params={"window": "7d"})
    assert res.status_code == 200
    assert "text/markdown" in res.headers.get("content-type", "")
    body = res.text
    assert "HMIS Inference Digest" in body
    assert "Rows considered" in body


def test_digest_json_returns_payload(client, mock_db):
    mock_db.fetch = AsyncMock(return_value=[])
    res = client.get("/api/v1/inference/audit/digest", params={"fmt": "json", "window": "24h"})
    assert res.status_code == 200
    body = res.json()
    assert "summary" in body
    assert body["summary"]["window"] == "24h"


def test_digest_rejects_bad_format(client):
    res = client.get("/api/v1/inference/audit/digest", params={"fmt": "xml"})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------
def test_metrics_endpoint_returns_text(client):
    res = client.get("/metrics")
    assert res.status_code == 200
    text = res.text
    assert "inf_calls_total" in text
    assert "inf_cache_total" in text
    assert "inf_alerts_total" in text
    assert "inf_durations_seconds_sum" in text


# ---------------------------------------------------------------------------
# realtime (SSE)
# ---------------------------------------------------------------------------
def test_realtime_events_returns_sse_header(mock_db, mock_redis):
    """The SSE endpoint returns a text/event-stream response.

    We patch the cache's pubsub subscribe path so the generator exits
    cleanly without depending on a live Redis.
    """
    import backend.inference.cache as cache_mod
    import asyncio
    from fastapi.testclient import TestClient
    from backend.main import app

    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = AsyncMock()
    fake_pubsub.aclose = AsyncMock()
    fake_pubsub.unsubscribe = AsyncMock()

    async def _gen():
        yield {"event": "heartbeat", "data": "x"}

    with patch(f"{cache_mod.__name__}.get_client", return_value=mock_redis), \
         patch.object(mock_redis, "pubsub", return_value=fake_pubsub), \
         patch("backend.inference.pubsub.event_stream", return_value=_gen()):
        # The event_stream import in routers/realtime is at module level —
        # we patch the local reference there too.
        with patch("backend.routers.realtime.pubsub.event_stream", return_value=_gen()):
            with patch("backend.database.Database.initialize", AsyncMock()), \
                 patch("backend.database.Database.close", AsyncMock()), \
                 patch("backend.database.Database.run_migrations", AsyncMock(return_value=[])):
                with TestClient(app) as c:
                    with c.stream("GET", "/api/v1/realtime/events") as res:
                        assert res.status_code == 200
                        ct = res.headers.get("content-type", "")
                        assert "text/event-stream" in ct
                        # Read at most one chunk (controller emits heartbeat quickly).
                        chunks = []
                        for chunk in res.iter_text():
                            chunks.append(chunk)
                            if chunks:
                                break


# ---------------------------------------------------------------------------
# Trace id propagation
# ---------------------------------------------------------------------------
def test_trace_id_header_round_trips(client):
    res = client.get("/", headers={"X-Request-Id": "abc-123"})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "abc-123"


def test_trace_id_is_generated_when_missing(client):
    res = client.get("/")
    assert res.status_code == 200
    generated = res.headers.get("x-request-id") or ""
    # Must be a uuid-like string with >8 chars.
    assert len(generated) >= 8
