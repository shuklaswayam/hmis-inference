"""Redis pub/sub utilities for live push.

Channel naming:
  inf:events          — fan-out for cache_warm + audit_row inserts
  inf:priority_alerts — fired only by the notifier on CRITICAL transitions

Publishers never throw — failures degrade silently because the dashboard
continues to work via the 5-minute polling cadence.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

import redis.asyncio as aioredis

from backend.inference.cache import get_client

logger = logging.getLogger(__name__)

CHANNEL_EVENTS = "inf:events"
CHANNEL_PRIORITY = "inf:priority_alerts"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def publish_event(event: str, payload: Optional[dict[str, Any]] = None) -> int:
    """Publish a fan-out event onto the events channel.

    Returns the subscriber count delivered to (0 means nobody is listening).
    """
    body = {
        "event":     event,
        "emitted_at": _now_iso(),
        "payload":   payload or {},
    }
    try:
        client = get_client()
        return await client.publish(CHANNEL_EVENTS, json.dumps(body, default=str))
    except Exception:  # noqa: BLE001
        logger.debug("publish_event(%s) failed", event, exc_info=True)
        return 0


async def publish_priority_critical(payload: dict[str, Any]) -> int:
    """Used by the CRITICAL notifier — separate channel so subscribers can
    filter to only priority alerts without parsing all events."""
    body = {
        "event":      "priority_critical_transition",
        "emitted_at": _now_iso(),
        "payload":    payload,
    }
    try:
        client = get_client()
        return await client.publish(CHANNEL_PRIORITY, json.dumps(body, default=str))
    except Exception:  # noqa: BLE001
        logger.debug("publish_priority_critical failed", exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Server-Sent Events (SSE) — bridge pub/sub to the browser.
# ---------------------------------------------------------------------------
async def event_stream(
    channels: tuple[str, ...] = (CHANNEL_EVENTS,),
    *,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[dict[str, str]]:
    """Yield SSE-formatted dicts ready for StreamingResponse.

    Each message has at minimum :``event`` (:data) and a periodic comment
    line as a keep-alive so proxies don't kill idle connections.
    """
    client = get_client()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(*channels)
        last_keepalive = asyncio.get_event_loop().time()
        while True:
            now = asyncio.get_event_loop().time()
            if now - last_keepalive > heartbeat_seconds:
                yield {"event": "heartbeat", "data": _now_iso()}
                last_keepalive = now

            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            raw = message.get("data")
            if raw is None:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            yield {"event": "message", "data": raw}
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass
