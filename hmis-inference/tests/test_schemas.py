"""
Pydantic schema validation tests.

Schemas are the contract between ingest endpoint and DB; a relaxed validator
lets bad rows slip past and explode during inference. Tests exercise:

    * required fields + length limits
    * ge / le range bounds (population, occupancy %, latitude/longitude)
    * validators — reported_date parses ISO strings gracefully
    * negative paths — empty names, out-of-range values
"""
from datetime import date

import pytest
from pydantic import ValidationError

from backend.schemas import (
    DistrictCreate,
    DistrictResponse,
    DiseaseReportCreate,
    DiseaseReportResponse,
    HealthFacilityCreate,
    HealthFacilityResponse,
    FacilityMetricsCreate,
    FacilityMetricsResponse,
)


# ─────────────────────────────────────────────────────────────────────────────
# DistrictCreate — required strings, ge=0 on population
# ─────────────────────────────────────────────────────────────────────────────
class TestDistrictCreate:
    def test_minimal_valid(self):
        d = DistrictCreate(name="Anand", state="Gujarat")
        assert d.name == "Anand"
        assert d.population is None
        assert d.zone is None

    def test_full_valid(self):
        d = DistrictCreate(
            name="Surat", state="Gujarat", population=6_000_000, zone="South",
        )
        assert d.population == 6_000_000
        assert d.zone == "South"

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError) as exc:
            DistrictCreate(name="", state="Gujarat")
        # Should mention the min_length=1 constraint somewhere.
        assert "at least 1 character" in str(exc.value).lower() or "min_length" in str(exc.value)

    def test_negative_population_rejected(self):
        with pytest.raises(ValidationError):
            DistrictCreate(name="X", state="Y", population=-1)

    def test_oversized_name_rejected(self):
        with pytest.raises(ValidationError):
            DistrictCreate(name="x" * 300, state="Y")


# ─────────────────────────────────────────────────────────────────────────────
# HealthFacilityCreate — coords bounded, beds nonnegative
# ─────────────────────────────────────────────────────────────────────────────
class TestHealthFacilityCreate:
    def test_valid_facility(self):
        f = HealthFacilityCreate(
            district_id="ad-uuid-here",
            name="CHC Amreli",
            facility_type="Community Health Centre",
            beds_total=30,
            icu_beds=4,
            latitude=21.62,
            longitude=71.23,
        )
        assert f.beds_total == 30

    def test_latitude_out_of_range(self):
        with pytest.raises(ValidationError):
            HealthFacilityCreate(
                district_id="x", name="x", facility_type="x",
                latitude=120.0, longitude=0.0,
            )

    def test_longitude_out_of_range(self):
        with pytest.raises(ValidationError):
            HealthFacilityCreate(
                district_id="x", name="x", facility_type="x",
                latitude=0.0, longitude=-200.0,
            )

    def test_negative_beds_rejected(self):
        with pytest.raises(ValidationError):
            HealthFacilityCreate(
                district_id="x", name="x", facility_type="x",
                beds_total=-5,
            )


# ─────────────────────────────────────────────────────────────────────────────
# DiseaseReportCreate — date parsing, case_count ge=0
# ─────────────────────────────────────────────────────────────────────────────
class TestDiseaseReportCreate:
    def test_iso_date_string_parses(self):
        r = DiseaseReportCreate(
            facility_id="fac-uuid",
            disease_name="Dengue",
            reported_date="2026-06-24",
            case_count=12,
        )
        assert r.reported_date == date(2026, 6, 24)

    def test_date_passes_through_when_date_object(self):
        r = DiseaseReportCreate(
            facility_id="fac-uuid",
            disease_name="Dengue",
            reported_date=date(2026, 6, 24),
            case_count=12,
        )
        assert r.reported_date == date(2026, 6, 24)

    def test_negative_case_count_rejected(self):
        with pytest.raises(ValidationError):
            DiseaseReportCreate(
                facility_id="x", disease_name="x",
                reported_date="2026-06-24", case_count=-1,
            )

    def test_default_deaths_zero(self):
        r = DiseaseReportCreate(
            facility_id="x", disease_name="x",
            reported_date="2026-06-24", case_count=5,
        )
        assert r.deaths == 0


# ─────────────────────────────────────────────────────────────────────────────
# FacilityMetricsCreate — optional occupancy %, count fields default to 0
# ─────────────────────────────────────────────────────────────────────────────
class TestFacilityMetricsCreate:
    def test_minimal_defaults(self):
        m = FacilityMetricsCreate(
            facility_id="fac-uuid", reported_date="2026-06-24",
        )
        assert m.opd_visits == 0
        assert m.emergency_visits == 0
        assert m.maternal_deaths == 0
        assert m.icu_occupancy_pct is None

    def test_occupancy_above_100_rejected(self):
        with pytest.raises(ValidationError):
            FacilityMetricsCreate(
                facility_id="x", reported_date="2026-06-24",
                icu_occupancy_pct=150.0,
            )

    def test_new_optional_fields_recognised(self):
        """Back-compat: medicine_days_remaining + staff_attendance_pct —
        optional, only present on metrics rows from >= 002 migration."""
        m = FacilityMetricsCreate(
            facility_id="x", reported_date="2026-06-24",
            medicine_days_remaining=2.5,
            staff_attendance_pct=45.0,
        )
        assert m.medicine_days_remaining == 2.5
        assert m.staff_attendance_pct == 45.0

    def test_response_model_round_trip(self):
        m = FacilityMetricsCreate(
            facility_id="x", reported_date="2026-06-24",
            opd_visits=200, icu_occupancy_pct=70.0,
        )
        resp = FacilityMetricsResponse(
            id="row-uuid",
            facility_id=m.facility_id,
            reported_date=m.reported_date,
            opd_visits=m.opd_visits,
            icu_occupancy_pct=m.icu_occupancy_pct,
            bed_occupancy_pct=None,
            emergency_visits=0,
            maternal_deaths=0,
            deliveries=0,
            created_at="2026-06-24T00:00:00",
        )
        assert resp.opd_visits == 200
