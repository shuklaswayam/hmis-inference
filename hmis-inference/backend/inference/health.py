"""Decomposed health checks for the inference system.

Phase 5 — production observability:

* DB:     asyncpg ``SELECT 1`` round-trip (best-effort 1 s timeout)
* Redis:  ``PING`` round-trip (best-effort 500 ms timeout)
* Celery beat: read ``inf:celery_beat:last_tick`` from Redis (kept by
            the cache_warmer + check_priority_transition tasks). When
            missing or older than 90 s, we report stale.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from backend.database import Database
from backend.inference.cache import get_client

CELERY_TICK_KEY = "inf:celery_beat:last_tick"


async def _db_ok() -> tuple[bool, float, Optional[str]]:
    try:
        row = await asyncio.wait_for(
            Database.fetchrow("SELECT 1 AS ok"), timeout=1.0
        )
        return (bool(row and row["ok"] == 1), 0.0, None)
    except Exception as exc:  # noqa: BLE001
        return (False, 0.0, str(exc)[:160])


async def _redis_ok() -> tuple[bool, float, Optional[str]]:
    try:
        client = get_client()
        pong = await asyncio.wait_for(client.ping(), timeout=0.5)
        return (bool(pong), 0.0, None)
    except Exception as exc:  # noqa: BLE001
        return (False, 0.0, str(exc)[:160])


async def _beat_age_seconds() -> Optional[float]:
    try:
        client = get_client()
        raw = await client.get(CELERY_TICK_KEY)
        if not raw:
            return None
        return float(raw)
    except Exception:  # noqa: BLE001
        return None


async def check_liveness() -> dict:
    """Run all subsystem health probes and return a structured report."""
    db, redis_probes = await asyncio.gather(
        asyncio.create_task(_db_ok()),
        asyncio.create_task(_redis_ok()),
    )
    beat_age = await _beat_age_seconds()
    beats_stale = beat_age is None or beat_age > 90

    components = {
        "db":        {"ok": db[0],         "error": db[2]},
        "redis":     {"ok": redis_probes[0], "error": redis_probes[2]},
        "celery_beat": {
            "ok":            not beats_stale,
            "last_tick_age_s": beat_age,
            "stale_threshold_s": 90,
        },
    }
    overall_ok = (
        components["db"]["ok"]
        and components["redis"]["ok"]
        and components["celery_beat"]["ok"]
    )
    return {"ok": overall_ok, "components": components}


def beat_tick_key() -> str:
    return CELERY_TICK_KEY


def beat_tick_seconds() -> str:
    """In-process time now — used by celery tasks to mark their ticks."""
    import time
    return str(time.time())
