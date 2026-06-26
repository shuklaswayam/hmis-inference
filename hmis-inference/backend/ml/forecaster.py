"""
Disease Forecasting Module for HMIS Inference System.
Uses Facebook Prophet to forecast disease cases 7 days ahead.
"""

from typing import Optional

import pandas as pd
from prophet import Prophet


class DiseaseForecaster:
    """
    Prophet-based disease case forecaster.

    Forecasts daily case counts for a specific disease using
    historical time series data from the HMIS database.
    """

    def __init__(
        self,
        weekly_seasonality: bool = True,
        yearly_seasonality: bool = True,
        interval_width: float = 0.95,
    ):
        self.weekly_seasonality = weekly_seasonality
        self.yearly_seasonality = yearly_seasonality
        self.interval_width = interval_width
        self.model: Optional[Prophet] = None
        self.disease_name: Optional[str] = None

    def fit(self, data: pd.DataFrame, disease_name: str) -> "DiseaseForecaster":
        """
        Fit the Prophet model on historical disease data.

        Args:
            data: DataFrame with columns 'ds' (date) and 'y' (case count)
            disease_name: Name of the disease being modeled

        Returns:
            self for method chaining
        """
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
        """
        Generate a 7-day forecast.

        Args:
            horizon_days: Number of days to forecast (default 7)

        Returns:
            List of dicts with ds, yhat, yhat_lower, yhat_upper for each day
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        future = self.model.make_future_dataframe(periods=horizon_days)
        forecast = self.model.predict(future)

        future_only = forecast.tail(horizon_days)
        result = []
        for _, row in future_only.iterrows():
            result.append({
                "ds": row["ds"].strftime("%Y-%m-%d"),
                "yhat": round(float(row["yhat"]), 2),
                "yhat_lower": round(float(row["yhat_lower"]), 2),
                "yhat_upper": round(float(row["yhat_upper"]), 2),
            })

        return result

    def forecast(self, horizon_days: int = 7) -> pd.DataFrame:
        """
        Generate a forecast and return the full forecast DataFrame.

        Args:
            horizon_days: Number of days to forecast

        Returns:
            Full Prophet forecast DataFrame
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        future = self.model.make_future_dataframe(periods=horizon_days)
        return self.model.predict(future)
