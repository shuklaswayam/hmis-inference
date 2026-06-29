"""CRITICAL notifier — fires a webhook when priority-rank #1 transitions.

Tunable via env:
  WEBHOOK_URL          — POST destination (Commissioner's external
                          briefing system, Slack, etc.). If unset, the
                          notifier still detects transitions but logs
                          instead of firing HTTP.
  WEBHOOK_ENABLED      — '1' / '0' master switch.
  WEBHOOK_TIMEOUT_S    — request timeout (default 5s).

Celery beat calls ``check_priority_transition()`` once a minute. The
function:
  1. Recomputes priority-rank (cheap — single aggregation query).
  2. Loads the last-seen #1 snapshot from Redis.
  3. If #1 is CRITICAL *and* the snapshot differs (rank/headline/severity),
     fires POST. Falls back to lg.INFO when no destination is configured.
  4. Saves the new snapshot regardless (so transitions are durable).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.inference import (
    hospital_pressure,
    outbreak_risk,
    priority_rank,
    store,
)

logger = logging.getLogger(__name__)


WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
WEBHOOK_ENABLED = os.environ.get("WEBHOOK_ENABLED", "0").strip() == "1"
WEBHOOK_TIMEOUT = float(os.environ.get("WEBHOOK_TIMEOUT_S", "5.0"))


def is_configured() -> bool:
    return bool(WEBHOOK_URL) and WEBHOOK_ENABLED


def _summarise_top(ranked: list[dict]) -> Optional[dict]:
    """Pick the ranked list's #1 — or None if empty."""
    if not ranked:
        return None
    top = ranked[0]
    return {
        "rank":       top.get("rank"),
        "headline":   top.get("headline"),
        "severity":   top.get("severity"),
        "owner":      top.get("recommended_owner"),
        "sla_hours":  top.get("sla_hours"),
        "step":       top.get("recommended_step"),
    }


def _snapshots_differ(prev: Optional[dict], cur: dict) -> bool:
    """Return True when (rank, headline, severity) all match the prior."""
    if prev is None:
        return True  # no prior → first observation; treat as a transition
    return (
        prev.get("rank")     != cur.get("rank")
        or prev.get("headline") != cur.get("headline")
        or prev.get("severity") != cur.get("severity")
    )


async def _post_webhook(payload: dict) -> bool:
    if not is_configured():
        logger.info("notifier (dry-run): %s", payload)
        return False
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            res = await client.post(WEBHOOK_URL, json=payload)
            res.raise_for_status()
            return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("notifier POST failed (url=%s): %s", WEBHOOK_URL, exc)
        return False


async def check_priority_transition() -> dict:
    """Inspect the current #1 ranking; fire webhook on CRITICAL transition."""
    ob_signals = await outbreak_risk.score()
    pr_signals = await hospital_pressure.score()
    ranked = await priority_rank.rank(
        outbreak_signals=ob_signals, pressure_signals=pr_signals
    )
    cur = _summarise_top(ranked)
    if cur is None:
        return {"ok": True, "reason": "no_ranked_items"}

    prev = await store.load_priority_snapshot()
    should_fire = (
        cur.get("severity") == "CRITICAL"
        and _snapshots_differ(prev, cur)
    )
    payload = {
        "event":       "priority_critical_transition",
        "fired_at":    datetime.now(timezone.utc).isoformat(),
        "workstream":  "priority_rank",
        "ranked":      cur,
        "all_ranked":  ranked[:5],
    }
    fired = False
    if should_fire:
        fired = await _post_webhook(payload)
        # Phase 3: live push — publish to Redis so the SSE stream fans
        # out to any subscribed dashboard tab.
        try:
            from backend.inference.pubsub import publish_priority_critical
            await publish_priority_critical(payload)
        except Exception:  # noqa: BLE001
            logger.debug("publish_priority_critical failed")
    await store.save_priority_snapshot(cur)
    return {
        "ok": True,
        "should_fire": bool(should_fire),
        "fired": fired,
        "destination_configured": is_configured(),
        "current":  cur,
        "previous": prev,
    }


def check_sync_for_celery() -> dict:
    """Celery-friendly entrypoint."""
    try:
        return asyncio.run(check_priority_transition())
    except Exception as exc:  # noqa: BLE001
        logger.exception("check_sync_for_celery failed: %s", exc)
        return {"ok": False, "error": str(exc)}
