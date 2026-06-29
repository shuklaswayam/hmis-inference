"""Write inference outputs to the ``inference_audit`` table (migration 003).

Every /api/v1/inference/* endpoint calls ``audit.write(...)`` once per
response so the weekly policy review called out in §6.2 is a SQL
``GROUP BY`` away.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from backend.database import Database

logger = logging.getLogger(__name__)


async def write(
    *,
    workstream: str,
    trace_id: UUID,
    response: dict[str, Any],
    request: Optional[dict[str, Any]] = None,
    severity: Optional[str] = None,
    confidence: Optional[float] = None,
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
    user_id: Optional[str] = None,
    generated_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
) -> None:
    """Persist one inference output row. Never raises — auditing must
    not break the live endpoint.
    """
    if not workstream or workstream not in {
        "outbreak_risk",
        "hospital_pressure",
        "priority_rank",
        "policy_memo",
    }:
        logger.warning("refusing to audit unknown workstream=%s", workstream)
        return

    generated_at = generated_at or datetime.utcnow()
    expires_at = expires_at or generated_at

    try:
        await Database.execute(
            """
            INSERT INTO inference_audit (
                workstream, trace_id, district_id, facility_id,
                user_id, request, response, severity, confidence,
                generated_at, expires_at
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11)
            """,
            workstream,
            trace_id,
            UUID(district_id) if district_id else None,
            UUID(facility_id) if facility_id else None,
            UUID(user_id) if user_id else None,
            json.dumps(request or {}),
            json.dumps(response, default=str),
            severity,
            confidence,
            generated_at,
            expires_at,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "inference_audit write failed (workstream=%s trace=%s)",
            workstream, trace_id,
        )


def new_trace() -> UUID:
    return uuid4()
