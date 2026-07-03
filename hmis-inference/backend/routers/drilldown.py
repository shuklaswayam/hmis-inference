"""Drilldown router — per-facility and per-(district × disease) detail pages.

    GET /api/v1/inference/drilldown/facility/{facility_id}
    GET /api/v1/inference/drilldown/district?district_id=&disease=

Detail payload includes:
  * 14-day trajectory of ICU + bed occupancy (for chart rendering)
  * z-scores against the trajectory window
  * 48-h Prophet projection
  * Contributing signals + recommended action

This powers the dashboard click-through from any widget item.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import numpy as np
from fastapi import APIRouter, HTTPException

from backend.database import Database
from backend.inference import audit, cache as inference_cache
from backend.inference.hospital_pressure import _projection
from backend.inference.outbreak_risk import _recent_window, _baseline_avg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/inference/drilldown", tags=["inference-drilldown"])


# ---------------------------------------------------------------------------
# Facility drilldown
# ---------------------------------------------------------------------------
@router.get(
    "/facility/{facility_id}",
    summary="Drilldown detail for one facility",
)
async def facility_drilldown(facility_id: UUID) -> dict:
    facility_row = await Database.fetchrow(
        "SELECT id, name, district_id FROM health_facilities WHERE id = $1",
        facility_id,
    )
    if not facility_row:
        raise HTTPException(
            status_code=404, detail=f"facility {facility_id} not found"
        )

    district_row = await Database.fetchrow(
        "SELECT id, name FROM districts WHERE id = $1", facility_row["district_id"]
    )

    trajectory_rows = await Database.fetch(
        """
        SELECT reported_date, icu_occupancy_pct, bed_occupancy_pct,
               opd_visits, emergency_visits
        FROM facility_metrics
        WHERE facility_id = $1
          AND reported_date >= CURRENT_DATE - INTERVAL '14 days'
        ORDER BY reported_date
        """,
        facility_id,
    )

    trajectory = {
        "dates":           [r["reported_date"].isoformat()                       for r in trajectory_rows],
        "icu_pct":         [float(r["icu_occupancy_pct"] or 0.0) if r["icu_occupancy_pct"] is not None else None for r in trajectory_rows],
        "bed_pct":         [float(r["bed_occupancy_pct"] or 0.0) if r["bed_occupancy_pct"] is not None else None for r in trajectory_rows],
        "opd_visits":      [int(r["opd_visits"] or 0) for r in trajectory_rows],
        "emergency_visits":[int(r["emergency_visits"] or 0) for r in trajectory_rows],
    }

    # z-scores against the 14-day window
    z_summary: dict[str, dict] = {}
    for metric in ("icu_pct", "bed_pct", "opd_visits", "emergency_visits"):
        vals = [v for v in trajectory[metric] if v is not None]
        if len(vals) < 2:
            continue
        mean = float(np.mean(vals))
        std = float(np.std(vals, ddof=1)) or 1.0
        latest = vals[-1]
        z_summary[metric] = {
            "mean": round(mean, 2),
            "std":  round(std, 2),
            "z_score_latest": round((latest - mean) / std, 2),
            "latest": latest,
        }

    proj = await _projection(str(facility_id))

    return {
        "facility": {
            "id":   str(facility_row["id"]),
            "name": facility_row["name"],
            "district": district_row["name"] if district_row else None,
            "district_id": str(facility_row["district_id"]),
        },
        "trajectory": trajectory,
        "z_scores": z_summary,
        "projected_48h": {
            "trend":    (proj or {}).get("trend"),
            "trend_confidence": (proj or {}).get("trend_confidence", 0.0),
            "projection_available": (proj or {}).get("projection_available", False),
            "icu_24h":  (proj or {}).get("icu_pred_24h"),
            "icu_48h":  (proj or {}).get("icu_pred_48h"),
            "bed_48h":  (proj or {}).get("bed_pred_48h"),
            "series":   (proj or {}).get("series", []),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace_id":     str(audit.new_trace()),
    }


# ---------------------------------------------------------------------------
# District × disease drilldown
# ---------------------------------------------------------------------------
@router.get(
    "/district",
    summary="Drilldown detail for one (district × disease)",
)
async def district_disease_drilldown(
    district_id: str = "",
    disease: str = "",
) -> dict:
    try:
        dist_uuid = UUID(district_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid district_id: {district_id}") from exc

    district_row = await Database.fetchrow(
        "SELECT id, name FROM districts WHERE id = $1", dist_uuid
    )
    if not district_row:
        raise HTTPException(status_code=404, detail=f"district {district_id} not found")

    if not disease:
        raise HTTPException(
            status_code=400,
            detail="?disease=<name> is required for the district drilldown",
        )

    end_date = datetime.now(timezone.utc).date()
    recent = await _recent_window(disease, district_id, end_date=end_date)
    baseline = await _baseline_avg(disease, district_id, end_date=end_date)
    baseline_ratio = (
        (recent["cases_last_14d"] / 14.0) / baseline if baseline > 0 else 0.0
    )

    series_rows = await Database.fetch(
        """
        SELECT reported_date, SUM(case_count) AS cases
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE dr.disease_name = $1
          AND hf.district_id = $2::uuid
          AND dr.reported_date >= CURRENT_DATE - INTERVAL '14 days'
        GROUP BY reported_date
        ORDER BY reported_date
        """,
        disease,
        district_id,
    )
    series = [
        {"date": r["reported_date"].isoformat(), "cases": int(r["cases"] or 0)}
        for r in series_rows
    ]
    cases = [p["cases"] for p in series]
    slope = 0.0
    if len(cases) >= 2:
        xs = list(range(len(cases)))
        mx = sum(xs) / len(xs)
        my = sum(cases) / len(cases)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, cases))
        den = sum((x - mx) ** 2 for x in xs)
        slope = num / den if den else 0.0

    return {
        "district": {
            "id":   district_id,
            "name": district_row["name"],
        },
        "disease": disease,
        "cases_last_14d": recent["cases_last_14d"],
        "deaths_last_14d": recent["deaths_last_14d"],
        "baseline_avg":    round(baseline, 2),
        "baseline_ratio":  round(baseline_ratio, 2),
        "weekly_trend_slope": round(slope, 2),
        "series":          series,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "trace_id":        str(audit.new_trace()),
    }
