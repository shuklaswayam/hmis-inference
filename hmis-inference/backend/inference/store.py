"""Read-side helpers over ``inference_audit`` for the weekly review surface.

Keeps DB SQL out of the router — every audit fetch goes through here.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from backend.database import Database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time-window parsing
# ---------------------------------------------------------------------------
def parse_window_to_hours(window: str) -> int:
    """Parse short-window tokens used by the UI: 1h / 24h / 7d / 30d."""
    token = (window or "").strip().lower()
    table = {"1h": 1, "24h": 24, "7d": 24 * 7, "30d": 24 * 30}
    return table.get(token, 24)


# ---------------------------------------------------------------------------
# Audit list + detail
# ---------------------------------------------------------------------------
async def list_audit_rows(
    *,
    workstream: Optional[str] = None,
    severity: Optional[str] = None,
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
    window: str = "24h",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Pull recent audit rows ordered newest-first.

    Filters compose via AND. ``window`` maps onto ``generated_at``.
    """
    hours = parse_window_to_hours(window)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    conditions = ["generated_at >= $1"]
    params: list = [since]
    idx = 2

    if workstream:
        conditions.append(f"workstream = ${idx}")
        params.append(workstream)
        idx += 1
    if severity:
        conditions.append(f"severity = ${idx}")
        params.append(severity.upper())
        idx += 1
    if district_id:
        conditions.append(f"district_id = ${idx}::uuid")
        params.append(district_id)
        idx += 1
    if facility_id:
        conditions.append(f"facility_id = ${idx}::uuid")
        params.append(facility_id)
        idx += 1

    where_sql = " AND ".join(conditions)
    sql = f"""
        (
            SELECT
                id, workstream, trace_id, district_id, facility_id,
                user_id, severity, confidence, generated_at, expires_at,
                request, response
            FROM inference_audit
            WHERE {where_sql}
        )
        UNION ALL
        (
            SELECT
                id, workstream, trace_id, district_id, facility_id,
                user_id, severity, confidence, generated_at, expires_at,
                request, response
            FROM inference_audit_archive
            WHERE {where_sql}
        )
        ORDER BY generated_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """
    params.extend([limit, offset])

    rows = await Database.fetch(sql, *params)
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": str(r["id"]),
                "workstream": r["workstream"],
                "trace_id": str(r["trace_id"]),
                "district_id": str(r["district_id"]) if r["district_id"] else None,
                "facility_id": str(r["facility_id"]) if r["facility_id"] else None,
                "user_id": str(r["user_id"]) if r["user_id"] else None,
                "severity": r["severity"],
                "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
                "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "request": _decode_jsonb(r["request"]),
                "response": _decode_jsonb(r["response"]),
            }
        )
    return out


async def get_audit_row(trace_id: str | UUID) -> Optional[dict]:
    """Return one audit row by trace_id, or None if missing."""
    tid = str(trace_id)
    row = await Database.fetchrow(
        """
        (
            SELECT
                id, workstream, trace_id, district_id, facility_id,
                user_id, severity, confidence, generated_at, expires_at,
                request, response
            FROM inference_audit
            WHERE trace_id = $1::uuid
        )
        UNION ALL
        (
            SELECT
                id, workstream, trace_id, district_id, facility_id,
                user_id, severity, confidence, generated_at, expires_at,
                request, response
            FROM inference_audit_archive
            WHERE trace_id = $1::uuid
        )
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        tid,
    )
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "workstream": row["workstream"],
        "trace_id": str(row["trace_id"]),
        "district_id": str(row["district_id"]) if row["district_id"] else None,
        "facility_id": str(row["facility_id"]) if row["facility_id"] else None,
        "user_id": str(row["user_id"]) if row.get("user_id") else None,
        "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
        "generated_at": row["generated_at"].isoformat() if row["generated_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "request": _decode_jsonb(row["request"]),
        "response": _decode_jsonb(row["response"]),
    }


def _decode_jsonb(value) -> dict:
    """asyncpg returns jsonb as either str (when text-format fetch) or
    already-decoded object — normalise to dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {"_raw": value}
    return {}


# ---------------------------------------------------------------------------
# Priority-snapshot storage for the notifier's transition detector
# ---------------------------------------------------------------------------
PRIORITY_SNAPSHOT_KEY = "inf:priority_rank:last_snapshot:v1"


async def load_priority_snapshot() -> Optional[dict]:
    """Last-seen #1 ranking snapshot. Stored in Redis with no TTL —
    the notifier explicitly clears it on success."""
    try:
        from backend.inference.cache import get_client
        raw = await get_client().get(PRIORITY_SNAPSHOT_KEY)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


async def save_priority_snapshot(snapshot: dict) -> None:
    try:
        from backend.inference.cache import get_client, ttl_seconds
        await get_client().setex(
            PRIORITY_SNAPSHOT_KEY,
            # Two cache cycles is plenty for the transition detector.
            max(ttl_seconds() * 2, 1800),
            json.dumps(snapshot, default=str),
        )
    except Exception:  # noqa: BLE001
        logger.debug("priority snapshot save failed", exc_info=True)
