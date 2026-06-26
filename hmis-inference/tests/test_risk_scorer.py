"""
Unit tests for the HMIS Risk Scoring Module.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ml.risk_scorer import RiskScorer


def test_high_priority_high_rule_and_anomaly():
    """HIGH rule + anomalous score → HIGH priority."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))
    rule_flags = [{"rule_id": "R001", "rule_name": "icu_overload", "severity": "HIGH"}]
    result = scorer.score(rule_flags, anomaly_score=-0.15)
    assert result["priority_rank"] == "HIGH"
    assert len(result["contributing_rules"]) == 1


def test_medium_priority_high_rule_only():
    """HIGH rule fired but anomaly score is normal → MEDIUM priority."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))
    rule_flags = [{"rule_id": "R005", "rule_name": "maternal_cluster", "severity": "HIGH"}]
    result = scorer.score(rule_flags, anomaly_score=0.0)
    assert result["priority_rank"] == "MEDIUM"


def test_medium_priority_anomaly_only():
    """No HIGH rules, but anomaly score < -0.2 → MEDIUM priority."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))
    rule_flags = [{"rule_id": "R007", "rule_name": "opd_surge", "severity": "MEDIUM"}]
    result = scorer.score(rule_flags, anomaly_score=-0.3)
    assert result["priority_rank"] == "MEDIUM"


def test_low_priority_no_high_rules_normal_anomaly():
    """No HIGH rules and normal anomaly score → LOW priority."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))
    rule_flags = [{"rule_id": "R007", "rule_name": "opd_surge", "severity": "MEDIUM"}]
    result = scorer.score(rule_flags, anomaly_score=0.1)
    assert result["priority_rank"] == "LOW"


def test_low_priority_no_rules():
    """No rules triggered and normal anomaly score → LOW priority."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))
    result = scorer.score([], anomaly_score=0.2)
    assert result["priority_rank"] == "LOW"
    assert result["combined_score"] < 0.1


def test_seasonal_weight_applied_during_monsoon():
    """Dengue during monsoon months gets seasonal weight applied."""
    scorer = RiskScorer(current_date=datetime(2026, 8, 15))  # August = monsoon
    rule_flags = [{"rule_id": "R004", "rule_name": "outbreak", "severity": "HIGH"}]

    # Without disease name
    result_no_season = scorer.score(rule_flags, anomaly_score=-0.05, disease_name=None)
    # With dengue
    result_season = scorer.score(rule_flags, anomaly_score=-0.05, disease_name="Dengue")

    assert result_season["combined_score"] > result_no_season["combined_score"]


def test_combined_score_increases_with_more_rules():
    """More triggered rules should produce a higher combined score."""
    scorer = RiskScorer(current_date=datetime(2026, 3, 1))

    one_rule = [{"rule_id": "R001", "rule_name": "icu_overload", "severity": "HIGH"}]
    three_rules = [
        {"rule_id": "R001", "rule_name": "icu_overload", "severity": "HIGH"},
        {"rule_id": "R002", "rule_name": "icu_critical", "severity": "HIGH"},
        {"rule_id": "R007", "rule_name": "opd_surge", "severity": "MEDIUM"},
    ]

    score_one = scorer.score(one_rule, anomaly_score=-0.1)
    score_three = scorer.score(three_rules, anomaly_score=-0.1)

    assert score_three["combined_score"] > score_one["combined_score"]
    assert len(score_three["contributing_rules"]) == 3
