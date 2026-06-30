"""
WebSocket endpoint tests.

``/ws/alerts`` streams alert payloads via Redis pub/sub. Tests cover what's
realistic without spinning up a live Redis:

    * the route is registered on the app under the expected path
    * connecting opens a handshake and immediately receives the ``connected``
      bootstrap frame (so clients can confirm a live channel before relying
      on it)
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_websocket_route_is_registered_on_app():
    """``/ws/alerts`` must be on the FastAPI app — missing this is a
    regression on router.include_router()."""
    from backend.main import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/ws/alerts" in paths


def test_websocket_route_is_websocket_upgrade():
    """Sanity: the registered route actually accepts the WebSocket protocol.

    FastAPI exposes WebSocket routes as ``APIWebSocketRoute`` instances —
    they carry a ``path`` and ``path_format`` but **no** ``methods`` attribute
    (HTTP-only routes are the ones that record methods).  So detect by class
    name + path, not by ``route.methods``.
    """
    from fastapi.routing import APIWebSocketRoute

    from backend.main import app

    ws_routes = [
        route for route in app.routes
        if isinstance(route, APIWebSocketRoute) and route.path == "/ws/alerts"
    ]
    assert ws_routes, "Expected at least one APIWebSocketRoute at /ws/alerts"
    # Path-format and class sanity so a future refactor that swaps the WS
    # implementation for an HTTP-route gets a clear failure.
    assert ws_routes[0].path == "/ws/alerts"
    assert ws_routes[0].path_format == ws_routes[0].path


@patch("backend._legacy.websocket.aioredis")
def test_websocket_handshake_emits_connected_frame(mock_aioredis):
    """Connecting to /ws/alerts immediately sends ``{"type": "connected"}`` —
    clients rely on this to detect a failed channel before any alert lands."""
    from fastapi.testclient import TestClient

    # Mock the async Redis client + pubsub so the subscription call succeeds.
    fake_r = MagicMock()
    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = AsyncMock(return_value=None)

    # get_message must yield forever (no messages → loop continues). Raise on
    # second call to gracefully exit the loop after the handshake.
    call = {"n": 0}

    async def fake_get_message(*args, **kwargs):
        if call["n"] > 0:
            raise ConnectionResetError("test done")
        call["n"] += 1
        return None

    fake_pubsub.get_message = fake_get_message
    fake_r.pubsub = MagicMock(return_value=fake_pubsub)
    fake_r.aclose = AsyncMock(return_value=None)
    fake_pubsub.unsubscribe = AsyncMock(return_value=None)
    fake_pubsub.close = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = fake_r

    with patch("backend.main.Database"):
        from backend.main import app
        client = TestClient(app)

        with client.websocket_connect("/ws/alerts") as ws:
            first = ws.receive_text()
            data = json.loads(first)
            assert data["type"] == "connected"


@patch("backend._legacy.websocket.aioredis")
def test_websocket_publishes_alert_payload(mock_aioredis):
    """If a message lands on the channel, the ws broadcasts it verbatim."""
    from fastapi.testclient import TestClient

    payload = json.dumps({"type": "new_alert", "alert": {
        "id": "abc", "facility_name": "CHC Anand", "severity": "HIGH",
    }})

    fake_r = MagicMock()
    fake_pubsub = MagicMock()
    fake_pubsub.subscribe = AsyncMock(return_value=None)

    sent_message = {"value": None}

    async def fake_get_message(*a, **kw):
        if sent_message["value"] is None:
            # First call — return the alert payload; subsequent calls yield
            # busy loop until sent_message is consumed by the test.
            sent_message["value"] = payload
            return {"type": "message", "data": payload}
        return None

    fake_pubsub.get_message = fake_get_message
    fake_r.pubsub = MagicMock(return_value=fake_pubsub)
    fake_r.aclose = AsyncMock(return_value=None)
    fake_pubsub.unsubscribe = AsyncMock(return_value=None)
    fake_pubsub.close = AsyncMock(return_value=None)
    mock_aioredis.from_url.return_value = fake_r

    with patch("backend.main.Database"):
        from backend.main import app
        client = TestClient(app)

        with client.websocket_connect("/ws/alerts") as ws:
            ws.receive_text()  # drain "connected"
            forwarded = ws.receive_text()
            assert json.loads(forwarded)["type"] == "new_alert"
