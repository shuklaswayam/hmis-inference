"""Realtime SSE bridge — exposes Redis pub/sub events to the dashboard.

    GET /api/v1/realtime/events     — fan-out stream (cache warm + audit
                                       inserts + memo regeneration).
    GET /api/v1/realtime/priority   — CRITICAL-transition-only stream.

Both endpoints emit ``text/event-stream`` over Server-Sent Events, which
sit comfortably behind the existing API-key middleware and survive L4
load balancers better than raw WebSocket. The frontend consumes them
through `frontend/src/lib/realtime.ts`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.inference import pubsub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/realtime", tags=["realtime"])


def _sse_response(generator):
    """Format an async iterator of dicts into a StreamingResponse."""
    async def wrapped():
        async for chunk in generator:
            # Each chunk must contain 'event' and 'data' for SSE.
            ev = chunk.get("event", "message")
            data = chunk.get("data", "")
            yield f"event: {ev}\ndata: {data}\n\n"
    return StreamingResponse(
        wrapped(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection":     "keep-alive",
        },
    )


@router.get("/events", summary="SSE stream of inference events")
async def stream_events():
    return _sse_response(
        pubsub.event_stream(channels=(pubsub.CHANNEL_EVENTS, pubsub.CHANNEL_PRIORITY))
    )


@router.get("/priority", summary="SSE stream of CRITICAL transitions only")
async def stream_priority():
    return _sse_response(
        pubsub.event_stream(channels=(pubsub.CHANNEL_PRIORITY,))
    )
