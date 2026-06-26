from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DistrictCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    state: str = Field(..., min_length=1, max_length=100)
    population: Optional[int] = Field(None, ge=0)
    zone: Optional[str] = Field(None, max_length=50)


class DistrictResponse(BaseModel):
    id: str
    name: str
    state: str
    population: Optional[int] = None
    zone: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class HealthFacilityCreate(BaseModel):
    district_id: str
    name: str = Field(..., min_length=1, max_length=255)
    facility_type: str = Field(..., min_length=1, max_length=100)
    beds_total: Optional[int] = Field(None, ge=0)
    icu_beds: Optional[int] = Field(None, ge=0)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)


class HealthFacilityResponse(BaseModel):
    id: str
    district_id: str
    name: str
    facility_type: str
    beds_total: Optional[int] = None
    icu_beds: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class DiseaseReportCreate(BaseModel):
    facility_id: str
    disease_name: str = Field(..., min_length=1, max_length=255)
    reported_date: date
    case_count: int = Field(..., ge=0)
    deaths: int = Field(0, ge=0)
    age_group: Optional[str] = Field(None, max_length=50)
    severity: Optional[str] = Field(None, max_length=50)

    @field_validator("reported_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v


class DiseaseReportResponse(BaseModel):
    id: str
    facility_id: str
    disease_name: str
    reported_date: date
    case_count: int
    deaths: int
    age_group: Optional[str] = None
    severity: Optional[str] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class FacilityMetricsCreate(BaseModel):
    facility_id: str
    reported_date: date
    opd_visits: int = Field(0, ge=0)
    icu_occupancy_pct: Optional[float] = Field(None, ge=0, le=100)
    bed_occupancy_pct: Optional[float] = Field(None, ge=0, le=100)
    emergency_visits: int = Field(0, ge=0)
    maternal_deaths: int = Field(0, ge=0)
    deliveries: int = Field(0, ge=0)
    # Fields backing R008 (severe_stockout → CRITICAL) and R009
    # (staff_attendance_dip → LOW). Both optional — back-compat is preserved
    # for any existing callers that only POST the original six fields.
    medicine_days_remaining: Optional[float] = Field(None, ge=0)
    staff_attendance_pct: Optional[float] = Field(None, ge=0, le=100)

    @field_validator("reported_date", mode="before")
    @classmethod
    def parse_date(cls, v):
        if isinstance(v, str):
            return date.fromisoformat(v)
        return v


class FacilityMetricsResponse(BaseModel):
    id: str
    facility_id: str
    reported_date: date
    opd_visits: int
    icu_occupancy_pct: Optional[float] = None
    bed_occupancy_pct: Optional[float] = None
    emergency_visits: int
    maternal_deaths: int
    deliveries: int
    medicine_days_remaining: Optional[float] = None
    staff_attendance_pct: Optional[float] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)