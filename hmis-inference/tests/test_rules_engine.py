"""
Unit tests for HMIS Rules Engine.
CRITICAL: These rules are deterministic — tests must verify exact behavior.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from rules_engine import HMISRulesEngine


engine = HMISRulesEngine()


def test_r001_icu_overload():
    """Test R001: ICU occupancy > 85% triggers icu_overload."""
    metrics = {"icu_occupancy_pct": 90}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "icu_overload" in names
    assert triggered[names.index("icu_overload")]["severity"] == "HIGH"


def test_r002_icu_critical():
    """Test R002: ICU occupancy > 95% triggers icu_critical."""
    metrics = {"icu_occupancy_pct": 97}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "icu_critical" in names


def test_r003_stockout():
    """Test R003: Medicine days_remaining < 7 triggers stockout."""
    metrics = {"medicine_days_remaining": 5}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "stockout" in names


def test_r004_outbreak():
    """Test R004: case_count > 2x baseline_avg triggers outbreak."""
    metrics = {"case_count": 50, "baseline_avg": 20}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "outbreak" in names


def test_r005_maternal_cluster():
    """Test R005: maternal_deaths >= 2 triggers maternal_cluster."""
    metrics = {"maternal_deaths": 2}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "maternal_cluster" in names


def test_r006_vacc_gap():
    """Test R006: vaccination_rate < 50% triggers vacc_gap."""
    metrics = {"vaccination_rate_pct": 40}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "vacc_gap" in names


def test_r007_opd_surge():
    """Test R007: opd_visits > 1.5x avg_opd triggers opd_surge."""
    metrics = {"opd_visits": 300, "avg_opd": 180}
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "opd_surge" in names


def test_no_rules_triggered_safe_values():
    """Test that no rules trigger when all values are within safe thresholds."""
    metrics = {
        "icu_occupancy_pct": 50,
        "medicine_days_remaining": 30,
        "case_count": 10,
        "baseline_avg": 20,
        "maternal_deaths": 0,
        "vaccination_rate_pct": 95,
        "opd_visits": 100,
        "avg_opd": 200,
    }
    triggered = engine.evaluate(metrics)
    assert len(triggered) == 0


def test_multiple_rules_trigger():
    """Test that multiple rules can trigger simultaneously."""
    metrics = {
        "icu_occupancy_pct": 96,
        "medicine_days_remaining": 3,
        "case_count": 100,
        "baseline_avg": 20,
    }
    triggered = engine.evaluate(metrics)
    names = [r["rule_name"] for r in triggered]
    assert "icu_critical" in names
    assert "icu_overload" in names
    assert "stockout" in names
    assert "outbreak" in names
