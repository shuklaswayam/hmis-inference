import json
import os
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, status

from backend.database import Database
from backend.rules_engine import HMISRulesEngine

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

rules_engine = HMISRulesEngine()

# Async Redis client — non-blocking in async event loop
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

CACHE_TTL = 60  # seconds


async def _run_rules_engine_on_facilities() -> list[dict]:
    """Run the rules engine on the latest facility_metrics for each facility and store triggered alerts."""
    query = """
        WITH latest_metrics AS (
            SELECT DISTINCT ON (facility_id)
                id, facility_id, reported_date, opd_visits,
                icu_occupancy_pct, bed_occupancy_pct,
                emergency_visits, maternal_deaths, deliveries
            FROM facility_metrics
            ORDER BY facility_id, reported_date DESC
        )
        SELECT lm.*,
               hf.district_id,
               hf.name as facility_name
        FROM latest_metrics lm
        JOIN health_facilities hf ON hf.id = lm.facility_id
    """
    metrics_rows = await Database.fetch(query)
    newly_triggered = []

    for row in metrics_rows:
        metrics = {
            "icu_occupancy_pct": float(row["icu_occupancy_pct"]) if row["icu_occupancy_pct"] else 0,
            "bed_occupancy_pct": float(row["bed_occupancy_pct"]) if row["bed_occupancy_pct"] else 0,
            "opd_visits": row["opd_visits"],
            "emergency_visits": row["emergency_visits"],
            "maternal_deaths": row["maternal_deaths"],
            "deliveries": row["deliveries"],
        }

        triggered = rules_engine.evaluate(metrics)

        for rule in triggered:
            # Check if this alert already exists for this facility+date
            check = await Database.fetchrow(
                """
                SELECT id FROM inference_results
                WHERE facility_id = $1
                  AND rule_flags->>'rule_name' = $2
                  AND created_at::date = CURRENT_DATE
                """,
                row["facility_id"],
                rule["rule_name"],
            )
            if check:
                continue

            insert_query = """
                INSERT INTO inference_results (
                    facility_id, district_id, inference_type, severity,
                    what_is_happening, why_it_happening, recommended_action,
                    confidence_score, rule_flags, llm_generated
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, 1.0, $8, FALSE)
                RETURNING id, created_at
            """
            rule_flags = {
                "rule_id": rule["rule_id"],
                "rule_name": rule["rule_name"],
                "description": rule["description"],
                "facility_name": row.get("facility_name", ""),
            }
            new_row = await Database.fetchrow(
                insert_query,
                row["facility_id"],
                row["district_id"],
                rule["rule_name"],
                rule["severity"],
                rule["what_is_happening"],
                rule["why_it_happening"],
                rule["recommended_action"],
                json.dumps(rule_flags),
            )
            newly_triggered.append(
                {
                    "id": str(new_row["id"]),
                    "facility_id": str(row["facility_id"]),
                    "district_id": str(row["district_id"]),
                    "facility_name": row.get("facility_name", ""),
                    **rule,
                    "created_at": new_row["created_at"].isoformat(),
                }
            )

            # Publish HIGH severity alerts to Redis for WebSocket streaming
            if rule["severity"] == "HIGH":
                try:
                    alert_payload = json.dumps({
                        "type": "new_alert",
                        "alert": {
                            "id": str(new_row["id"]),
                            "facility_id": str(row["facility_id"]),
                            "district_id": str(row["district_id"]),
                            "facility_name": row.get("facility_name", ""),
                            "severity": rule["severity"],
                            "rule_name": rule["rule_name"],
                            "what_is_happening": rule["what_is_happening"],
                            "created_at": new_row["created_at"].isoformat(),
                        },
                    })
                    await redis_client.publish("new_alerts", alert_payload)
                except Exception:
                    pass  # Non-critical: alert still saved even if publish fails

    return newly_triggered


async def _fetch_active_alerts(
    district_id: Optional[str], severity: str
) -> list[dict]:
    """Fetch active (non-expired) alerts from inference_results."""
    conditions = ["ir.expires_at IS NULL"]
    params = []
    idx = 1

    if district_id:
        conditions.append(f"ir.district_id = ${idx}")
        params.append(district_id)
        idx += 1

    if severity:
        conditions.append(f"ir.severity = ${idx}")
        params.append(severity.upper())
        idx += 1

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            ir.id,
            ir.facility_id,
            ir.district_id,
            ir.inference_type,
            ir.severity,
            ir.what_is_happening,
            ir.why_it_happening,
            ir.recommended_action,
            ir.confidence_score,
            ir.rule_flags,
            ir.llm_generated,
            ir.created_at,
            ir.expires_at,
            hf.name as facility_name,
            d.name as district_name
        FROM inference_results ir
        LEFT JOIN health_facilities hf ON hf.id = ir.facility_id
        LEFT JOIN districts d ON d.id = ir.district_id
        WHERE {where_clause}
        ORDER BY ir.created_at DESC
        LIMIT 100
    """
    rows = await Database.fetch(query, *params)

    alerts = []
    for row in rows:
        rule_flags = row["rule_flags"]
        if isinstance(rule_flags, str):
            rule_flags = json.loads(rule_flags) if rule_flags else {}
        elif rule_flags is None:
            rule_flags = {}

        alerts.append(
            {
                "id": str(row["id"]),
                "rule_id": rule_flags.get("rule_id", ""),
                "rule_name": rule_flags.get("rule_name", ""),
                "description": rule_flags.get("description", ""),
                "severity": row["severity"],
                "inference_type": row["inference_type"],
                "facility_id": str(row["facility_id"]) if row["facility_id"] else None,
                "facility_name": row["facility_name"] or "",
                "district_id": str(row["district_id"]) if row["district_id"] else None,
                "district_name": row["district_name"] or "",
                "what_is_happening": row["what_is_happening"],
                "why_it_happening": row["why_it_happening"],
                "recommended_action": row["recommended_action"],
                "confidence_score": float(row["confidence_score"]),
                "llm_generated": row["llm_generated"],
                "created_at": row["created_at"].isoformat(),
                "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
            }
        )

    return alerts


@router.get(
    "/",
    summary="Get active alerts",
    response_description="List of triggered alerts",
)
async def get_alerts(
    district_id: Optional[str] = Query(None, description="Filter by district UUID"),
    severity: Optional[str] = Query("HIGH", description="Filter by severity: HIGH, MEDIUM, LOW"),
) -> list[dict]:
    """
    Get active alerts.

    - Runs the rules engine on the latest facility_metrics for each facility.
    - Stores any newly triggered alerts in inference_results.
    - Returns all active (non-expired) alerts matching the filters.
    - Response is cached in Redis for 60 seconds.
    """
    cache_key = f"alerts:{district_id}:{severity}"

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    await _run_rules_engine_on_facilities()

    alerts = await _fetch_active_alerts(district_id, severity)

    await redis_client.setex(cache_key, CACHE_TTL, json.dumps(alerts))

    return alerts
