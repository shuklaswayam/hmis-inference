"""
FastAPI router for disease forecasting endpoints.
"""

import pandas as pd
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.database import Database
from backend.ml.forecaster import DiseaseForecaster


router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


class ForecastResponse(BaseModel):
    disease: str
    district_id: Optional[str] = None
    horizon_days: int
    generated_at: str
    forecast: list[dict]


async def _get_disease_data(
    disease_name: str,
    district_id: Optional[str] = None,
    days: int = 90,
) -> pd.DataFrame:
    """Fetch historical disease data from database."""
    conditions = ["disease_name = $1"]
    params = [disease_name]
    idx = 2

    if district_id:
        conditions.append(f"hf.district_id = ${idx}")
        params.append(district_id)
        idx += 1

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            dr.reported_date as ds,
            SUM(dr.case_count) as y
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE {where_clause}
        GROUP BY dr.reported_date
        ORDER BY dr.reported_date
        LIMIT {days}
    """
    rows = await Database.fetch(query, *params)

    df = pd.DataFrame(rows, columns=["ds", "y"])
    if df.empty:
        return df

    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    return df.sort_values("ds")


@router.get(
    "/{disease}",
    response_model=ForecastResponse,
    summary="Get 7-day disease forecast",
    description="Forecast disease cases for the next 7 days using Prophet",
)
async def get_forecast(
    disease: str,
    district_id: Optional[str] = Query(None, description="Filter by district UUID"),
    horizon_days: int = Query(7, ge=1, le=30, description="Number of days to forecast"),
) -> ForecastResponse:
    """
    Get disease forecast.

    - Fetches last 90 days of disease_reports from DB
    - Fits Prophet model with weekly/yearly seasonality
    - Returns 7-day forecast with confidence intervals
    """
    df = await _get_disease_data(disease, district_id, days=90)

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No historical data found for disease '{disease}'"
                  f"{' in district ' + district_id if district_id else ''}",
        )

    if len(df) < 14:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient data: need at least 14 days, got {len(df)}",
        )

    forecaster = DiseaseForecaster(
        weekly_seasonality=True,
        yearly_seasonality=True,
        interval_width=0.95,
    )
    forecaster.fit(df, disease)

    forecast = forecaster.forecast_7day(horizon_days)

    from datetime import datetime, timezone
    return ForecastResponse(
        disease=disease,
        district_id=district_id,
        horizon_days=horizon_days,
        generated_at=datetime.now(timezone.utc).isoformat(),
        forecast=forecast,
    )


