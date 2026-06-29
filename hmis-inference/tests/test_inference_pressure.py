"""
Unit tests for Workstream 2 — Hospital Pressure Classifier.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend.inference.hospital_pressure import _classify, aggregate_severity, ACTION


def test_classify_normal_when_metrics_low():
    assert _classify(icu_pct=50.0, bed_pct=60.0, opd_ratio=0.8) == "Normal"


def test_classify_strained_when_icu_above_80():
    assert _classify(icu_pct=85.0, bed_pct=60.0, opd_ratio=0.9) == "Strained"


def test_classify_strained_when_bed_above_85():
    assert _classify(icu_pct=70.0, bed_pct=88.0, opd_ratio=0.9) == "Strained"


def test_classify_strained_when_opd_surge_above_1_5x():
    assert _classify(icu_pct=70.0, bed_pct=70.0, opd_ratio=1.6) == "Strained"


def test_classify_critical_when_icu_above_90():
    assert _classify(icu_pct=92.0, bed_pct=60.0, opd_ratio=0.8) == "Critical"


def test_classify_critical_when_bed_above_95():
    assert _classify(icu_pct=70.0, bed_pct=96.0, opd_ratio=0.8) == "Critical"


def test_classify_critical_when_opd_surge_and_high_icu():
    # OPD >= 1.8x AND icu >= 75 → Critical
    assert _classify(icu_pct=80.0, bed_pct=70.0, opd_ratio=2.0) == "Critical"


def test_classify_off_by_one_boundary():
    # Boundary conditions: 80.0 -> Strained, 79.9 -> Normal
    assert _classify(icu_pct=80.0, bed_pct=70.0, opd_ratio=0.9) == "Strained"
    assert _classify(icu_pct=79.9, bed_pct=70.0, opd_ratio=0.9) == "Normal"


def test_aggregate_severity_defaults_when_empty():
    assert aggregate_severity([]) == ("LOW", 0.0)


def test_aggregate_severity_critical_when_a_critical_facility():
    signals = [
        {"tier": "Strained", "confidence": 0.7},
        {"tier": "Critical", "confidence": 0.9},
        {"tier": "Normal", "confidence": 0.5},
    ]
    sev, conf = aggregate_severity(signals)
    assert sev == "CRITICAL"
    assert conf == 0.9


def test_aggregate_severity_high_when_strained_no_critical():
    signals = [{"tier": "Strained", "confidence": 0.65}]
    sev, _ = aggregate_severity(signals)
    assert sev == "HIGH"


def test_action_strings_present_for_every_tier():
    for tier in ("Normal", "Strained", "Critical"):
        assert ACTION.get(tier), f"missing action for {tier}"
