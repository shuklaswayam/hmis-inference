"""Pydantic envelopes shared by the 4 workstream endpoints + audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class InferenceEnvelope(BaseModel):
    """Common shape returned by every /api/v1/inference/* endpoint."""

    workstream: Literal[
        "outbreak_risk",
        "hospital_pressure",
        "priority_rank",
        "policy_memo",
    ]
    data: dict[str, Any]
    severity: Optional[Severity] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    generated_at: datetime
    expires_at: datetime
    trace_id: str


# ---------------------------------------------------------------------------
# Workstream-specific shapes (input row schemas, useful for typed hooks)
# ---------------------------------------------------------------------------
class OutbreakSignal(BaseModel):
    """One (ward, disease) bucket for Outbreak Risk Scoring."""

    district_id: str
    district_name: str
    disease_name: str
    cases_last_14d: int
    cases_baseline_avg_30d: float
    baseline_ratio: float
    deaths_last_14d: int
    weekly_trend_slope: float
    tier: Severity
    confidence: float
    contributing_signals: list[str]
    recommended_action: str
    one_liner: str


class HospitalPressureSignal(BaseModel):
    facility_id: str
    facility_name: str
    district_name: str
    tier: Literal["Normal", "Strained", "Critical"]
    icu_occupancy_pct: float
    bed_occupancy_pct: float
    icu_pred_24h: float
    icu_pred_48h: float
    bed_pred_48h: float
    trend_48h: Literal["rising", "stable", "easing"]
    contributing_metrics: list[str]
    recommended_action: str
    one_liner: str


class PriorityAction(BaseModel):
    rank: int
    headline: str
    severity: Severity
    severity_score: float = Field(ge=0.0, le=10.0)
    recommended_owner: str
    sla_hours: int
    evidence_refs: list[str]


class PolicyMemo(BaseModel):
    headline: str
    body_md: str
    recommended_actions: list[dict[str, Any]]
    generated_from: dict[str, Any]
