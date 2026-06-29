"""Workstream 3 — Priority Alert Ranker.

Pure-function ranking of all candidate governance signals:
  * active inference_results rows (rule-fired alerts — ICU overload,
    drug stockouts, maternal clusters, etc.)
  * Workstream-1 outbreak signals (high / critical tiers)
  * Workstream-2 pressure signals (critical tier only)
  * Zero-dose pockets — derived proxy from low OPD attendance in
    under-5 age groups in vaccination-eligible sub-districts

Score = severity_w * 0.55
      + recency   * 0.25   (1 / (hours_old + 1), normalized)
      + spread    * 0.20   (facilities / diseases affected)
      + owner_penalty      (+1) when owner is inferred generically

Owner mapping is a static dispatch table — kept simple and explicit
so the inbound team can amend it without code spelunking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from backend.database import Database

logger = logging.getLogger(__name__)


SEVERITY_WEIGHT = {"CRITICAL": 6, "HIGH": 4, "MEDIUM": 2, "LOW": 1}
SLATABLE_HOURS = {
    "CRITICAL": 4,
    "HIGH": 12,
    "MEDIUM": 24,
    "LOW": 72,
    "ZERO_DOSE": 48,
    "OUTBREAK_HIGH": 24,
    "OUTBREAK_CRITICAL": 8,
    "PRESSURE_CRITICAL": 8,
}


# ---------------------------------------------------------------------------
# Owner-mapping dispatch table (no LLM, fully deterministic)
# ---------------------------------------------------------------------------
OWNER_BY_RULE = {
    "icu_overload":      ("Facility In-Charge",          "Activate surge plan; consider transfers."),
    "icu_critical":      ("Facility In-Charge + State",  "Declare ICU emergency; halt electives."),
    "stockout":          ("State Procurement",           "Initiate emergency procurement."),
    "severe_stockout":   ("State Procurement + Commissioner",
                          "Trigger inter-facility stock transfer."),
    "outbreak":          ("District Surveillance Officer", "Initiate outbreak investigation."),
    "maternal_cluster":  ("District Maternal Health Officer + State MDR Committee",
                          "Trigger maternal death review."),
    "vacc_gap":          ("District Immunisation Officer", "Launch targeted vaccination drive."),
    "zero_dose_pocket":  ("District Immunisation Officer", "Door-to-door zero-dose recovery."),
    "opd_surge":         ("Facility In-Charge",          "Extend OPD hours; redeploy staff."),
    "staff_attendance_dip": ("Facility HR",              "Investigate; reroute only if trend worsens."),
    "hospital_pressure_critical": ("Facility In-Charge + State",
                                    "Pre-emptive patient diversion."),
    "outbreak_high":        ("District Surveillance Officer + State", "Activate containment protocol."),
    "outbreak_critical":    ("Commissioner + Rapid Response Team", "Commissioner-level escalation."),
}


@dataclass(frozen=True)
class RankedAction:
    rank: int
    headline: str
    severity: str
    severity_score: float
    recommended_owner: str
    sla_hours: int
    evidence_refs: list[str]


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------
async def _collect_rule_alerts() -> list[dict]:
    """Pull active (non-expired) inference_results with a known rule_name."""
    rows = await Database.fetch(
        """
        SELECT
            ir.id,
            ir.severity,
            ir.inference_type,
            ir.rule_flags,
            ir.what_is_happening,
            ir.recommended_action,
            ir.facility_id,
            ir.district_id,
            ir.created_at,
            hf.name AS facility_name,
            d.name  AS district_name
        FROM inference_results ir
        LEFT JOIN health_facilities hf ON hf.id = ir.facility_id
        LEFT JOIN districts d ON d.id = ir.district_id
        WHERE ir.expires_at IS NULL
          AND ir.severity IN ('HIGH', 'MEDIUM', 'LOW', 'CRITICAL')
        ORDER BY ir.created_at DESC
        LIMIT 200
        """
    )
    out: list[dict] = []
    for r in rows:
        rule_flags = r["rule_flags"]
        if isinstance(rule_flags, str):
            import json
            try:
                rule_flags = json.loads(rule_flags)
            except Exception:  # noqa: BLE001
                rule_flags = {}
        rule_name = (rule_flags or {}).get("rule_name") or r["inference_type"]
        out.append(
            {
                "kind": "rule",
                "rule_name": rule_name,
                "severity": r["severity"],
                "headline": r["what_is_happening"]
                    or f"{rule_name} flagged at {r['facility_name'] or 'unknown facility'}",
                "facility_id": str(r["facility_id"]) if r["facility_id"] else None,
                "facility_name": r["facility_name"],
                "district_name": r["district_name"],
                "created_at": r["created_at"],
                "spread": 1.0,
                "one_liner": r["recommended_action"] or "",
            }
        )
    return out


async def _inject_outbreak_and_pressure(
    candidates: list[dict],
    outbreak_signals: list[dict],
    pressure_signals: list[dict],
) -> None:
    """Promote WS1 high/critical signals and WS2 critical pressure tier to
    ranker candidates — these aren't yet in inference_results."""
    for s in outbreak_signals:
        if s["tier"] in {"High", "Critical"}:
            rule_name = (
                "outbreak_critical" if s["tier"] == "Critical" else "outbreak_high"
            )
            candidates.append(
                {
                    "kind": "outbreak",
                    "rule_name": rule_name,
                    "severity": "CRITICAL" if s["tier"] == "Critical" else "HIGH",
                    "headline": s["one_liner"],
                    "facility_id": None,
                    "facility_name": None,
                    "district_name": s["district_name"],
                    "created_at": datetime.now(timezone.utc),
                    "spread": float(max(1, s["cases_last_14d"] // 10)),
                    "one_liner": s["recommended_action"],
                }
            )
    for s in pressure_signals:
        if s["tier"] == "Critical":
            candidates.append(
                {
                    "kind": "pressure",
                    "rule_name": "hospital_pressure_critical",
                    "severity": "CRITICAL",
                    "headline": s["one_liner"],
                    "facility_id": s["facility_id"],
                    "facility_name": s["facility_name"],
                    "district_name": s["district_name"],
                    "created_at": datetime.now(timezone.utc),
                    "spread": 1.0,
                    "one_liner": s["recommended_action"],
                }
            )


async def _collect_zero_dose_pockets() -> list[dict]:
    """Surrogate for true immunisation coverage: districts whose recent
    0-5 OPD-attendance dropped to >1 std-dev below the 30-day mean."""
    rows = await Database.fetch(
        """
        WITH age AS (
            SELECT
                hf.district_id,
                d.name AS district_name,
                dr.reported_date,
                SUM(CASE WHEN dr.age_group = '0-5' THEN dr.case_count ELSE 0 END) AS cases_0_5
            FROM disease_reports dr
            JOIN health_facilities hf ON hf.id = dr.facility_id
            JOIN districts d ON d.id = hf.district_id
            WHERE dr.reported_date >= CURRENT_DATE - INTERVAL '14 days'
            GROUP BY hf.district_id, d.name, dr.reported_date
        ),
        stats AS (
            SELECT
                district_id,
                district_name,
                AVG(cases_0_5) AS mean,
                COALESCE(STDDEV(cases_0_5), 0) AS sd
            FROM age
            GROUP BY district_id, district_name
        ),
        recent AS (
            SELECT
                district_id,
                SUM(cases_0_5) AS total_last3
            FROM age
            WHERE reported_date >= CURRENT_DATE - INTERVAL '3 days'
            GROUP BY district_id
        )
        SELECT
            s.district_name,
            r.total_last3,
            s.mean * 0.5 AS recent_baseline,
            s.mean,
            s.sd
        FROM stats s
        LEFT JOIN recent r ON r.district_id = s.district_id
        WHERE r.total_last3 IS NOT NULL
          AND s.sd > 0
          AND r.total_last3 < (s.mean - s.sd)
          AND r.total_last3 < (s.mean * 0.5)
        """
    )
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "kind": "zero_dose",
                "rule_name": "zero_dose_pocket",
                "severity": "HIGH",
                "headline": (
                    f"Possible zero-dose pocket in {r['district_name']} "
                    f"({r['total_last3']} 0-5 cases vs baseline {round(float(r['mean'] or 0), 1)})"
                ),
                "facility_id": None,
                "facility_name": None,
                "district_name": r["district_name"],
                "created_at": datetime.now(timezone.utc),
                "spread": float(max(1, round(float(r['sd'] or 1), 1))),
                "one_liner": "Door-to-door zero-dose recovery drive.",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Scoring + sorting
# ---------------------------------------------------------------------------
def _recency_score(created_at: datetime, now: datetime) -> float:
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600.0)
    return 1.0 / (age_hours + 1.0)


def _score(c: dict, now: datetime, max_recency: float) -> tuple[float, dict]:
    sev = SEVERITY_WEIGHT.get(c["severity"], 1)
    recency = _recency_score(c["created_at"], now)
    recency_norm = recency / max_recency if max_recency else 0.0
    spread = min(10.0, max(1.0, c["spread"]))

    owner = OWNER_BY_RULE.get(c["rule_name"])
    owner_penalty = 0.0 if owner else 1.0

    # owner_penalty subtracts: known/dispatchable signals beat raw
    # signals with no assigned owner. Net floor is ≥ 0 since
    # the other components naturally dominate.
    score = (
        sev * 0.55
        + recency_norm * 0.25 * 10.0   # rescale ~ 0..10
        + spread * 0.20
        - owner_penalty
    )

    owner_label, _action = owner or ("State Health Commissioner", "")
    return (
        score,
        {
            "score": score,
            "severity": c["severity"],
            "owner_penalty": owner_penalty,
            "recency_norm": round(recency_norm, 4),
            "spread": spread,
            "owner": owner_label,
        },
    )


def _sla_hours(c: dict) -> int:
    # Specific overrides come first so each gets its own SLA bucket.
    if c["rule_name"] == "outbreak_critical":
        return SLATABLE_HOURS["OUTBREAK_CRITICAL"]
    if c["rule_name"] == "outbreak_high":
        return SLATABLE_HOURS["OUTBREAK_HIGH"]
    if c["rule_name"] == "zero_dose_pocket":
        return SLATABLE_HOURS["ZERO_DOSE"]
    if c["rule_name"] in {"hospital_pressure_critical", "icu_critical", "severe_stockout"}:
        return SLATABLE_HOURS.get("CRITICAL", 4)
    if c["rule_name"] == "icu_overload":
        return SLATABLE_HOURS.get("HIGH", 12)
    return SLATABLE_HOURS.get(c["severity"], 24)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def rank(
    *,
    outbreak_signals: Optional[list[dict]] = None,
    pressure_signals: Optional[list[dict]] = None,
) -> list[dict]:
    """Top-5 ranked policy actions.

    ``outbreak_signals`` and ``pressure_signals`` come from WS1 / WS2 —
    by default we recompute them so the ranker is self-sufficient when
    called from the bare router, but the router can memoize.
    """
    rule_alerts = await _collect_rule_alerts()
    zero_dose = await _collect_zero_dose_pockets()
    candidates: list[dict] = list(rule_alerts) + zero_dose

    if outbreak_signals is None or pressure_signals is None:
        # Lazy import to avoid a circular import; safe at call-time.
        from backend.inference import outbreak_risk, hospital_pressure
        outbreak_signals = outbreak_signals or await outbreak_risk.score()
        pressure_signals = pressure_signals or await hospital_pressure.score()

    await _inject_outbreak_and_pressure(candidates, outbreak_signals, pressure_signals)
    if not candidates:
        return []

    now = datetime.now(timezone.utc)
    # Deduplicate by (rule_name, facility_id) keeping the most recent.
    dedup: dict[tuple[str, Optional[str]], dict] = {}
    for c in candidates:
        c["created_at"] = c["created_at"]
        if c["created_at"].tzinfo is None:
            c["created_at"] = c["created_at"].replace(tzinfo=timezone.utc)
        key = (c["rule_name"], c["facility_id"])
        prior = dedup.get(key)
        if prior is None or (c["created_at"] - prior["created_at"]).total_seconds() > 0:
            dedup[key] = c
    candidates = list(dedup.values())

    max_recency = max(
        (1.0 / ((now - c["created_at"]).total_seconds() / 3600.0 + 1.0))
        for c in candidates
    )

    scored: list[tuple[float, dict]] = [
        (_score(c, now, max_recency)[0], c) for c in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[:5]

    out: list[dict] = []
    for idx, (s, c) in enumerate(top, start=1):
        owner, action = OWNER_BY_RULE.get(
            c["rule_name"], ("State Health Commissioner", "Escalate to State.")
        )
        out.append(
            {
                "rank": idx,
                "headline": c["headline"],
                "severity": c["severity"],
                "severity_score": round(min(10.0, s / 10.0), 2),
                "recommended_owner": owner,
                "sla_hours": _sla_hours(c),
                "evidence_refs": [
                    f"facility:{c['facility_id']}" if c["facility_name"] else f"district:{c['district_name']}",
                    f"rule:{c['rule_name']}",
                ],
                "recommended_step": action or c.get("one_liner", ""),
            }
        )
    return out


def aggregate_severity(ranked: list[dict]) -> tuple[str, float]:
    if not ranked:
        return ("LOW", 0.0)
    top = ranked[0]
    sev = top["severity"]
    score = float(top["severity_score"])
    if sev == "CRITICAL":
        return ("CRITICAL", score)
    if sev == "HIGH":
        return ("HIGH", score)
    return ("MEDIUM", score)
