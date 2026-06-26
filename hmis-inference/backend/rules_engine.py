"""
HMIS Rules Engine — Deterministic rule-based inference.
CRITICAL: These rules are deterministic — they must NEVER be replaced by LLM predictions.
Medical decisions require 100% reproducibility.
"""

from typing import Any


class HMISRulesEngine:
    """
    Deterministic rule engine for HMIS inference.
    Each rule has a fixed threshold and produces a predictable output.
    """

    RULES = [
        {
            "id": "R001",
            "name": "icu_overload",
            "description": "ICU occupancy exceeds 85%",
            "severity": "HIGH",
            "condition": lambda m: m.get("icu_occupancy_pct", 0) > 85,
            "what_is_happening": "ICU occupancy is above 85%, indicating potential capacity strain.",
            "why_it_happening": "High patient acuity or insufficient ICU beds for current demand.",
            "recommended_action": "Activate surge capacity plan; consider patient transfers to nearby facilities.",
        },
        {
            "id": "R002",
            "name": "icu_critical",
            "description": "ICU occupancy exceeds 95%",
            "severity": "HIGH",
            "condition": lambda m: m.get("icu_occupancy_pct", 0) > 95,
            "what_is_happening": "ICU occupancy is above 95%, indicating critical capacity shortage.",
            "why_it_happening": "Severe patient surge or major incident overwhelming ICU resources.",
            "recommended_action": "Declare ICU emergency; request regional support; halt elective admissions.",
        },
        {
            "id": "R003",
            "name": "stockout",
            "description": "Medicine stock below 7 days",
            "severity": "HIGH",
            "condition": lambda m: m.get("medicine_days_remaining", 999) < 7,
            "what_is_happening": "Essential medicine stock is below 7 days, risking stockout.",
            "why_it_happening": "Supply chain disruption or higher than expected consumption.",
            "recommended_action": "Initiate emergency procurement; contact state medical supply corporation.",
        },
        {
            "id": "R004",
            "name": "outbreak",
            "description": "Disease cases exceed 2x baseline average",
            "severity": "HIGH",
            "condition": lambda m: m.get("case_count", 0) > 2 * m.get("baseline_avg", 1),
            "what_is_happening": "Reported cases exceed twice the baseline average, indicating potential outbreak.",
            "why_it_happening": "Possible disease outbreak, seasonal surge, or reporting anomaly.",
            "recommended_action": "Notify district surveillance officer; initiate outbreak investigation protocol.",
        },
        {
            "id": "R005",
            "name": "maternal_cluster",
            "description": "Two or more maternal deaths in reporting period",
            "severity": "HIGH",
            "condition": lambda m: m.get("maternal_deaths", 0) >= 2,
            "what_is_happening": "Multiple maternal deaths detected in the reporting period.",
            "why_it_happening": "Potential systemic issue in obstetric care or emergency referral chain.",
            "recommended_action": "Trigger maternal death review committee; audit emergency obstetric pathways.",
        },
        {
            "id": "R006",
            "name": "vacc_gap",
            "description": "Vaccination rate below 50%",
            "severity": "MEDIUM",
            "condition": lambda m: m.get("vaccination_rate_pct", 100) < 50,
            "what_is_happening": "Vaccination coverage is below 50%, leaving population vulnerable.",
            "why_it_happening": "Vaccine hesitancy, supply issues, or access barriers in the community.",
            "recommended_action": "Launch targeted vaccination drive; engage community health workers.",
        },
        {
            "id": "R007",
            "name": "opd_surge",
            "description": "OPD visits exceed 1.5x average",
            "severity": "MEDIUM",
            "condition": lambda m: m.get("opd_visits", 0) > 1.5 * m.get("avg_opd", 1),
            "what_is_happening": "Outpatient visits exceed 1.5 times the facility average.",
            "why_it_happening": "Seasonal illness surge, community outbreak, or reduced access elsewhere.",
            "recommended_action": "Extend OPD hours; deploy additional staff; monitor for admission trends.",
        },
        {
            "id": "R008",
            "name": "severe_stockout",
            "description": "Medicine stock below 2 days — critical runway",
            "severity": "CRITICAL",
            "condition": lambda m: m.get("medicine_days_remaining", 999) < 2,
            "what_is_happening": "Essential medicine will run out within 48 hours.",
            "why_it_happening": "Severe supply chain failure, with all replacement channels exhausted.",
            "recommended_action": "Trigger inter-facility stock transfer; escalate to state-level emergency procurement.",
        },
        {
            "id": "R009",
            "name": "staff_attendance_dip",
            "description": "Staff attendance below 75%",
            "severity": "LOW",
            "condition": lambda m: m.get("staff_attendance_pct", 100) < 75,
            "what_is_happening": "Staff attendance at the facility has slipped below 75%.",
            "why_it_happening": "Local seasonal absence, transport issues, or unannounced leave.",
            "recommended_action": "Log and review next Monday; reroute patients only if attendance trends worsen.",
        },
    ]

    def __init__(self):
        self.rules = self.RULES

    def evaluate(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Evaluate all rules against the provided metrics.

        Args:
            metrics: Dictionary containing metric values (e.g., icu_occupancy_pct, case_count, etc.)

        Returns:
            List of triggered rules with their details.
        """
        triggered = []

        for rule in self.rules:
            try:
                if rule["condition"](metrics):
                    triggered.append(
                        {
                            "rule_id": rule["id"],
                            "rule_name": rule["name"],
                            "severity": rule["severity"],
                            "description": rule["description"],
                            "what_is_happening": rule["what_is_happening"],
                            "why_it_happening": rule["why_it_happening"],
                            "recommended_action": rule["recommended_action"],
                        }
                    )
            except Exception:
                # Rules must not crash; log and continue
                continue

        return triggered