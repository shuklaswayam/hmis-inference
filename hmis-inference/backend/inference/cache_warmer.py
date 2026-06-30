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
from backend.inference.audit import new_trace
from backend.inference.schemas import Severity

logger = logging.getLogger(__name__)


WARM_INTERVAL_SECONDS = int(os.environ.get("INFERENCE_WARM_INTERVAL_SECONDS", "840"))


def _envelope_shape(*, workstream: str, signals) -> dict:
    """Build the same envelope shape the live loader returns so a
    cache-warmed key validates against ``InferenceEnvelope`` cleanly.
    The warmer doesn't write audit rows (it's a periodic refresh); it
    only seeds the Redis hot-path with the response-shaped envelope."""
    now = datetime.now(timezone.utc)
    expires = inference_cache.expires_at(now)
    sev, conf = _aggregate_severity(workstream, signals)
    return {
        "workstream": workstream,
        "data": {"signals": signals, "count": len(signals)}
        if isinstance(signals, list)
        else signals,
        "severity": sev,
        "confidence": conf,
        "generated_at": now.isoformat(),
        "expires_at":   expires.isoformat(),
        "trace_id":     str(new_trace()),
    }


_SEVERITY_BY_WORKSTREAM = {
    "outbreak_risk":   outbreak_risk.aggregate_severity,
    "hospital_pressure": hospital_pressure.aggregate_severity,
}


def _aggregate_severity(name: str, signals):
    """Run the workstream's severity aggregator so the cached envelope
    carries the same ``severity`` + ``confidence`` the live endpoint would
    compute on a cache miss."""
    agg = _SEVERITY_BY_WORKSTREAM.get(name)
    if agg is None:
        # priority_rank and policy_memo emit dict-shaped payloads whose
        # aggregate_severity takes that dict, not a list. Resolve at call-time.
        if name == "priority_rank":
            return priority_rank.aggregate_severity(signals)
        if name == "policy_memo":
            return _memo_severity(signals)
        return ("LOW", None)
    return agg(signals)


def _memo_severity(memo: dict) -> tuple[str, float]:
    sev = (memo.get("severity") or "LOW").upper()
    conf_raw = memo.get("confidence")
    try:
        conf = float(conf_raw) if conf_raw is not None else 0.0
    except (TypeError, ValueError):
        conf = 0.0
    if conf > 1.0:
        conf = conf / 10.0  # memo stores 0..10
    return (sev, conf)


async def warm_all() -> dict:
    """Recompute and refresh cache for all 4 workstreams."""
    results: dict[str, dict] = {}

    async def _run(name: str, score_fn):
        key = inference_cache.make_key(name, {"w": "warm"})
        try:
            signals = await score_fn()
            envelope = _envelope_shape(workstream=name, signals=signals)
            await inference_cache.set_around(key, envelope)
            results[name] = {"ok": True, "key": key}
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache warmer failed for %s: %s", name, exc)
            results[name] = {"ok": False, "error": str(exc)}

    # priority_rank needs outbreak + pressure first.
    await _run("outbreak_risk",   outbreak_risk.score)
    ob = await outbreak_risk.score()
    await _run("hospital_pressure", lambda: hospital_pressure.score())
    pr = await hospital_pressure.score()
    await _run(
        "priority_rank",
        lambda: priority_rank.rank(outbreak_signals=ob, pressure_signals=pr),
    )
    rk = await priority_rank.rank(outbreak_signals=ob, pressure_signals=pr)
    await _run(
        "policy_memo",
        lambda: policy_memo.compose(outbreak_signals=ob, pressure_signals=pr, ranked=rk),
    )

    try:
        from backend.inference.pubsub import publish_event
        await publish_event("cache_warmed", {"workstreams": list(results.keys())})
    except Exception:  # noqa: BLE001
        logger.debug("publish_event(cache_warmed) failed")

    return {"now": datetime.now(timezone.utc).isoformat(), "results": results}


def warm_sync_for_celery() -> dict:
    """Celery-friendly entrypoint that runs the warm in a fresh loop."""
    try:
        return asyncio.run(warm_all())
    except Exception as exc:  # noqa: BLE001
        logger.exception("warm_sync_for_celery failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def warm_interval() -> int:
    return WARM_INTERVAL_SECONDS
