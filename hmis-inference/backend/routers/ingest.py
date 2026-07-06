from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.database import Database
from backend.inference.bulk_ingest import perform_bulk_ingest
from backend.schemas import (
    DiseaseReportCreate,
    DiseaseReportResponse,
    DistrictCreate,
    DistrictResponse,
    FacilityMetricsCreate,
    FacilityMetricsResponse,
)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.post(
    "/district",
    response_model=DistrictResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new district",
)
async def create_district(district: DistrictCreate) -> DistrictResponse:
    query = """
        INSERT INTO districts (name, state, population, zone)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, state, population, zone, created_at
    """
    try:
        row = await Database.fetchrow(
            query, district.name, district.state, district.population, district.zone
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return DistrictResponse(
        id=str(row["id"]),
        name=row["name"],
        state=row["state"],
        population=row["population"],
        zone=row["zone"],
        created_at=row["created_at"].isoformat(),
    )


@router.post(
    "/disease_report",
    response_model=DiseaseReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new disease report",
)
async def create_disease_report(report: DiseaseReportCreate) -> DiseaseReportResponse:
    # Verify facility exists
    facility_check = await Database.fetchrow(
        "SELECT id FROM health_facilities WHERE id = $1", report.facility_id
    )
    if not facility_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility {report.facility_id} not found",
        )

    query = """
        INSERT INTO disease_reports (
            facility_id, disease_name, reported_date, case_count, deaths,
            age_group, severity
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, facility_id, disease_name, reported_date, case_count,
                  deaths, age_group, severity, created_at
    """
    try:
        row = await Database.fetchrow(
            query,
            UUID(report.facility_id),
            report.disease_name,
            report.reported_date,
            report.case_count,
            report.deaths,
            report.age_group,
            report.severity,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return DiseaseReportResponse(
        id=str(row["id"]),
        facility_id=str(row["facility_id"]),
        disease_name=row["disease_name"],
        reported_date=row["reported_date"],
        case_count=row["case_count"],
        deaths=row["deaths"],
        age_group=row["age_group"],
        severity=row["severity"],
        created_at=row["created_at"].isoformat(),
    )


@router.post(
    "/facility_metrics",
    response_model=FacilityMetricsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new facility metrics",
)
async def create_facility_metrics(
    metrics: FacilityMetricsCreate,
) -> FacilityMetricsResponse:
    # Verify facility exists
    facility_check = await Database.fetchrow(
        "SELECT id FROM health_facilities WHERE id = $1", metrics.facility_id
    )
    if not facility_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility {metrics.facility_id} not found",
        )

    query = """
        INSERT INTO facility_metrics (
            facility_id, reported_date, opd_visits, icu_occupancy_pct,
            bed_occupancy_pct, emergency_visits, maternal_deaths, deliveries
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, facility_id, reported_date, opd_visits, icu_occupancy_pct,
                  bed_occupancy_pct, emergency_visits, maternal_deaths, deliveries, created_at
    """
    try:
        row = await Database.fetchrow(
            query,
            UUID(metrics.facility_id),
            metrics.reported_date,
            metrics.opd_visits,
            metrics.icu_occupancy_pct,
            metrics.bed_occupancy_pct,
            metrics.emergency_visits,
            metrics.maternal_deaths,
            metrics.deliveries,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    return FacilityMetricsResponse(
        id=str(row["id"]),
        facility_id=str(row["facility_id"]),
        reported_date=row["reported_date"],
        opd_visits=row["opd_visits"],
        icu_occupancy_pct=row["icu_occupancy_pct"],
        bed_occupancy_pct=row["bed_occupancy_pct"],
        emergency_visits=row["emergency_visits"],
        maternal_deaths=row["maternal_deaths"],
        deliveries=row["deliveries"],
        created_at=row["created_at"].isoformat(),
    )

@router.post("/csv", summary="Bulk-ingest facility_metrics from a CSV body")
async def ingest_csv(request: Request) -> dict:
    """Parse + validate + insert. Returns a per-row report."""
    body = (await request.body()).decode("utf-8", errors="replace")
    if len(body) > 2_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="CSV body exceeds 2MB cap — split the upload.",
        )
    return await perform_bulk_ingest(body)


@router.get("/disease_reports", summary="List raw disease reports with filters")
async def list_disease_reports(
    facility_id: Optional[str] = Query(None),
    disease_name: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    conditions = []
    params: list = []
    idx = 1

    if facility_id:
        conditions.append(f"dr.facility_id = ${idx}")
        params.append(UUID(facility_id))
        idx += 1
    if disease_name:
        conditions.append(f"dr.disease_name = ${idx}")
        params.append(disease_name)
        idx += 1
    if district_id:
        conditions.append(f"hf.district_id = ${idx}")
        params.append(UUID(district_id))
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_q = f"""
        SELECT COUNT(*) FROM disease_reports dr
        JOIN health_facilities hf ON dr.facility_id = hf.id
        {where}
    """
    total = await Database.fetchval(count_q, *params)

    query = f"""
        SELECT dr.id, dr.facility_id, hf.name AS facility_name, hf.district_id,
               d.name AS district_name, dr.disease_name, dr.reported_date,
               dr.case_count, dr.deaths, dr.age_group, dr.severity, dr.created_at
        FROM disease_reports dr
        JOIN health_facilities hf ON dr.facility_id = hf.id
        JOIN districts d ON hf.district_id = d.id
        {where}
        ORDER BY dr.created_at DESC, dr.case_count DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """
    params.extend([limit, offset])
    rows = await Database.fetch(query, *params)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(r) for r in rows],
    }


@router.get("/facility_metrics", summary="List raw facility metrics with filters")
async def list_facility_metrics(
    facility_id: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    conditions = []
    params: list = []
    idx = 1

    if facility_id:
        conditions.append(f"fm.facility_id = ${idx}")
        params.append(UUID(facility_id))
        idx += 1
    if district_id:
        conditions.append(f"hf.district_id = ${idx}")
        params.append(UUID(district_id))
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_q = f"""
        SELECT COUNT(*) FROM facility_metrics fm
        JOIN health_facilities hf ON fm.facility_id = hf.id
        {where}
    """
    total = await Database.fetchval(count_q, *params)

    query = f"""
        SELECT fm.id, fm.facility_id, hf.name AS facility_name, hf.district_id,
               d.name AS district_name, fm.reported_date, fm.opd_visits,
               fm.icu_occupancy_pct, fm.bed_occupancy_pct, fm.emergency_visits,
               fm.maternal_deaths, fm.deliveries, fm.medicine_days_remaining,
               fm.staff_attendance_pct, fm.created_at
        FROM facility_metrics fm
        JOIN health_facilities hf ON fm.facility_id = hf.id
        JOIN districts d ON hf.district_id = d.id
        {where}
        ORDER BY fm.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """
    params.extend([limit, offset])
    rows = await Database.fetch(query, *params)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(r) for r in rows],
    }
