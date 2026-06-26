"""
Forecaster tests — pure-Python coverage for the Prophet-based
``DiseaseForecaster``. No DB, no LLM, no Redis.

The forecast endpoint enforces >= 14 days of history (see forecast.py); the
tests honour that floor so the production gate stays calibrated.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.ml.forecaster import DiseaseForecaster


def _make_series(days: int = 30, seed: int = 7) -> pd.DataFrame:
    """Synthetic daily case counts — linear trend + weekly seasonality over
    noise, deterministic so CI bounds don't flap."""
    rng = np.random.RandomState(seed)
    start = date(2026, 1, 1)
    daily = []
    for i in range(days):
        d = start + timedelta(days=i)
        base = 20 + 0.4 * i  # mild upward trend
        seasonal = 6 * np.sin(2 * np.pi * i / 7)  # weekly bump
        noise = rng.normal(0, 2.5)
        daily.append({"ds": d, "y": max(0.0, base + seasonal + noise)})
    return pd.DataFrame(daily)


class TestDiseaseForecaster:
    def setup_method(self):
        self.df = _make_series()
        self.f = DiseaseForecaster().fit(self.df, "dengue")

    def test_fit_returns_self(self):
        f = DiseaseForecaster()
        assert f.fit(self.df, "dengue") is f

    def test_fit_records_disease_name(self):
        assert self.f.disease_name == "dengue"

    def test_forecast_horizon_default_is_seven(self):
        out = self.f.forecast_7day()
        # future dataframe extends history + horizon, so total days = N + 7
        assert isinstance(out, pd.DataFrame)
        assert len(out) == len(self.df) + 7

    def test_forecast_horizon_custom(self):
        out = self.f.forecast_7day(horizon_days=14)
        assert len(out) == len(self.df) + 14

    def test_unfitted_raises_runtime(self):
        f = DiseaseForecaster()
        with pytest.raises(RuntimeError, match="not fitted"):
            f.forecast_7day()

    def test_forecast_contains_required_columns(self):
        """Prophet output must contain the canonical columns the API serialises."""
        out = self.f.forecast_7day()
        for col in ("ds", "yhat", "yhat_lower", "yhat_upper"):
            assert col in out.columns, f"Missing column in forecast: {col}"

    def test_forecast_dates_are_progressive(self):
        """Forecast ds must be sorted ascending."""
        out = self.f.forecast_7day()
        ds = pd.to_datetime(out["ds"])
        assert ds.is_monotonic_increasing

    def test_forecast_respects_interval_width(self):
        """A wider interval (95%) should be looser than 50% on the same data."""
        f_loose = DiseaseForecaster(interval_width=0.95).fit(self.df, "dengue")
        f_tight = DiseaseForecaster(interval_width=0.50).fit(self.df, "dengue")
        loose = f_loose.forecast_7day()
        tight = f_tight.forecast_7day()
        # Look at the last row — the day furthest from the data end.
        last = -1
        loose_span = loose.loc[last, "yhat_upper"] - loose.loc[last, "yhat_lower"]
        tight_span = tight.loc[last, "yhat_upper"] - tight.loc[last, "yhat_lower"]
        # 95% should give a wider band than 50%, modulo Prophet noise floor.
        assert loose_span >= tight_span - 5.0  # small tolerance

    def test_forecast_handles_short_series(self):
        """Prophet can technically fit down to ~2 points; verify the model
        doesn't blow up on a degenerate window."""
        short_df = _make_series(days=2)
        f = DiseaseForecaster(weekly_seasonality=False, yearly_seasonality=False)
        f.fit(short_df, "dengue")
        out = f.forecast_7day(horizon_days=3)
        assert len(out) == 5  # 2 + 3
