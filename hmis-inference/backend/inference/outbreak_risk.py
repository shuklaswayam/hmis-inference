"""Workstream 1 — Outbreak Risk Scorer.

Per-ward × per-disease 4-tier classification with confidence level.
Rule-augmented scoring (per premise §6.1):

  1. Threshold rules (deterministic) pick the tier.
  2. ML classifier (decision tree) soft-corrects the tier if enough
     signal exists, and supplies a 0-1 confidence probability.
  3. Confidence is blended with a seasonality multiplier for
     vector-borne diseases in monsoon months.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional

import pandas as pd

from backend.database import Database
from backend.ml.outbreak_classifier import OutbreakClassifier, FEATURES

logger = logging.getLogger(__name__)


# Vector-borne diseases with monsoon seasonality.
MONSOON_MONTHS = {7, 8, 9, 10}
SEASONAL_DISEASES = {"dengue", "malaria", "chikungunya", "chickengunya"}


# Deterministic rule thresholds (tier overrides from raw signals).
@dataclass(frozen=True)
class TierRule:
    name: str
    min_baseline_ratio: float = 0.0
    requires_deaths_ge: int = 0


TIER_RULES = [
    TierRule("Critical", min_baseline_ratio=5.0, requires_deaths_ge=3),
    TierRule("High",     min_baseline_ratio=4.0, requires_deaths_ge=1),
    TierRule("Medium",   min_baseline_ratio=2.0),
    TierRule("Low",      min_baseline_ratio=0.0),
]


# Per-tier one-line policy action map.
TIER_ACTION = {
    "Low":      "Maintain routine surveillance; document today's readings.",
    "Medium":   "Issue ward containment advisory; verify accuracy of recent reports.",
    "High":     "Notify District Surveillance Officer; initiate containment protocol.",
    "Critical": "Trigger Commissioner-level alert; activate rapid response team.",
}


@dataclass(frozen=True)
class OutbreakRisk:
    district_id: str
    district_name: str
    disease_name: str
    tier: str
    confidence: float
    cases_last_14d: int
    baseline_ratio: float
    deaths_last_14d: int
    one_liner: str
    recommended_action: str
    contributing_signals: list[str]


async def _baseline_avg(
    disease_name: str,
    district_id: str,
    *,
    end_date: date,
    window_days: int = 30,
) -> float:
    """Compute mean daily case count for the disease in the district
    over the prior 30 days (before the last 14)."""
    start = end_date - timedelta(days=window_days + 14)
    cutoff = end_date - timedelta(days=14)
    row = await Database.fetchrow(
        """
        SELECT COALESCE(AVG(daily_cases), 0) AS baseline_avg
        FROM (
            SELECT dr.reported_date,
                   SUM(dr.case_count) AS daily_cases
            FROM disease_reports dr
            JOIN health_facilities hf ON hf.id = dr.facility_id
            WHERE dr.disease_name = $1
              AND hf.district_id = $2::uuid
              AND dr.reported_date >= $3
              AND dr.reported_date < $4
            GROUP BY dr.reported_date
        ) daily
        """,
        disease_name,
        district_id,
        start,
        cutoff,
    )
    return float(row["baseline_avg"]) if row else 0.0


async def _recent_window(
    disease_name: str,
    district_id: str,
    *,
    end_date: date,
    window_days: int = 14,
) -> dict:
    """Aggregate cases/deaths for the last N days and a per-day series."""
    start = end_date - timedelta(days=window_days)
    rows = await Database.fetch(
        """
        SELECT
            dr.reported_date,
            SUM(dr.case_count) AS cases,
            SUM(dr.deaths) AS deaths
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE dr.disease_name = $1
          AND hf.district_id = $2::uuid
          AND dr.reported_date >= $3
          AND dr.reported_date <= $4
        GROUP BY dr.reported_date
        ORDER BY dr.reported_date
        """,
        disease_name,
        district_id,
        start,
        end_date,
    )
    series = [int(r["cases"] or 0) for r in rows]
    deaths_sum = sum(int(r["deaths"] or 0) for r in rows)
    if len(series) < 2:
        slope = 0.0
    else:
        xs = list(range(len(series)))
        mean_x = sum(xs) / len(xs)
        mean_y = sum(series) / len(series)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series))
        den = sum((x - mean_x) ** 2 for x in xs)
        slope = num / den if den else 0.0
    return {
        "cases_last_14d": sum(series),
        "deaths_last_14d": deaths_sum,
        "weekly_trend_slope": float(slope),
    }


def _rule_tier(baseline_ratio: float, deaths: int) -> str:
    """Map baseline ratio + deaths to a tier.

    OR semantics on the two signals — any one of them hits the next
    tier (per the rule defined for the Workstream 1 spec):
        Critical: ratio ≥ 5× OR deaths ≥ 3
        High:     ratio ≥ 4× OR deaths ≥ 1
        Medium:   ratio ≥ 2×
        Low:      otherwise
    """
    if baseline_ratio >= 5.0 or deaths >= 3:
        return "Critical"
    if baseline_ratio >= 4.0 or deaths >= 1:
        return "High"
    if baseline_ratio >= 2.0:
        return "Medium"
    return "Low"


def _seasonality_multiplier(disease: str, when: datetime) -> float:
    if when.month in MONSOON_MONTHS and disease.strip().lower() in SEASONAL_DISEASES:
        return 1.2  # modest boost to confidence in monsoon window
    return 1.0


async def _district_choices(
    district_id: str,
    *,
    end_date: date,
    limit: int = 8,
) -> pd.DataFrame:
    """Top diseases by 30-day case count for the district."""
    rows = await Database.fetch(
        """
        SELECT dr.disease_name, SUM(dr.case_count) AS total
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE hf.district_id = $1::uuid
          AND dr.reported_date >= $2
        GROUP BY dr.disease_name
        ORDER BY total DESC
        LIMIT $3
        """,
        district_id,
        end_date - timedelta(days=30),
        limit,
    )
    return pd.DataFrame(
        [(r["disease_name"], int(r["total"] or 0)) for r in rows],
        columns=["disease_name", "total"],
    )


async def score(
    *,
    district_id: str | None = None,
    disease_name: str | None = None,
    end_date: Optional[date] = None,
) -> list[dict]:
    """Compute outbreak risk for one or all (district × disease) buckets.

    Filters:
      - district_id  : restrict to a single district (else all districts)
      - disease_name : restrict to a single disease (else top-N in each
                       district, by recent case volume)
    """
    end_date = end_date or date.today()
    district_ids = [district_id] if district_id else None

    if district_ids is None:
        rows = await Database.fetch("SELECT id, name FROM districts ORDER BY name")
        district_ids = [str(r["id"]) for r in rows]
        district_names = {str(r["id"]): r["name"] for r in rows}
    else:
        row = await Database.fetchrow(
            "SELECT id, name FROM districts WHERE id = $1::uuid", district_id
        )
        district_names = {district_id: row["name"] if row else ""}

    # Attempt to load the ML classifier — fall back to rule-only.
    classifier: OutbreakClassifier | None = None
    try:
        classifier = OutbreakClassifier().load()
    except FileNotFoundError:
        logger.info("Outbreak classifier absent — rule-only mode.")

    signals: list[dict] = []
    now = datetime.utcnow()

    for dist_id in district_ids:
        if disease_name:
            diseases = [(disease_name, 0)]
        else:
            df = await _district_choices(dist_id, end_date=end_date, limit=8)
            if df.empty:
                continue
            diseases = list(zip(df["disease_name"].tolist(), df["total"].tolist()))

        for disease, _total in diseases:
            baseline = await _baseline_avg(
                disease, dist_id, end_date=end_date
            )
            recent = await _recent_window(
                disease, dist_id, end_date=end_date
            )

            baseline_ratio = (
                (recent["cases_last_14d"] / 14.0) / baseline
                if baseline > 0
                else 0.0
            )
            rule_t = _rule_tier(baseline_ratio, recent["deaths_last_14d"])

            confidence = 0.5
            tier = rule_t

            if classifier is not None:
                features = {
                    "cases_last_14d": recent["cases_last_14d"],
                    "baseline_ratio": round(baseline_ratio, 4),
                    "deaths_last_14d": recent["deaths_last_14d"],
                    "weekly_trend_slope": round(recent["weekly_trend_slope"], 4),
                    "district_z": 0.0,
                }
                try:
                    pred = classifier.predict(features)
                    tier = pred.tier
                    confidence = pred.confidence
                except Exception:  # noqa: BLE001
                    confidence = 0.5

            confidence = min(1.0, confidence * _seasonality_multiplier(disease, now))

            contributing = [
                f"14-day cases = {recent['cases_last_14d']}",
                f"baseline ratio = {baseline_ratio:.2f}×",
                f"deaths = {recent['deaths_last_14d']}",
                f"trend slope = {recent['weekly_trend_slope']:+.2f}",
            ]
            one_liner = (
                f"{disease} in {district_names.get(dist_id, 'unknown')}: "
                f"{tier} ({baseline_ratio:.1f}× baseline)"
            )

            signals.append(
                {
                    "district_id": dist_id,
                    "district_name": district_names.get(dist_id, ""),
                    "disease_name": disease,
                    "tier": tier,
                    "confidence": round(confidence, 3),
                    "cases_last_14d": recent["cases_last_14d"],
                    "baseline_ratio": round(baseline_ratio, 3),
                    "deaths_last_14d": recent["deaths_last_14d"],
                    "one_liner": one_liner,
                    "recommended_action": TIER_ACTION.get(tier, ""),
                    "contributing_signals": contributing,
                }
            )

    return sorted(signals, key=lambda s: (-_tier_weight(s["tier"]), s["disease_name"]))


def _tier_weight(tier: str) -> int:
    return {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(tier, 0)


def aggregate_severity(signals: list[dict]) -> tuple[str, float]:
    """Pick the worst-severity tier across signals + mean confidence."""
    if not signals:
        return ("LOW", 0.0)
    rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    worst = max(signals, key=lambda s: rank.get(s["tier"], 0))
    sev = {"Critical": "CRITICAL", "High": "HIGH", "Medium": "MEDIUM", "Low": "LOW"}[worst["tier"]]
    return (sev, float(worst["confidence"]))
