"""WebSocket endpoint for real-time alert streaming via Redis Pub/Sub."""
import asyncio
import json
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CHANNEL = "new_alerts"


@router.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket):
    await websocket.accept()

    pubsub = None
    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)

        # Send initial ping so client knows connection is alive
        await websocket.send_text(json.dumps({"type": "connected"}))

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])

            # Also check if client is still connected
            # Use a short timeout so we don't block forever
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if pubsub:
            try:
                await pubsub.unsubscribe(CHANNEL)
                await pubsub.close()
            except Exception:
                pass
        try:
            await r.aclose()
        except Exception:
            pass
