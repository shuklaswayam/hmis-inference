"""Outbreak classifier — lightweight ML (per premise §6.1).

Trained on HMIS ``disease_reports``: features are the same deterministic
inputs the rule engine uses (cases / baseline ratio / deaths / weekly
slope), with the tier label provided by the deterministic rule thresholds
themselves. scikit-learn's ``DecisionTreeClassifier`` keeps the model
tiny and interpretable; class probabilities are surfaced as confidence.

If the pickled model is missing, the loader raises ``FileNotFoundError``
and the calling workstream falls back to rule-only (confidence=0.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
from sklearn.tree import DecisionTreeClassifier

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "outbreak_classifier.pkl"

FEATURES = [
    "cases_last_14d",
    "baseline_ratio",
    "deaths_last_14d",
    "weekly_trend_slope",
    "district_z",
]

LABELS = ["Low", "Medium", "High", "Critical"]


@dataclass(frozen=True)
class OutbreakPrediction:
    tier: str
    confidence: float
    probabilities: dict[str, float]


def _to_vector(features: dict[str, Any]) -> np.ndarray:
    return np.array([[float(features.get(f, 0.0)) for f in FEATURES]])


class OutbreakClassifier:
    def __init__(self, max_depth: int = 6, random_state: int = 42) -> None:
        self.max_depth = max_depth
        self.random_state = random_state
        self._model: DecisionTreeClassifier | None = None
        self._fitted = False

    def fit(
        self,
        rows: Iterable[dict[str, Any]],
        labels: Iterable[str],
    ) -> "OutbreakClassifier":
        X = np.array(
            [
                [float(r.get(f, 0.0)) for f in FEATURES]
                for r in rows
            ]
        )
        y = list(labels)
        self._model = DecisionTreeClassifier(
            max_depth=self.max_depth,
            random_state=self.random_state,
            class_weight="balanced",
        )
        self._model.fit(X, y)
        self._fitted = True
        return self

    def predict(self, features: dict[str, Any]) -> OutbreakPrediction:
        if not self._fitted or self._model is None:
            raise RuntimeError("OutbreakClassifier not fitted. Call fit() first.")
        X = _to_vector(features)
        proba = self._model.predict_proba(X)[0]
        classes = list(self._model.classes_)
        probs = {str(c): float(p) for c, p in zip(classes, proba)}
        tier = str(self._model.predict(X)[0])
        confidence = float(probs.get(tier, 0.0))
        return OutbreakPrediction(tier=tier, confidence=confidence, probabilities=probs)

    def save(self, path: str | Path | None = None) -> Path:
        if not self._fitted or self._model is None:
            raise RuntimeError("OutbreakClassifier not fitted.")
        target = Path(path) if path else MODEL_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self._model, target)
        return target

    def load(self, path: str | Path | None = None) -> "OutbreakClassifier":
        target = Path(path) if path else MODEL_PATH
        if not target.exists():
            raise FileNotFoundError(f"Outbreak classifier model missing: {target}")
        self._model = joblib.load(target)
        self._fitted = True
        return self
