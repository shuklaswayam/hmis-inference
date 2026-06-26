"""
Unit tests for the HMIS Anomaly Detection Module.
"""

import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ml.anomaly import AnomalyDetector, FEATURES


def _make_sample_data(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic training data for tests."""
    rng = np.random.RandomState(seed)
    data = {
        "opd_visits": rng.normal(200, 40, n).clip(50, 500).astype(int),
        "icu_occupancy_pct": rng.normal(60, 15, n).clip(10, 100),
        "case_count": rng.poisson(15, n).clip(0, 200),
        "emergency_visits": rng.normal(40, 10, n).clip(5, 150).astype(int),
    }
    return pd.DataFrame(data)


@pytest.fixture
def detector():
    """Create and fit a detector with synthetic data."""
    df = _make_sample_data()
    det = AnomalyDetector(contamination=0.1, random_state=42, n_estimators=50)
    det.fit(df)
    return det


def test_score_normal_data_returns_positive(detector):
    """Normal data should score above the model's anomaly threshold."""
    normal = {
        "opd_visits": 200,
        "icu_occupancy_pct": 55.0,
        "case_count": 12,
        "emergency_visits": 35,
    }
    score = detector.score(normal)
    threshold = detector.model.offset_
    assert score > threshold, f"Expected score ({score}) > threshold ({threshold}) for normal data"


def test_score_extreme_data_returns_negative(detector):
    """Extreme/anomalous data should have a negative anomaly score."""
    extreme = {
        "opd_visits": 500,
        "icu_occupancy_pct": 99.0,
        "case_count": 200,
        "emergency_visits": 200,
    }
    score = detector.score(extreme)
    assert score < 0, f"Expected negative score for extreme data, got {score}"


def test_score_moderate_data(detector):
    """Moderately abnormal data should score between extreme and normal."""
    normal_score = detector.score({
        "opd_visits": 200,
        "icu_occupancy_pct": 55.0,
        "case_count": 12,
        "emergency_visits": 35,
    })
    extreme_score = detector.score({
        "opd_visits": 500,
        "icu_occupancy_pct": 99.0,
        "case_count": 200,
        "emergency_visits": 200,
    })
    moderate_score = detector.score({
        "opd_visits": 350,
        "icu_occupancy_pct": 85.0,
        "case_count": 80,
        "emergency_visits": 100,
    })
    assert extreme_score < moderate_score < normal_score


def test_predict_anomalous(detector):
    """Predict should return -1 for anomalous data."""
    extreme = {
        "opd_visits": 500,
        "icu_occupancy_pct": 99.0,
        "case_count": 200,
        "emergency_visits": 200,
    }
    prediction = detector.predict(extreme)
    assert prediction == -1


def test_predict_normal(detector):
    """Predict should return 1 for normal data."""
    normal = {
        "opd_visits": 200,
        "icu_occupancy_pct": 55.0,
        "case_count": 12,
        "emergency_visits": 35,
    }
    prediction = detector.predict(normal)
    assert prediction == 1


def test_save_and_load(tmp_path, detector):
    """Model should save and load correctly."""
    model_path = tmp_path / "test_model.pkl"
    detector.save(str(model_path))
    assert model_path.exists()

    loaded_detector = AnomalyDetector()
    loaded_detector.load(str(model_path))

    original_score = detector.score({"opd_visits": 200, "icu_occupancy_pct": 55.0, "case_count": 12, "emergency_visits": 35})
    loaded_score = loaded_detector.score({"opd_visits": 200, "icu_occupancy_pct": 55.0, "case_count": 12, "emergency_visits": 35})
    assert abs(original_score - loaded_score) < 1e-10


def test_unfitted_raises_error():
    """Calling score on unfitted detector should raise RuntimeError."""
    detector = AnomalyDetector()
    with pytest.raises(RuntimeError, match="Model not fitted"):
        detector.score({"opd_visits": 200})


# --- Z-Score Tests ---


def _make_historical_data(n: int = 30, seed: int = 42) -> pd.DataFrame:
    """Generate 30-day historical data with known distribution."""
    rng = np.random.RandomState(seed)
    data = {
        "opd_visits": rng.normal(200, 30, n).clip(50, 500).astype(int),
        "icu_occupancy_pct": rng.normal(60, 10, n).clip(10, 100),
        "case_count": rng.poisson(15, n).clip(0, 200),
    }
    return pd.DataFrame(data)


def test_z_score_normal_value_returns_low_z():
    """A value near the historical mean should have a low Z-score."""
    hist = _make_historical_data()
    current = {
        "opd_visits": 200,
        "icu_occupancy_pct": 60.0,
        "case_count": 15,
    }
    results = AnomalyDetector.z_score_check(current, hist)
    for metric in ["opd_visits", "icu_occupancy_pct", "case_count"]:
        assert abs(results[metric]["z_score"]) < 2.5, (
            f"Expected low Z-score for {metric}, got {results[metric]['z_score']}"
        )
        assert results[metric]["is_anomalous"] is False


def test_z_score_extreme_value_returns_high_z():
    """A value far from the historical mean should be flagged anomalous."""
    hist = _make_historical_data()
    current = {
        "opd_visits": 400,  # ~6.7 std deviations above mean
        "icu_occupancy_pct": 99.0,  # ~3.9 std deviations above mean
        "case_count": 80,  # ~12 std deviations above mean
    }
    results = AnomalyDetector.z_score_check(current, hist)
    for metric in ["opd_visits", "icu_occupancy_pct", "case_count"]:
        assert results[metric]["is_anomalous"] is True, (
            f"Expected {metric} to be flagged anomalous, got z={results[metric]['z_score']}"
        )
        assert abs(results[metric]["z_score"]) > 2.5


def test_z_score_percentile_ranking():
    """Percentile should reflect relative position in historical distribution."""
    hist = _make_historical_data()
    current = {
        "opd_visits": 200,
        "icu_occupancy_pct": 60.0,
        "case_count": 15,
    }
    results = AnomalyDetector.z_score_check(current, hist)
    for metric in ["opd_visits", "icu_occupancy_pct", "case_count"]:
        p = results[metric]["percentile"]
        assert 0 <= p <= 100, f"Percentile out of range for {metric}: {p}"
