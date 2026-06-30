"""Analytics read endpoints — used by the dashboard's Analytics page.

Returns rows from ``inference_results`` joined to ``districts`` and
``health_facilities``. The four charts on the Analytics page consume
``severity``, ``district_name``, ``created_at``, and ``confidence_score`` —
nothing more, so this endpoint is intentionally lean.

Mounted under ``/api/v1/alerts`` (same path the frontend already calls).
Kept distinct from ``backend/_legacy/alerts.py`` which:
  * defaults ``severity='HIGH'`` and would silently drop MEDIUM/LOW/CRITICAL
  * re-runs the deterministic rules engine on every GET as a side-effect
"""

from __future__ import annotations

import json
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, Query

from backend.database import Database

router = APIRouter(prefix="/api/v1/alerts", tags=["analytics"])

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
CACHE_TTL = 30


@router.get("/", summary="Active alerts for the Analytics dashboard")
async def list_alerts(
    severity: str | None = Query(
        None, description="Optional severity filter (HIGH, MEDIUM, LOW, CRITICAL)"
    ),
    district_id: str | None = Query(
        None, description="Optional district UUID filter"
    ),
    limit: int = Query(500, ge=1, le=1000),
) -> list[dict]:
    """Read straight from ``inference_results`` joined to lookups.

    Returns rows suitable for the four Analytics charts: severity,
    district_name, created_at, confidence_score. All severities by default so
    the distribution pie renders naturally.
    """
    cache_key = f"analytics:alerts:{severity or 'ALL'}:{district_id or 'ALL'}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:  # noqa: BLE001 — cache outage must not break the page
        cached = None

    conds = ["ir.expires_at IS NULL"]
    params: list = []
    idx = 1
    if severity:
        conds.append(f"ir.severity = ${idx}")
        params.append(severity.upper())
        idx += 1
    if district_id:
        conds.append(f"ir.district_id = ${idx}::uuid")
        params.append(district_id)
        idx += 1
    where = " AND ".join(conds)
    sql = f"""
        SELECT
            ir.id,
            ir.severity,
            ir.inference_type,
            ir.confidence_score,
            ir.created_at,
            ir.district_id,
            ir.facility_id,
            d.name AS district_name,
            hf.name AS facility_name
        FROM inference_results ir
        LEFT JOIN districts d ON d.id = ir.district_id
        LEFT JOIN health_facilities hf ON hf.id = ir.facility_id
        WHERE {where}
        ORDER BY ir.created_at DESC
        LIMIT ${idx}
    """
    params.append(limit)
    rows = await Database.fetch(sql, *params)

    out = [
        {
            "id": str(r["id"]),
            "severity": r["severity"],
            "inference_type": r["inference_type"],
            "district_id": str(r["district_id"]) if r["district_id"] else None,
            "district_name": r["district_name"] or "",
            "facility_id": str(r["facility_id"]) if r["facility_id"] else None,
            "facility_name": r["facility_name"] or "",
            "confidence_score": float(r["confidence_score"])
            if r["confidence_score"] is not None
            else 0.0,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]

    try:
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(out))
    except Exception:  # noqa: BLE001
        pass

    return out
