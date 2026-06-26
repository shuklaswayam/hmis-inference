"""
Risk Scoring Module for HMIS Inference System.
Combines deterministic rules engine output, ML anomaly scores,
and Z-score analysis to produce a unified priority ranking.
"""

from datetime import datetime
from typing import Optional


# Seasonal weight for vector-borne diseases during monsoon (July–October)
MONSOON_MONTHS = {7, 8, 9, 10}
SEASONAL_WEIGHT = 1.3

# Anomaly score thresholds
ANOMALY_THRESHOLD_HIGH = -0.2
ANOMALY_THRESHOLD_MEDIUM = -0.1

# Z-score threshold for priority escalation
ZSCORE_ESCALATION_THRESHOLD = 3.0

# Disease names affected by seasonal weighting
SEASONAL_DISEASES = {"dengue", "malaria", "chikungunya"}


class RiskScorer:
    """
    Combines rule-based flags, ML anomaly scores, and Z-score analysis
    into a unified risk priority.

    Priority logic:
        HIGH   — any HIGH-severity rule fired AND anomaly_score < -0.1
                 OR any Z-score > 3.0 with HIGH rule
        MEDIUM — any HIGH-severity rule fired OR anomaly_score < -0.2
                 OR any Z-score > 3.0
        LOW    — neither condition met
    """

    def __init__(self, current_date: Optional[datetime] = None):
        self.current_date = current_date or datetime.now()

    def score(
        self,
        rule_flags: list[dict],
        anomaly_score: float,
        disease_name: Optional[str] = None,
        z_score_results: Optional[dict] = None,
    ) -> dict:
        """
        Compute a unified risk score from rules, anomaly detection, and Z-scores.

        Args:
            rule_flags: List of triggered rules, each with at least 'severity' and 'rule_name'.
            anomaly_score: Float score from IsolationForest (negative = anomalous).
            disease_name: Optional disease name for seasonal weighting.
            z_score_results: Optional dict from AnomalyDetector.z_score_check().

        Returns:
            dict with priority_rank, combined_score, contributing_rules, z_score_summary
        """
        has_high_rule = any(
            r.get("severity", "").upper() == "HIGH" for r in rule_flags
        )

        # Check for extreme Z-scores
        has_extreme_z = False
        max_z_score = 0.0
        if z_score_results:
            for metric, info in z_score_results.items():
                z = abs(info.get("z_score", 0))
                if z > max_z_score:
                    max_z_score = z
                if z > ZSCORE_ESCALATION_THRESHOLD:
                    has_extreme_z = True

        # Base priority determination
        if has_high_rule and anomaly_score < ANOMALY_THRESHOLD_MEDIUM:
            priority = "HIGH"
        elif has_high_rule or anomaly_score < ANOMALY_THRESHOLD_HIGH:
            priority = "MEDIUM"
        else:
            priority = "LOW"

        # Z-score escalation: if any Z-score > 3.0, upgrade to at least MEDIUM
        if has_extreme_z and priority == "LOW":
            priority = "MEDIUM"
        # If extreme Z-score + HIGH rule → force HIGH
        if has_extreme_z and has_high_rule:
            priority = "HIGH"

        # Compute combined score
        rule_count = len(rule_flags)
        high_count = sum(1 for r in rule_flags if r.get("severity", "").upper() == "HIGH")
        medium_count = sum(1 for r in rule_flags if r.get("severity", "").upper() == "MEDIUM")

        combined_score = (anomaly_score * 0.4) + (high_count * 0.3) + (medium_count * 0.15) + (rule_count * 0.05)

        # Add Z-score contribution to combined score
        if max_z_score > 0:
            combined_score += (max_z_score * 0.1)

        # Apply seasonal weighting for monsoon months
        month = self.current_date.month
        if month in MONSOON_MONTHS and disease_name and disease_name.lower() in SEASONAL_DISEASES:
            combined_score *= SEASONAL_WEIGHT
            # Escalate priority if seasonal disease + already elevated risk
            if priority == "MEDIUM" and combined_score > 0.5:
                priority = "HIGH"

        contributing_rules = [
            {
                "rule_id": r.get("rule_id", ""),
                "rule_name": r.get("rule_name", ""),
                "severity": r.get("severity", ""),
            }
            for r in rule_flags
        ]

        # Build Z-score summary
        z_score_summary = {}
        if z_score_results:
            for metric, info in z_score_results.items():
                z_score_summary[metric] = {
                    "z_score": info.get("z_score", 0),
                    "is_anomalous": info.get("is_anomalous", False),
                }

        return {
            "priority_rank": priority,
            "combined_score": round(combined_score, 4),
            "contributing_rules": contributing_rules,
            "z_score_summary": z_score_summary,
        }
