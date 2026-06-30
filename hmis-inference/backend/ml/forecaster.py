"""
Disease + Facility-load Forecasting Module for HMIS Inference System.

``DiseaseForecaster`` forecasts daily case counts (Workstream 1's 7-day
projection used by the per-facility insight).

``FacilityLoadForecaster`` is an extension called by Workstream 2 — it
fits a Prophet model on a single facility's last-N-days facility_metrics
and produces a 48-hour ICU + bed occupancy projection with confidence
intervals (per premise §6.1 — Hospital Pressure Classifier).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from prophet import Prophet


# ---------------------------------------------------------------------------
# Disease case forecaster (existing; preserved verbatim for back-compat)
# ---------------------------------------------------------------------------
class DiseaseForecaster:
    def __init__(
        self,
        weekly_seasonality: bool = True,
        yearly_seasonality: bool = True,
        interval_width: float = 0.95,
    ) -> None:
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        self.interval_width = interval_width
        self.model: Optional[Prophet] = None
        self.disease_name: Optional[str] = None

    def fit(self, data: pd.DataFrame, disease_name: str) -> "DiseaseForecaster":
        self.disease_name = disease_name
        self.model = Prophet(
            weekly_seasonality=self.weekly_seasonality,
            yearly_seasonality=self.yearly_seasonality,
            interval_width=self.interval_width,
            daily_seasonality=False,
        )
        self.model.fit(data)
        return self

    def forecast_7day(self, horizon_days: int = 7) -> list[dict]:
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        future = self.model.make_future_dataframe(periods=horizon_days)
        forecast = self.model.predict(future)
        future_only = forecast.tail(horizon_days)
        return [
            {
                "ds": row["ds"].strftime("%Y-%m-%d"),
                "yhat": round(float(row["yhat"]), 2),
                "yhat_lower": round(float(row["yhat_lower"]), 2),
                "yhat_upper": round(float(row["yhat_upper"]), 2),
            }
            for _, row in future_only.iterrows()
        ]

    def forecast(self, horizon_days: int = 7) -> pd.DataFrame:
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        future = self.model.make_future_dataframe(periods=horizon_days)
        return self.model.predict(future)


# ---------------------------------------------------------------------------
# Facility-load forecaster (Workstream 2 — 48-hour ICU/bed projection)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FacilityLoadProjection:
    horizon_days: int
    series: list[dict]            # [{ds, icu_yhat, bed_yhat, ...}]
    trend: str                    # "rising" / "stable" / "easing"
    icu_pred_24h: float
    icu_pred_48h: float
    bed_pred_48h: float


class FacilityLoadForecaster:
    """Project ICU + bed occupancy 48 hours ahead for one facility.

    Uses Prophet on concatenated ("ds", "y") frames — one series for
    icu_occupancy_pct, one for bed_occupancy_pct.
    """

    def __init__(
        self,
        weekly_seasonality: bool = True,
        yearly_seasonality: bool = False,
        interval_width: float = 0.95,
    ) -> None:
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        self.interval_width = interval_width

    def fit_and_forecast(
        self,
        icu_series: pd.DataFrame,
        bed_series: pd.DataFrame,
        *,
        horizon_days: int = 2,
    ) -> FacilityLoadProjection:
        """Fit two Projhet models and return their forward projection.

        ``icu_series`` and ``bed_series`` must each contain columns
        ``ds`` (Timestamp-like) and ``y`` (float, percentage 0-100).
        """
        if icu_series.empty or bed_series.empty:
            raise ValueError("Forecaster requires non-empty series.")
        icu_model = self._fit(icu_series)
        bed_model = self._fit(bed_series)
        icu_fc = self._tail(icu_model, horizon_days)
        bed_fc = self._tail(bed_model, horizon_days)

        # Trend classification: rising if most-recent yhat > first yhat
        # by >= 2 percentage points (over the horizon); easing if it
        # drops by >= 2; otherwise stable. Use ``.iloc[i]`` so we read
        # rows positionally — ``df[i]`` is a column lookup and breaks
        # against Prophet's frame (KeyError: 0).
        icu_first = float(icu_fc.iloc[0]["yhat"])
        icu_last = float(icu_fc.iloc[-1]["yhat"])
        if icu_last - icu_first >= 2.0:
            trend = "rising"
        elif icu_first - icu_last >= 2.0:
            trend = "easing"
        else:
            trend = "stable"

        # 24h point — pad horizon=2 with one more day for a clean 24h number
        icu_pad = self._tail(icu_model, max(horizon_days, 2))
        return FacilityLoadProjection(
            horizon_days=horizon_days,
            series=[
                {
                    "ds": str(icu_fc.iloc[i]["ds"]),
                    "icu_yhat": float(icu_fc.iloc[i]["yhat"]),
                    "icu_lower": float(icu_fc.iloc[i]["yhat_lower"]),
                    "icu_upper": float(icu_fc.iloc[i]["yhat_upper"]),
                    "bed_yhat": float(bed_fc.iloc[i]["yhat"]),
                    "bed_lower": float(bed_fc.iloc[i]["yhat_lower"]),
                    "bed_upper": float(bed_fc.iloc[i]["yhat_upper"]),
                }
                for i in range(len(icu_fc))
            ],
            trend=trend,
            icu_pred_24h=float(icu_pad.iloc[1]["yhat"]) if len(icu_pad) >= 2 else float(icu_pad.iloc[0]["yhat"]),
            icu_pred_48h=float(icu_last),
            bed_pred_48h=float(bed_fc.iloc[-1]["yhat"]),
        )

    def _fit(self, df: pd.DataFrame) -> Prophet:
        ds = pd.to_datetime(df["ds"]).dt.tz_localize(None)
        model = Prophet(
            weekly_seasonality=self.weekly_seasonality,
            yearly_seasonality=self.yearly_seasonality,
            interval_width=self.interval_width,
            daily_seasonality=False,
        )
        fit_df = pd.DataFrame({"ds": ds, "y": df["y"].astype(float)})
        model.fit(fit_df)
        return model

    @staticmethod
    def _tail(model: Prophet, horizon_days: int) -> pd.DataFrame:
        future = model.make_future_dataframe(periods=horizon_days)
        forecast = model.predict(future)
        return forecast.tail(horizon_days).reset_index(drop=True)
