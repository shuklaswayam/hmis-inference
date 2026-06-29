"""
Unit tests for Workstream 1 — Outbreak Risk Scorer.

We deliberately exercise only the pure-Python tier logic — DB-touching
helpers are covered in test_inference_router.py with mocks.
"""
import sys
from datetime import datetime, date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend.inference.outbreak_risk import (
    _rule_tier,
    _seasonality_multiplier,
    TIER_RULES,
    TIER_ACTION,
    aggregate_severity,
)


def test_rule_tier_low_when_baseline_ratio_is_zero():
    assert _rule_tier(baseline_ratio=0.5, deaths=0) == "Low"


def test_rule_tier_medium_when_baseline_ratio_above_2x():
    assert _rule_tier(baseline_ratio=2.0, deaths=0) == "Medium"


def test_rule_tier_high_when_baseline_above_4x():
    assert _rule_tier(baseline_ratio=4.0, deaths=0) == "High"


def test_rule_tier_critical_when_baseline_above_5x():
    assert _rule_tier(baseline_ratio=5.0, deaths=0) == "Critical"


def test_rule_tier_high_when_one_death_even_with_low_ratio():
    # Deaths > 0 forces at least High regardless of case ratio.
    assert _rule_tier(baseline_ratio=1.0, deaths=1) == "High"


def test_rule_tier_critical_when_3_or_more_deaths():
    assert _rule_tier(baseline_ratio=0.1, deaths=3) == "Critical"


def test_seasonality_multiplier_active_in_monsoon_for_dengue():
    when = datetime(2026, 8, 15)  # August = monsoon
    mult = _seasonality_multiplier("dengue", when)
    assert mult > 1.0


def test_seasonality_multiplier_inactive_for_non_vector_borne():
    when = datetime(2026, 8, 15)
    mult = _seasonality_multiplier("TB", when)
    assert mult == 1.0


def test_seasonality_multiplier_inactive_outside_monsoon():
    when = datetime(2026, 3, 15)
    mult = _seasonality_multiplier("dengue", when)
    assert mult == 1.0


def test_aggregate_severity_picks_worst_tier():
    signals = [
        {"tier": "Low", "confidence": 0.6},
        {"tier": "High", "confidence": 0.9},
        {"tier": "Medium", "confidence": 0.7},
    ]
    sev, conf = aggregate_severity(signals)
    assert sev == "HIGH"
    assert conf == 0.9


def test_aggregate_severity_critical_when_present():
    signals = [
        {"tier": "Low", "confidence": 0.4},
        {"tier": "Critical", "confidence": 0.95},
    ]
    sev, _ = aggregate_severity(signals)
    assert sev == "CRITICAL"


def test_aggregate_severity_defaults_when_empty():
    assert aggregate_severity([]) == ("LOW", 0.0)


def test_tier_action_strings_present_for_every_tier():
    for tier in ("Low", "Medium", "High", "Critical"):
        assert TIER_ACTION.get(tier), f"missing action for {tier}"


def test_tier_rules_priority_order():
    # First-rule-fires-wins is what determines tier.
    names_in_order = [r.name for r in TIER_RULES]
    assert names_in_order == ["Critical", "High", "Medium", "Low"]
