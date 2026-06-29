"""Cache warmer — keeps the 4 workstream cache keys hot.

Called from Celery beat every ``warm_interval_seconds`` (default 840s =
14 minutes, just under the 15-min TTL). We invoke the workstream score
functions directly and write the response-shaped envelope into Redis,
so the first public request after expiry never sees a slow path.

Failures are silently logged — a missed tick is recoverable; the next
public request will still recompute on cache miss.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Awaitable, Callable

from backend.inference import (
    cache as inference_cache,
    hospital_pressure,
    outbreak_risk,
    policy_memo,
    priority_rank,
)

logger = logging.getLogger(__name__)


WARM_INTERVAL_SECONDS = int(os.environ.get("INFERENCE_WARM_INTERVAL_SECONDS", "840"))


async def warm_all() -> dict:
    """Recompute and refresh cache for all 4 workstreams."""
    now = datetime.now(timezone.utc)
    results: dict[str, dict] = {}

    async def _run(name: str, params: dict, score_fn: Callable[..., Awaitable]):
        key = inference_cache.make_key(name, params)
        try:
            if name == "outbreak_risk":
                signals = await score_fn()
            elif name == "hospital_pressure":
                signals = await score_fn()
            elif name == "priority_rank":
                ob = await outbreak_risk.score()
                pr = await hospital_pressure.score()
                signals = await score_fn(outbreak_signals=ob, pressure_signals=pr)
            elif name == "policy_memo":
                ob = await outbreak_risk.score()
                pr = await hospital_pressure.score()
                rk = await priority_rank.rank(outbreak_signals=ob, pressure_signals=pr)
                signals = await score_fn(
                    outbreak_signals=ob, pressure_signals=pr, ranked=rk
                )
            else:
                return
            envelope = {
                "workstream": name,
                "data": signals if isinstance(signals, dict) else {"signals": signals},
                "generated_at": now.isoformat(),
                "expires_at":   inference_cache.expires_at(now).isoformat(),
            }
            await inference_cache.set_around(key, envelope)
            results[name] = {"ok": True, "key": key}
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache warmer failed for %s: %s", name, exc)
            results[name] = {"ok": False, "error": str(exc)}

    await asyncio.gather(
        _run("outbreak_risk",  {"d": "ALL", "dz": "ALL"}, lambda: outbreak_risk.score()),
        _run("hospital_pressure", {"d": "ALL", "f": "ALL"}, lambda: hospital_pressure.score()),
        _run("priority_rank",  {"d": "ALL"}, priority_rank.rank),
        _run("policy_memo",    {"d": "ALL"}, policy_memo.compose),
    )

    # Phase 3: live push — announce that the cache is hot so subscribers
    # can refetch immediately instead of waiting for their 5-min cadence.
    try:
        from backend.inference.pubsub import publish_event
        await publish_event("cache_warmed", {"workstreams": list(results.keys())})
    except Exception:  # noqa: BLE001
        logger.debug("publish_event(cache_warmed) failed")

    return {"now": now.isoformat(), "results": results}


def warm_sync_for_celery() -> dict:
    """Celery-friendly entrypoint that runs the warm in a fresh loop."""
    try:
        return asyncio.run(warm_all())
    except Exception as exc:  # noqa: BLE001
        logger.exception("warm_sync_for_celery failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def warm_interval() -> int:
    return WARM_INTERVAL_SECONDS
