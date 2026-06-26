"""Metrics router — facility metric trends over time."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.database import Database

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

VALID_METRICS = [
    "opd_visits",
    "icu_occupancy_pct",
    "bed_occupancy_pct",
    "emergency_visits",
    "maternal_deaths",
    "deliveries",
]


@router.get(
    "/trend",
    summary="Get metric trend for a facility",
    description="Returns daily values for a given metric over the last N days.",
)
async def get_metric_trend(
    facility_id: str = Query(..., description="Facility UUID"),
    metric: str = Query(..., description=f"Metric name: {', '.join(VALID_METRICS)}"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
) -> list[dict]:
    if metric not in VALID_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric '{metric}'. Valid options: {', '.join(VALID_METRICS)}",
        )

    rows = await Database.fetch(
        """
        SELECT
            fm.reported_date,
            fm.%s AS value,
            hf.name AS facility_name
        FROM facility_metrics fm
        JOIN health_facilities hf ON hf.id = fm.facility_id
        WHERE fm.facility_id = $1
          AND fm.reported_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY fm.reported_date ASC
        """
        % (metric, days),
        facility_id,
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for facility_id={facility_id} metric={metric}",
        )

    return [
        {
            "date": r["reported_date"].isoformat(),
            "value": float(r["value"]) if r["value"] is not None else 0,
            "facility_name": r["facility_name"],
        }
        for r in rows
    ]
