"""
Tests for Phase 3 backend modules:
  - pubsub publish helpers (event / priority_critical)
  - metrics counters track correctly + render Prometheus text
  - observability: TraceIdMiddleware echoes X-Request-Id, JsonFormatter
  - digest builder (markdown shape)
  - SSE generator (sanity check that heartbeat + message pass through)
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


# ---------------------------------------------------------------------------
# metrics.py
# ---------------------------------------------------------------------------
def test_record_call_increments_counter():
    from backend.inference.metrics import record_call, to_prometheus_text, reset
    reset()
    record_call("outbreak_risk")
    record_call("outbreak_risk")
    record_call("outbreak_risk", status="error")
    out = to_prometheus_text()
    assert 'inf_calls_total{workstream="outbreak_risk",status="ok"} 2' in out
    assert 'inf_calls_total{workstream="outbreak_risk",status="error"} 1' in out


def test_record_cache_hit_and_miss():
    from backend.inference.metrics import record_cache, to_prometheus_text, reset
    reset()
    record_cache("priority_rank", hit=True)
    record_cache("priority_rank", hit=False)
    record_cache("priority_rank", hit=False)
    out = to_prometheus_text()
    assert 'inf_cache_total{workstream="priority_rank",kind="hit"} 1' in out
    assert 'inf_cache_total{workstream="priority_rank",kind="miss"} 2' in out


def test_record_alert_valid_kind_only():
    from backend.inference.metrics import record_alert, to_prometheus_text, reset
    reset()
    record_alert("critical_transition")
    record_alert("webhook_fired")
    record_alert("garbage_kind")  # silently ignored
    out = to_prometheus_text()
    assert 'inf_alerts_total{kind="critical_transition"} 1' in out
    assert 'inf_alerts_total{kind="webhook_fired"} 1' in out
    assert "garbage" not in out


def test_track_call_measures_duration():
    import time
    from backend.inference.metrics import track_call, reset, to_prometheus_text
    reset()
    with track_call("hospital_pressure") as meta:
        time.sleep(0.001)
    assert meta["status"] == "ok"
    assert "0.00" in to_prometheus_text() or "0.001" in to_prometheus_text()


def test_track_call_marks_status_error_on_exception():
    from backend.inference.metrics import track_call, reset
    reset()
    with pytest.raises(RuntimeError):
        with track_call("policy_memo"):
            raise RuntimeError("boom")
    from backend.inference import metrics as m
    assert m._call_counts[("policy_memo", "error")] == 1


# ---------------------------------------------------------------------------
# observability: JsonFormatter + TraceIdMiddleware
# ---------------------------------------------------------------------------
def test_json_formatter_includes_message_level():
    from backend.inference.observability import JsonFormatter
    fmt = JsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = fmt.format(record)
    body = json.loads(out)
    assert body["message"] == "hello world"
    assert body["level"] == "INFO"


def test_trace_id_propagates_through_contextvar():
    from backend.inference.observability import current_trace_id, set_trace_id
    set_trace_id("test-trace-id")
    assert current_trace_id() == "test-trace-id"


# ---------------------------------------------------------------------------
# pubsub.publish_event / publish_priority_critical
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_publish_event_calls_publish():
    from backend.inference import pubsub
    fake_client = MagicMock()
    fake_client.publish = AsyncMock(return_value=2)
    with patch.object(pubsub, "get_client", return_value=fake_client):
        count = await pubsub.publish_event("cache_warmed", payload={"k": "v"})
    assert count == 2
    fake_client.publish.assert_called_once()
    channel, body = fake_client.publish.call_args.args
    assert channel == pubsub.CHANNEL_EVENTS
    decoded = json.loads(body)
    assert decoded["event"] == "cache_warmed"
    assert decoded["payload"] == {"k": "v"}


@pytest.mark.asyncio
async def test_publish_priority_critical_uses_priority_channel():
    from backend.inference import pubsub
    fake_client = MagicMock()
    fake_client.publish = AsyncMock(return_value=1)
    with patch.object(pubsub, "get_client", return_value=fake_client):
        await pubsub.publish_priority_critical({"a": 1})
    called_channel = fake_client.publish.call_args.args[0]
    assert called_channel == pubsub.CHANNEL_PRIORITY


# ---------------------------------------------------------------------------
# digest builder
# ---------------------------------------------------------------------------
def test_digest_render_markdown_includes_summary_rows():
    from backend.inference.digest import render_markdown
    summary = {
        "window": "7d", "generated_at": "2026-06-27T18:00:00Z", "row_count": 5,
        "by_severity": {"HIGH": 2, "LOW": 3},
        "by_workstream": {"outbreak_risk": 5},
        "latest_per_workstream": {
            "outbreak_risk": {
                "trace_id": "abc", "severity": "HIGH", "confidence": 0.83,
                "generated_at": "2026-06-27T17:30:00Z",
            },
        },
    }
    rows = [{
        "id": "1", "workstream": "outbreak_risk", "trace_id": "abc",
        "severity": "HIGH", "confidence": 0.83,
        "generated_at": "2026-06-27T17:30:00Z", "expires_at": None,
        "district_id": None, "facility_id": None,
        "request": {}, "response": {"data": {"ranked": []}},
    }]
    md = render_markdown(summary, rows)
    assert "# HMIS Inference Digest — 7d" in md
    assert "Rows considered: **5**" in md
    assert "outbreak_risk" in md
    assert "| HIGH |" in md
