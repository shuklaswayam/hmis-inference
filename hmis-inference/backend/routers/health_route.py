"""Decomposed fastapi ``/health`` endpoint that surfaces per-subsystem liveness."""

from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.inference.health import check_liveness

router = APIRouter(tags=["observability"])


@router.get("/health/deep", summary="Deep health probe — DB/Redis/Celery")
async def health_deep():
    """Sub-system liveness probe used by orchestrators and dashboards.

    Returns HTTP 200 with ``ok=True`` when all subsystems healthy,
    otherwise 200 with ``ok=False`` plus per-subsystem error details.
    The endpoint always returns 200 so operators get the full report
    (status code 500 wouldn't add information past ``ok=False``).
    """
    report = await check_liveness()
    return JSONResponse(report)


@router.get("/health", summary="Liveness (legacy) — returns overall OK string")
async def health_legacy():
    report = await check_liveness()
    return {
        "status": "healthy" if report["ok"] else "degraded",
        "service": "hmis-inference",
        "version": os.environ.get("HMIS_VERSION", "2.0.0"),
        "auth_enabled": bool(os.environ.get("API_KEY", "").strip()),
        "inference_workstreams": [
            "outbreak_risk",
            "hospital_pressure",
            "priority_rank",
            "policy_memo",
        ],
        "auth_endpoints": [
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/me",
            "/api/v1/auth/register",
        ],
    }
