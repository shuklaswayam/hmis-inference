"""Facilities router — list facilities with latest metrics."""
from typing import Optional

from fastapi import APIRouter, Query

from backend.database import Database

router = APIRouter(prefix="/api/v1/facilities", tags=["facilities"])


@router.get("/", summary="List all facilities with latest metrics")
async def list_facilities(
    district_id: Optional[str] = Query(None, description="Filter by district UUID"),
) -> list[dict]:
    conditions = []
    params = []
    idx = 1

    if district_id:
        conditions.append(f"hf.district_id = ${idx}")
        params.append(district_id)
        idx += 1

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT
            hf.id,
            hf.name,
            hf.facility_type,
            hf.beds_total,
            hf.icu_beds,
            hf.latitude,
            hf.longitude,
            d.name AS district_name,
            d.id AS district_id,
            fm.opd_visits,
            fm.icu_occupancy_pct,
            fm.bed_occupancy_pct,
            fm.emergency_visits,
            fm.maternal_deaths,
            fm.deliveries,
            fm.reported_date
        FROM health_facilities hf
        LEFT JOIN districts d ON d.id = hf.district_id
        LEFT JOIN LATERAL (
            SELECT opd_visits, icu_occupancy_pct, bed_occupancy_pct,
                   emergency_visits, maternal_deaths, deliveries, reported_date
            FROM facility_metrics
            WHERE facility_id = hf.id
            ORDER BY reported_date DESC
            LIMIT 1
        ) fm ON TRUE
        {where_clause}
        ORDER BY hf.name
    """
    rows = await Database.fetch(query, *params)

    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "facility_type": r["facility_type"],
            "beds_total": r["beds_total"],
            "icu_beds": r["icu_beds"],
            "latitude": float(r["latitude"]) if r["latitude"] else None,
            "longitude": float(r["longitude"]) if r["longitude"] else None,
            "district_name": r["district_name"] or "",
            "district_id": str(r["district_id"]) if r["district_id"] else None,
            "opd_visits": r["opd_visits"],
            "icu_occupancy_pct": float(r["icu_occupancy_pct"]) if r["icu_occupancy_pct"] else None,
            "bed_occupancy_pct": float(r["bed_occupancy_pct"]) if r["bed_occupancy_pct"] else None,
            "emergency_visits": r["emergency_visits"],
            "maternal_deaths": r["maternal_deaths"],
            "deliveries": r["deliveries"],
            "reported_date": r["reported_date"].isoformat() if r["reported_date"] else None,
        }
        for r in rows
    ]


@router.get("/summary", summary="Get facilities summary stats")
async def facilities_summary() -> dict:
    row = await Database.fetchrow("""
        SELECT
            COUNT(*) AS total,
            COUNT(DISTINCT hf.district_id) AS districts,
            SUM(hf.beds_total) AS total_beds,
            SUM(hf.icu_beds) AS total_icu_beds
        FROM health_facilities hf
    """)
    latest = await Database.fetchrow("""
        SELECT
            AVG(fm.bed_occupancy_pct) AS avg_bed_occ,
            AVG(fm.icu_occupancy_pct) AS avg_icu_occ,
            SUM(fm.opd_visits) AS total_opd,
            SUM(fm.emergency_visits) AS total_emergency
        FROM facility_metrics fm
        WHERE fm.reported_date >= CURRENT_DATE - INTERVAL '7 days'
    """)
    return {
        "total_facilities": row["total"] if row else 0,
        "total_districts": row["districts"] if row else 0,
        "total_beds": row["total_beds"] if row else 0,
        "total_icu_beds": row["total_icu_beds"] if row else 0,
        "avg_bed_occupancy": round(float(latest["avg_bed_occ"] or 0), 1) if latest else 0,
        "avg_icu_occupancy": round(float(latest["avg_icu_occ"] or 0), 1) if latest else 0,
        "total_opd_7d": latest["total_opd"] if latest else 0,
        "total_emergency_7d": latest["total_emergency"] if latest else 0,
    }
