"""
Unit tests for Workstream 3 — Priority Alert Ranker.

We exercise only the pure-Python helpers — DB-collecting helpers route
through test_inference_router.py with mocks.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend.inference.priority_rank import (
    _score,
    _sla_hours,
    OWNER_BY_RULE,
    aggregate_severity,
    SEVERITY_WEIGHT,
)


def _candidate(rule_name, severity, age_hours, spread=1.0):
    return {
        "kind": "test",
        "rule_name": rule_name,
        "severity": severity,
        "headline": f"{rule_name} test signal",
        "facility_id": None,
        "facility_name": None,
        "district_name": "Ahmedabad",
        "created_at": datetime.now(timezone.utc) - timedelta(hours=age_hours),
        "spread": spread,
        "one_liner": "do something",
    }


def test_score_increases_with_severity():
    now = datetime.now(timezone.utc)
    candidates = [
        _candidate("icu_overload", "MEDIUM", age_hours=0),
        _candidate("icu_critical", "CRITICAL", age_hours=0),
    ]
    s_low, _ = _score(candidates[0], now, max_recency=1.0)
    s_high, _ = _score(candidates[1], now, max_recency=1.0)
    assert s_high > s_low


def test_score_increases_with_recency():
    now = datetime.now(timezone.utc)
    new = _candidate("icu_overload", "HIGH", age_hours=0)
    old = _candidate("icu_overload", "HIGH", age_hours=72)
    s_new, _ = _score(new, now, max_recency=1.0)
    s_old, _ = _score(old, now, max_recency=1.0)
    assert s_new > s_old


def test_score_boosts_unknown_owner_for_triage():
    # Per spec: owner_penalty ADDS +1 when no dispatchable owner is
    # mapped, so the signal is promoted into the human-triage queue
    # rather than silently dropped beneath well-mapped rule alerts.
    now = datetime.now(timezone.utc)
    known = _candidate("icu_overload", "HIGH", age_hours=0)
    unknown = _candidate("totally_unknown_signal", "HIGH", age_hours=0)
    s_known, _ = _score(known, now, max_recency=1.0)
    s_unknown, _ = _score(unknown, now, max_recency=1.0)
    assert s_unknown > s_known


def test_sla_hours_critical_default():
    assert _sla_hours(_candidate("icu_overload", "CRITICAL", 0)) <= 12


def test_sla_hours_short_for_icu_critical():
    # Critical ICU / stockout / pressure should be ≤ 8h.
    assert _sla_hours(_candidate("icu_critical", "CRITICAL", 0)) == 4


def test_sla_hours_for_outbreak_critical():
    assert _sla_hours(_candidate("outbreak_critical", "CRITICAL", 0)) == 8


def test_sla_hours_for_outbreak_high():
    assert _sla_hours(_candidate("outbreak_high", "HIGH", 0)) == 24


def test_owner_mapping_has_expected_dispatch():
    assert OWNER_BY_RULE["icu_critical"][0].startswith("Facility In-Charge")
    assert "Commissioner" in OWNER_BY_RULE["severe_stockout"][0]
    assert "Maternal" in OWNER_BY_RULE["maternal_cluster"][0]


def test_aggregate_severity_empty_returns_low():
    assert aggregate_severity([]) == ("LOW", 0.0)


def test_aggregate_severity_top_action_drives_label():
    ranked = [
        {"severity": "CRITICAL", "severity_score": 9.5},
        {"severity": "HIGH", "severity_score": 7.0},
    ]
    sev, score = aggregate_severity(ranked)
    assert sev == "CRITICAL"
    assert score == 9.5


def test_severity_weight_strictly_monotonic():
    assert SEVERITY_WEIGHT["CRITICAL"] > SEVERITY_WEIGHT["HIGH"]
    assert SEVERITY_WEIGHT["HIGH"] > SEVERITY_WEIGHT["MEDIUM"]
    assert SEVERITY_WEIGHT["MEDIUM"] > SEVERITY_WEIGHT["LOW"]
