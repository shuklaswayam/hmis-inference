from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from backend.database import Database
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