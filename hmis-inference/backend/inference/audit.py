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

    # Hot JSONB extraction — see migration 005 for the schema.
    signals_count, top_tier, llm_generated = _extract_hot_fields(workstream, response)

    try:
        await Database.execute(
            """
            INSERT INTO inference_audit (
                workstream, trace_id, district_id, facility_id,
                user_id, request, response,
                severity, confidence,
                response_signals_count, response_top_tier, response_llm_generated,
                generated_at, expires_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb,
                $8, $9,
                $10, $11, $12,
                $13, $14
            )
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
            signals_count,
            top_tier,
            llm_generated,
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


# ---------------------------------------------------------------------------
# Hot JSONB extraction — migration 005 promoted `signals_count`,
# `top_tier`, and (memo only) `llm_generated` from the JSONB blob
# to typed columns so the weekly policy-review query is plain SQL.
# Keep this in lock-step with backfill semantics in
# migrations/005_inference_audit_extract.sql.
# ---------------------------------------------------------------------------
_TIER_RANK = {
    "CRITICAL": 4, "HIGH": 3, "STRAINED": 3,
    "MEDIUM": 2, "LOW": 1, "NORMAL": 1,
}


def _extract_hot_fields(workstream: str, response: dict[str, Any]) -> tuple[Optional[int], Optional[str], Optional[bool]]:
    """Best-effort extraction of (signals_count, top_tier, llm_generated)."""
    if not isinstance(response, dict):
        return (None, None, None)

    if workstream in ("outbreak_risk", "hospital_pressure"):
        items = response.get("signals") or []
        if not isinstance(items, list) or not items:
            return (0, None, None)
        tiers = [
            (it.get("tier") if isinstance(it, dict) else "")
            for it in items
        ]
        valid = [t for t in tiers if isinstance(t, str) and t]
        if not valid:
            return (len(items), None, None)
        ranked = {k.upper() if isinstance(k, str) else k: v for k, v in {
            "Critical": 4, "High": 3, "Strained": 3,
            "Medium": 2, "Low": 1, "Normal": 1,
        }.items()}
        top = max(valid, key=lambda t: ranked.get(t.upper(), 0))
        return (len(items), top.upper() if top else None, None)

    if workstream == "priority_rank":
        items = response.get("ranked") or []
        if not isinstance(items, list) or not items:
            return (0, None, None)
        sev_values = [
            (it.get("severity") if isinstance(it, dict) else "")
            for it in items
        ]
        valid = [s for s in sev_values if isinstance(s, str) and s]
        if not valid:
            return (len(items), None, None)
        sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        top = max(valid, key=lambda s: sev_rank.get(s.upper(), 0))
        return (len(items), top.upper() if top else None, None)

    if workstream == "policy_memo":
        actions = response.get("recommended_actions") or []
        count = len(actions) if isinstance(actions, list) else 0
        llm = response.get("llm_generated")
        return (count, None, bool(llm) if llm is not None else None)

    return (None, None, None)
