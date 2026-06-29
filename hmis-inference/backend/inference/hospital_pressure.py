"""Workstream 2 — Hospital Pressure Classifier.

Per-facility 3-tier classification with 48-hour trend projection.
Rule-augmented (per premise §6.1):

  Tier rules (deterministic):
      Critical  — icu ≥ 90 OR bed ≥ 95 OR
                  (opd_visits ≥ 1.8× avg AND icu ≥ 75)
      Strained  — icu ≥ 80 OR bed ≥ 85 OR opd_visits ≥ 1.5× avg
      Normal    — otherwise

  48-hour projection: FacilityLoadForecaster gives ICU + bed yhat
  predictions; trend overall is rising/easing/stable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

from backend.database import Database
from backend.ml.forecaster import FacilityLoadForecaster

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Why-this-tier one-liner audit trails — kept short so they fit in widgets.
# ---------------------------------------------------------------------------
ACTION = {
    "Normal":   "Continue routine operations; no diversion required.",
    "Strained": "Pre-emptive patient diversion; redeploy float staff.",
    "Critical": "Activate emergency capacity; halt elective admissions; escalate to State.",
}


@dataclass(frozen=True)
class PressureSignal:
    facility_id: str
    facility_name: str
    district_name: str
    tier: str
    confidence: float
    icu_occupancy_pct: float
    bed_occupancy_pct: float
    trend: str
    proj_48h: dict
    one_liner: str
    recommended_action: str
    contributing_metrics: list[str]


# ---------------------------------------------------------------------------
# Tier rules
# ---------------------------------------------------------------------------
def _classify(
    *,
    icu_pct: float,
    bed_pct: float,
    opd_ratio: float,
) -> str:
    if icu_pct >= 90 or bed_pct >= 95 or (opd_ratio >= 1.8 and icu_pct >= 75):
        return "Critical"
    if icu_pct >= 80 or bed_pct >= 85 or opd_ratio >= 1.5:
        return "Strained"
    return "Normal"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def score(
    *,
    district_id: Optional[str] = None,
    facility_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[dict]:
    """Compute pressure signal per facility.

    Filters:
      - facility_id : single facility
      - district_id : all facilities in a district
      - (no filter) : every facility

    Pagination (Phase 3):
      - limit  : cap the number of returned signals (sorted worst-first)
      - offset : skip the first N signals
    """
    facility_rows = await Database.fetch(
        """
        WITH latest AS (
            SELECT DISTINCT ON (facility_id)
                facility_id, icu_occupancy_pct, bed_occupancy_pct,
                opd_visits, reported_date
            FROM facility_metrics
            ORDER BY facility_id, reported_date DESC
        )
        SELECT
            hf.id AS facility_id,
            hf.name AS facility_name,
            d.name AS district_name,
            l.icu_occupancy_pct,
            l.bed_occupancy_pct,
            l.opd_visits,
            l.reported_date
        FROM health_facilities hf
        JOIN districts d ON d.id = hf.district_id
        LEFT JOIN latest l ON l.facility_id = hf.id
        WHERE ($1::uuid IS NULL OR hf.id = $1::uuid)
          AND ($2::uuid IS NULL OR hf.district_id = $2::uuid)
        ORDER BY hf.name
        """,
        facility_id,
        district_id,
    )
    if not facility_rows:
        return []

    # 30-day OPD average per facility for ratio computation.
    avg_rows = await Database.fetch(
        """
        SELECT
            facility_id,
            COALESCE(AVG(opd_visits), 0) AS avg_opd
        FROM facility_metrics
        WHERE reported_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY facility_id
        """
    )
    avg_opd_by_facility = {str(r["facility_id"]): float(r["avg_opd"]) for r in avg_rows}

    out: list[dict] = []
    now = datetime.now(timezone.utc)

    for row in facility_rows:
        fid = str(row["facility_id"])
        icu = float(row["icu_occupancy_pct"] or 0.0)
        bed = float(row["bed_occupancy_pct"] or 0.0)
        opd = int(row["opd_visits"] or 0)
        avg_opd = avg_opd_by_facility.get(fid, 1.0) or 1.0
        opd_ratio = opd / avg_opd if avg_opd > 0 else 1.0
        tier = _classify(icu_pct=icu, bed_pct=bed, opd_ratio=opd_ratio)

        contributing = [
            f"ICU {icu:.1f}%",
            f"bed {bed:.1f}%",
            f"OPD {opd_ratio:.2f}× avg",
        ]

        # 48-hour projection — best effort; degrade gracefully.
        proj = await _projection(fid)
        trend = proj["trend"] if proj else "stable"
        icu24 = proj.get("icu_pred_24h")
        icu48 = proj.get("icu_pred_48h")
        bed48 = proj.get("bed_pred_48h")

        # Confidence: bigger inputs of the rule that fired → higher
        # confidence. Cap at 0.99 to avoid false certainty.
        if tier == "Critical":
            confidence = min(0.99, 0.7 + (icu - 80) / 50.0)
        elif tier == "Strained":
            confidence = min(0.95, 0.55 + max(icu - 70, bed - 70) / 80.0)
        else:
            # Confidence that this *is* Normal: more normal = higher.
            confidence = min(0.9, 0.5 + (50.0 - icu) / 100.0)
        confidence = round(max(0.05, min(0.99, confidence)), 3)

        one_liner = (
            f"{row['facility_name']}: {tier} "
            f"(ICU {icu:.0f}% / bed {bed:.0f}% / "
            f"48-h trend: {trend})"
        )

        out.append(
            {
                "facility_id": fid,
                "facility_name": row["facility_name"],
                "district_name": row["district_name"],
                "tier": tier,
                "confidence": confidence,
                "icu_occupancy_pct": round(icu, 1),
                "bed_occupancy_pct": round(bed, 1),
                "trend_48h": trend,
                "icu_pred_24h": icu24,
                "icu_pred_48h": icu48,
                "bed_pred_48h": bed48,
                "one_liner": one_liner,
                "recommended_action": ACTION[tier],
                "contributing_metrics": contributing,
                "generated_at": now.isoformat(),
            }
        )

    # Worst-first ordering (Critical before Strained before Normal).
    out.sort(key=lambda s: (_tier_weight(s["tier"]), -float(s["confidence"])))
    if limit is not None:
        return out[offset:offset + limit]
    return out[offset:]


def _tier_weight(tier: str) -> int:
    return {"Critical": 0, "Strained": 1, "Normal": 2}.get(tier, 3)


async def _projection(facility_id: str) -> Optional[dict]:
    """Forecast ICU + bed occupancy 48h ahead for one facility."""
    rows = await Database.fetch(
        """
        SELECT reported_date AS ds,
               icu_occupancy_pct AS icu,
               bed_occupancy_pct AS bed
        FROM facility_metrics
        WHERE facility_id = $1::uuid
          AND reported_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY reported_date
        """,
        facility_id,
    )
    if len(rows) < 14:
        return None
    icu_df = pd.DataFrame([(r["ds"], r["icu"] or 0.0) for r in rows], columns=["ds", "y"])
    bed_df = pd.DataFrame([(r["ds"], r["bed"] or 0.0) for r in rows], columns=["ds", "y"])
    try:
        forecaster = FacilityLoadForecaster(
            weekly_seasonality=True, yearly_seasonality=False
        )
        proj = forecaster.fit_and_forecast(icu_df, bed_df, horizon_days=2)
        return {
            "trend": proj.trend,
            "icu_pred_24h": round(proj.icu_pred_24h, 2),
            "icu_pred_48h": round(proj.icu_pred_48h, 2),
            "bed_pred_48h": round(proj.bed_pred_48h, 2),
            "series": proj.series,
        }
    except Exception:  # noqa: BLE001
        logger.exception("facility-load projection failed (facility=%s)", facility_id)
        return None


def aggregate_severity(signals: list[dict]) -> tuple[str, float]:
    if not signals:
        return ("LOW", 0.0)
    worst = min(signals, key=lambda s: _tier_weight(s["tier"]))
    sev = {"Critical": "CRITICAL", "Strained": "HIGH", "Normal": "LOW"}[worst["tier"]]
    return (sev, float(worst["confidence"]))
