"""
Anomaly Detection Module for HMIS Inference System.
Uses IsolationForest and Z-score analysis to detect anomalous facility metrics.
"""

import os
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import IsolationForest


FEATURES = [
    "opd_visits",
    "icu_occupancy_pct",
    "case_count",
    "emergency_visits",
]

ZSCORE_METRICS = ["opd_visits", "icu_occupancy_pct", "case_count"]

ZSCORE_THRESHOLD = 2.5

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "isolation_forest.pkl"


class AnomalyDetector:
    """
    IsolationForest-based anomaly detector for HMIS facility metrics.

    The model learns normal patterns from historical data and assigns
    anomaly scores. Negative scores indicate anomalous observations.
    """

    def __init__(self, contamination: float = 0.1, random_state: int = 42, n_estimators: int = 100):
        self.contamination = contamination
        self.random_state = random_state
        self.n_estimators = n_estimators
        self.model: Optional[IsolationForest] = None
        self.feature_names = FEATURES
        self._is_fitted = False

    def fit(self, data: pd.DataFrame) -> "AnomalyDetector":
        """
        Train the IsolationForest model on historical data.

        Args:
            data: DataFrame with columns matching FEATURES list.
                  Can contain additional columns (they will be ignored).

        Returns:
            self for method chaining.
        """
        X = data[self.feature_names].values

        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=self.random_state,
            n_estimators=self.n_estimators,
        )
        self.model.fit(X)
        self._is_fitted = True

        return self

    def score(self, current_metrics: dict) -> float:
        """
        Score a single observation against the trained model.

        Args:
            current_metrics: Dictionary with feature values.
                Required keys: opd_visits, icu_occupancy_pct, case_count, emergency_visits

        Returns:
            float: Anomaly score. Negative = anomalous, positive = normal.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.array([[current_metrics.get(f, 0) for f in self.feature_names]])
        score = self.model.score_samples(X)[0]
        return float(score)

    def predict(self, current_metrics: dict) -> int:
        """
        Predict if a single observation is anomalous.

        Args:
            current_metrics: Dictionary with feature values.

        Returns:
            int: -1 if anomalous, 1 if normal.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.array([[current_metrics.get(f, 0) for f in self.feature_names]])
        prediction = self.model.predict(X)[0]
        return int(prediction)

    def save(self, path: Optional[str] = None) -> Path:
        """
        Save the trained model to disk.

        Args:
            path: Optional custom path. Defaults to models/isolation_forest.pkl

        Returns:
            Path to the saved model file.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        save_path = Path(path) if path else MODEL_PATH
        save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, save_path)
        return save_path

    def load(self, path: Optional[str] = None) -> "AnomalyDetector":
        """
        Load a trained model from disk.

        Args:
            path: Optional custom path. Defaults to models/isolation_forest.pkl

        Returns:
            self for method chaining.
        """
        load_path = Path(path) if path else MODEL_PATH
        if not load_path.exists():
            raise FileNotFoundError(f"Model file not found: {load_path}")

        self.model = joblib.load(load_path)
        self._is_fitted = True
        return self

    @staticmethod
    def z_score_check(
        current_metrics: dict,
        historical_data: pd.DataFrame,
        threshold: float = ZSCORE_THRESHOLD,
    ) -> dict:
        """
        Compute Z-scores for current metrics against last 30 days of historical data.

        Args:
            current_metrics: Dictionary with current metric values.
            historical_data: DataFrame with columns matching ZSCORE_METRICS.
                Should contain at least 2 rows for meaningful std computation.
            threshold: Z-score threshold for flagging anomalies (default 2.5).

        Returns:
            dict: {metric_name: {z_score, is_anomalous, percentile}} for each metric.
        """
        results = {}

        for metric in ZSCORE_METRICS:
            current_val = current_metrics.get(metric, 0)

            if metric not in historical_data.columns:
                results[metric] = {
                    "z_score": 0.0,
                    "is_anomalous": False,
                    "percentile": 50,
                }
                continue

            hist_values = historical_data[metric].dropna().values
            if len(hist_values) < 2:
                results[metric] = {
                    "z_score": 0.0,
                    "is_anomalous": False,
                    "percentile": 50,
                }
                continue

            mean = np.mean(hist_values)
            std = np.std(hist_values, ddof=1)

            if std == 0:
                z_score = 0.0
            else:
                z_score = float((current_val - mean) / std)

            percentile = int(stats.percentileofscore(hist_values, current_val))

            results[metric] = {
                "z_score": round(z_score, 4),
                "is_anomalous": abs(z_score) > threshold,
                "percentile": percentile,
            }

        return results
