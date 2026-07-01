"""15-minute Redis read-through/write-around cache for inference outputs.

The premise §6.2 calls for a 15-minute refresh cycle. We expose:

- read_through(loader)  — get-or-set, decodes JSON, returns (hit, value)
- set_around(value)      — write to redis regardless of caller path
- invalidate(key)        — drop a key (audit-only; we don't bulk-invalidate)

The cache layer is read-trough at the endpoint level — endpoints call
``read_through`` once per call. Writes happen on cache-miss AND when the
caller wants to refresh (force_refresh=True).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


# Redis URL — same default as alerts.py. Decode_responses=True so we
# always get strings back (caller JSON-decodes if needed).
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_redis_client: Optional[aioredis.Redis] = None


def get_client() -> aioredis.Redis:
    """Lazy, module-singleton Redis client (avoids event-loop churn).
    Will raise if Redis is unavailable; callers handle via try/except.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            _REDIS_URL, db=0, decode_responses=True
        )
    return _redis_client


def ttl_seconds() -> int:
    """The 15-minute cache TTL called out in §6.2."""
    return int(os.environ.get("INFERENCE_CACHE_TTL_SECONDS", "900"))


def expires_at(now: Optional[datetime] = None) -> datetime:
    return (now or datetime.now(timezone.utc)) + timedelta(seconds=ttl_seconds())


async def read_through(
    cache_key: str,
    loader: Callable[[], Awaitable[dict[str, Any]]],
    *,
    force_refresh: bool = False,
) -> tuple[bool, dict[str, Any]]:
    """Read-through Redis gate.

    Returns (cache_hit, decoded_payload). On miss, runs ``loader``,
    persists the result, returns (False, payload). Cache failures
    degrade silently to a direct loader call so a single Redis outage
    cannot break the dashboard.
    """
    client = get_client()
    if not force_refresh:
        try:
            raw = await client.get(cache_key)
            if raw:
                return True, json.loads(raw)
        except Exception:  # noqa: BLE001
            logger.debug("cache read failed for %s", cache_key, exc_info=True)
    payload = await loader()
    await set_around(cache_key, payload)
    return False, payload


async def set_around(cache_key: str, payload: dict[str, Any]) -> None:
    """Write payload to Redis under cache_key with the configured TTL."""
    client = get_client()
    try:
        await client.setex(cache_key, ttl_seconds(), json.dumps(payload))
    except Exception:  # noqa: BLE001
        logger.debug("cache write failed for %s", cache_key, exc_info=True)


async def invalidate(cache_key: str) -> None:
    try:
        await get_client().delete(cache_key)
    except Exception:  # noqa: BLE001
        logger.debug("cache invalidate failed for %s", cache_key, exc_info=True)


def make_key(workstream: str, params: dict[str, Any], *, version: str = "v1") -> str:
    """Stable Redis key for a workstream call.

    ``params`` is hashed so we don't leak unbounded user-supplied text
    into key names.  ``version`` lets us invalidate stale payloads
    without bouncing Redis (e.g. ``policy_memo`` uses ``v2`` after the
    rich-description enrichment).
    """
    import hashlib

    raw = "&".join(f"{k}={params[k]}" for k in sorted(params))
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"inf:{workstream}:{version}:{h}"
