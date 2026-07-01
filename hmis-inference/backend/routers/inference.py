"""Inference router — 4 workstream endpoints (per premise §6.3).

    GET /api/v1/inference/outbreak-risk
    GET /api/v1/inference/hospital-pressure
    GET /api/v1/inference/priority-rank
    GET /api/v1/inference/policy-memo

Each endpoint:
  * Reads through the 15-minute Redis cache (``inference.cache``)
  * Calls the workstream's compute function
  * Writes one row to ``inference_audit`` (per premise §6.2)
  * Records metrics (Phase 3)
  * Attaches the calling user to the audit row (Phase 4)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.dependencies import CurrentUser, get_optional_user
from backend.inference import (
    audit,
    cache as inference_cache,
    hospital_pressure,
    metrics as inf_metrics,
    outbreak_risk,
    policy_memo,
    priority_rank,
)
from backend.inference.schemas import InferenceEnvelope, Severity

router = APIRouter(prefix="/api/v1/inference", tags=["inference"])


def _envelope(
    *,
    workstream: str,
    data: dict,
    severity: Severity,
    confidence: Optional[float],
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
    user_id: Optional[str] = None,
    trace_id=None,
) -> dict:
    now = datetime.now(timezone.utc)
    expires = inference_cache.expires_at(now)
    tid = trace_id or audit.new_trace()
    return {
        "workstream": workstream,
        "data": data,
        "severity": severity,
        "confidence": confidence,
        "generated_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "trace_id": str(tid),
        "_audit_kwargs": {
            "trace_id": tid,
            "district_id": district_id,
            "facility_id": facility_id,
            "user_id": user_id,
            "severity": severity,
            "confidence": confidence,
            "generated_at": now,
            "expires_at": expires,
            "request": {"district_id": district_id, "facility_id": facility_id},
            "workstream": workstream,
        },
    }


async def _finalize(envelope: dict, response: dict) -> dict:
    kwargs = envelope.pop("_audit_kwargs", None)
    if kwargs is not None:
        try:
            await audit.write(response=response, **kwargs)
        except Exception:  # noqa: BLE001
            pass
    return envelope


async def _read_through(key: str, workstream: str, loader, *, force_refresh: bool):
    """Cache read-through that records hit/miss + duration."""
    async with inf_metrics.async_track_call(workstream) as meta:
        hit, payload = await inference_cache.read_through(
            key, loader, force_refresh=force_refresh
        )
    inf_metrics.record_cache(workstream, hit=hit)
    return hit, payload


# ---------------------------------------------------------------------------
# WS1 — Outbreak Risk Scoring
# ---------------------------------------------------------------------------
@router.get(
    "/outbreak-risk",
    summary="Workstream 1 — Outbreak Risk per (ward × disease)",
    response_model=InferenceEnvelope,
)
async def get_outbreak_risk(
    district_id: Optional[str] = Query(None, description="Restrict to a district UUID"),
    disease_name: Optional[str] = Query(None, description="Restrict to a single disease"),
    force_refresh: bool = Query(False, description="Bypass the 15-minute Redis cache"),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    key = inference_cache.make_key(
        "outbreak_risk", {"d": district_id or "ALL", "dz": disease_name or "ALL"}
    )

    async def loader():
        signals = await outbreak_risk.score(
            district_id=district_id, disease_name=disease_name
        )
        sev, conf = outbreak_risk.aggregate_severity(signals)
        envelope = _envelope(
            workstream="outbreak_risk",
            data={"signals": signals, "count": len(signals)},
            severity=sev,
            confidence=conf,
            district_id=district_id,
            user_id=user.id if user else None,
        )
        envelope = await _finalize(envelope, response=envelope["data"])
        return envelope

    hit, payload = await _read_through(key, "outbreak_risk", loader, force_refresh=force_refresh)
    payload["cache_hit"] = hit
    return payload


# ---------------------------------------------------------------------------
# WS2 — Hospital Pressure Classification (Phase 3: paginated)
# ---------------------------------------------------------------------------
@router.get(
    "/hospital-pressure",
    summary="Workstream 2 — Hospital Pressure with 48-hour projection",
    response_model=InferenceEnvelope,
)
async def get_hospital_pressure(
    district_id: Optional[str] = Query(None, description="Restrict to a district UUID"),
    facility_id: Optional[str] = Query(None, description="Restrict to a single facility UUID"),
    limit: int = Query(25, ge=1, le=500, description="Cap returned signals"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    force_refresh: bool = Query(False),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    key = inference_cache.make_key(
        "hospital_pressure",
        {"d": district_id or "ALL", "f": facility_id or "ALL", "l": limit},
    )

    async def loader():
        signals = await hospital_pressure.score(
            district_id=district_id, facility_id=facility_id,
            limit=limit, offset=offset,
        )
        sev, conf = hospital_pressure.aggregate_severity(signals)
        envelope = _envelope(
            workstream="hospital_pressure",
            data={"signals": signals, "count": len(signals), "limit": limit, "offset": offset},
            severity=sev,
            confidence=conf,
            district_id=district_id,
            facility_id=facility_id,
            user_id=user.id if user else None,
        )
        envelope = await _finalize(envelope, response=envelope["data"])
        return envelope

    hit, payload = await _read_through(key, "hospital_pressure", loader, force_refresh=force_refresh)
    payload["cache_hit"] = hit
    return payload


# ---------------------------------------------------------------------------
# WS3 — Priority Alert Ranker
# ---------------------------------------------------------------------------
@router.get(
    "/priority-rank",
    summary="Workstream 3 — Top-5 ranked policy actions for today",
    response_model=InferenceEnvelope,
)
async def get_priority_rank(
    district_id: Optional[str] = Query(None, description="Optional district filter"),
    force_refresh: bool = Query(False),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    key = inference_cache.make_key("priority_rank", {"d": district_id or "ALL"})

    async def loader():
        outbreak_signals = await outbreak_risk.score(district_id=district_id)
        pressure_signals = await hospital_pressure.score(district_id=district_id)
        ranked = await priority_rank.rank(
            outbreak_signals=outbreak_signals,
            pressure_signals=pressure_signals,
        )
        sev, conf = priority_rank.aggregate_severity(ranked)
        envelope = _envelope(
            workstream="priority_rank",
            data={"ranked": ranked, "count": len(ranked)},
            severity=sev,
            confidence=conf,
            district_id=district_id,
            user_id=user.id if user else None,
        )
        envelope = await _finalize(envelope, response=envelope["data"])
        return envelope

    hit, payload = await _read_through(key, "priority_rank", loader, force_refresh=force_refresh)
    payload["cache_hit"] = hit
    return payload


# ---------------------------------------------------------------------------
# WS4 — Policy Insight Narrator
# ---------------------------------------------------------------------------
@router.get(
    "/policy-memo",
    summary="Workstream 4 — LLM-narrated policy memo (aggregated)",
    response_model=InferenceEnvelope,
)
async def get_policy_memo(
    district_id: Optional[str] = Query(None, description="Optional district scope"),
    force_refresh: bool = Query(False),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    # Cache key bumped v1 -> v2: invalidates any payloads cached before
    # the rich-description enrichment so the dashboard sees rich data ASAP.
    key = inference_cache.make_key(
        "policy_memo",
        {"d": district_id or "ALL"},
        version="v2",
    )

    async def loader():
        outbreak_signals = await outbreak_risk.score(district_id=district_id)
        pressure_signals = await hospital_pressure.score(district_id=district_id)
        ranked = await priority_rank.rank(
            outbreak_signals=outbreak_signals,
            pressure_signals=pressure_signals,
        )
        memo = await policy_memo.compose(
            outbreak_signals=outbreak_signals,
            pressure_signals=pressure_signals,
            ranked=ranked,
        )
        sev, conf = (
            ("CRITICAL", 0.95) if ranked and ranked[0]["severity"] == "CRITICAL"
            else ("HIGH", 0.85) if ranked and ranked[0]["severity"] == "HIGH"
            else ("MEDIUM", 0.5)
        )
        envelope = _envelope(
            workstream="policy_memo",
            data=memo,
            severity=sev,
            confidence=conf,
            district_id=district_id,
            user_id=user.id if user else None,
        )
        envelope = await _finalize(envelope, response=envelope["data"])
        return envelope

    hit, payload = await _read_through(key, "policy_memo", loader, force_refresh=force_refresh)
    payload["cache_hit"] = hit
    return payload


# ---------------------------------------------------------------------------
# Health endpoint for the dashboard widget spinner
# ---------------------------------------------------------------------------
@router.get("/health", summary="Inference subsystem health")
async def inference_health() -> dict:
    """Lightweight liveness check used by the dashboard header."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "workstreams": ["outbreak_risk", "hospital_pressure", "priority_rank", "policy_memo"],
        "cache_ttl_seconds": inference_cache.ttl_seconds(),
        "now": now,
    }
