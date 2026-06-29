"""Audit + digest routes — list/detail + weekly digest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from backend.inference import audit, digest, store

router = APIRouter(prefix="/api/v1/inference/audit", tags=["inference-audit"])


@router.get(
    "/",
    summary="List recent inference_audit rows",
)
async def list_audit(
    workstream: Optional[str] = Query(None, description="Filter by workstream name"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    district_id: Optional[str] = Query(None, description="Restrict to a district UUID"),
    facility_id: Optional[str] = Query(None, description="Restrict to a facility UUID"),
    window: str = Query("24h", description="1h | 24h | 7d | 30d"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    rows = await store.list_audit_rows(
        workstream=workstream,
        severity=severity,
        district_id=district_id,
        facility_id=facility_id,
        window=window,
        limit=limit,
        offset=offset,
    )
    return {
        "workstream_filter": workstream,
        "severity_filter": severity,
        "window": window,
        "count": len(rows),
        "rows": rows,
        "now": datetime.now(timezone.utc).isoformat(),
    }


# Phase 3: digest endpoint is mounted BEFORE /{trace_id} so the literal
# "digest" path doesn't get matched against the UUID dynamic route.
@router.get(
    "/digest",
    summary="Weekly digest — markdown or json",
)
async def get_digest(
    fmt: str = Query("md", pattern="^(md|json)$", description="Output format"),
    window: str = Query("7d", description="1h | 24h | 7d | 30d"),
):
    payload = await digest.build_digest(window=window)
    if fmt == "md":
        return PlainTextResponse(
            payload["markdown"],
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="hmis-digest-{window}.md"',
            },
        )
    return JSONResponse(payload)


@router.get(
    "/{trace_id}",
    summary="Detail of one audit row by trace_id",
)
async def get_audit(trace_id: UUID) -> dict:
    row = await store.get_audit_row(trace_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"trace_id {trace_id} not found in inference_audit"
        )
    return {
        "row": row,
        "latest_trace_audits": await store.list_audit_rows(
            workstream=row["workstream"], window="24h", limit=20
        ),
    }
