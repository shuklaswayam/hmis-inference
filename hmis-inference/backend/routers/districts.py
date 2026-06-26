"""Districts router — list all districts and risk summaries."""
from fastapi import APIRouter

from backend.database import Database

router = APIRouter(prefix="/api/v1/districts", tags=["districts"])

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@router.get("/", summary="List all districts")
async def list_districts() -> list[dict]:
    rows = await Database.fetch(
        """
        SELECT id, name, state, population, zone
        FROM districts
        ORDER BY name
        """
    )
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "state": r["state"],
            "population": r["population"],
            "zone": r["zone"],
        }
        for r in rows
    ]


@router.get("/risk-summary", summary="Risk summary per district")
async def district_risk_summary() -> list[dict]:
    """
    Get the latest inference result per district with highest severity and alert count.

    Returns a list of districts with:
    - district_id: UUID of the district
    - district_name: name of the district
    - highest_severity: 'HIGH', 'MEDIUM', 'LOW', or 'NONE' if no alerts
    - alert_count: total number of active (non-expired) alerts for the district
    """
    rows = await Database.fetch(
        """
        WITH latest_per_district AS (
            SELECT DISTINCT ON (ir.district_id)
                ir.district_id,
                ir.severity,
                ir.created_at
            FROM inference_results ir
            WHERE ir.expires_at IS NULL
            ORDER BY ir.district_id, ir.created_at DESC
        ),
        alert_counts AS (
            SELECT
                ir.district_id,
                COUNT(*)::int AS alert_count
            FROM inference_results ir
            WHERE ir.expires_at IS NULL
            GROUP BY ir.district_id
        )
        SELECT
            d.id AS district_id,
            d.name AS district_name,
            COALESCE(lpd.severity, 'NONE') AS highest_severity,
            COALESCE(ac.alert_count, 0) AS alert_count
        FROM districts d
        LEFT JOIN latest_per_district lpd ON lpd.district_id = d.id
        LEFT JOIN alert_counts ac ON ac.district_id = d.id
        ORDER BY d.name
        """
    )

    return sorted(
        [
            {
                "district_id": str(r["district_id"]),
                "district_name": r["district_name"],
                "highest_severity": r["highest_severity"],
                "alert_count": r["alert_count"],
            }
            for r in rows
        ],
        key=lambda x: (SEVERITY_ORDER.get(x["highest_severity"], 3), x["district_name"]),
    )
