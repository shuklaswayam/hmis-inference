"""
Celery tasks for HMIS Inference System.
Periodic tasks for nightly inference + inference cache warming +
priority-rank transition detection.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from celery import Celery

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(BACKEND_DIR))

from celery.schedules import crontab

_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery("hmis_tasks")
app.config_from_object({
    "broker_url": _REDIS_URL,
    "result_backend": _REDIS_URL,
    "timezone": "Asia/Kolkata",
    "enable_utc": True,
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
})

app.conf.beat_schedule = {
    "nightly-inference": {
        "task": "tasks.run_nightly_inference",
        "schedule": crontab(hour=0, minute=30),
        "args": (),
    },
    "warm-inference-cache": {
        "task": "tasks.warm_inference_cache",
        "schedule": 840.0,  # 14 minutes, just under the 15-min cache TTL
        "args": (),
    },
    "check-priority-transition": {
        "task": "tasks.check_priority_transition",
        "schedule": 60.0,   # once per minute, fires on CRITICAL transitions
        "args": (),
    },
    "audit-prune-archive": {
        "task": "tasks.audit_prune_archive",
        "schedule": crontab(hour=2, minute=0),  # 02:00 IST, off-peak
        "args": (),
    },
}


def _get_event_loop():
    """Get or create an event loop for async operations."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


async def _run_nightly_inference_async():
    """Run the full Rule+ML pipeline for all facilities."""
    from backend.database import Database
    from backend.rules_engine import HMISRulesEngine
    from backend.ml.anomaly import AnomalyDetector
    from backend.ml.risk_scorer import RiskScorer

    await Database.initialize()

    rules_engine = HMISRulesEngine()

    # Load anomaly detector if model exists
    detector = None
    try:
        detector = AnomalyDetector()
        detector.load()
    except (FileNotFoundError, RuntimeError):
        pass

    # Fetch all facilities with their latest metrics
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

    results = []

    for row in metrics_rows:
        metrics = {
            "icu_occupancy_pct": float(row["icu_occupancy_pct"]) if row["icu_occupancy_pct"] else 0,
            "bed_occupancy_pct": float(row["bed_occupancy_pct"]) if row["bed_occupancy_pct"] else 0,
            "opd_visits": row["opd_visits"] or 0,
            "emergency_visits": row["emergency_visits"] or 0,
            "maternal_deaths": row["maternal_deaths"] or 0,
            "deliveries": row["deliveries"] or 0,
        }

        # Step 1: Run rules engine
        rule_flags = rules_engine.evaluate(metrics)

        # Step 2: Anomaly detection
        anomaly_score = 0.0
        if detector:
            try:
                anomaly_score = detector.score(metrics)
            except Exception:
                pass

        # Step 3: Z-score analysis (using last 30 days)
        from backend.ml.anomaly import ZSCORE_METRICS
        historical_query = """
            SELECT reported_date, opd_visits, icu_occupancy_pct, case_count
            FROM facility_metrics
            WHERE facility_id = $1
              AND reported_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY reported_date
        """
        historical_rows = await Database.fetch(historical_query, row["facility_id"])
        if historical_rows:
            hist_df = pd.DataFrame([dict(r) for r in historical_rows])
            for col in ZSCORE_METRICS:
                if col in hist_df.columns:
                    hist_df[col] = pd.to_numeric(hist_df[col], errors="coerce").fillna(0)
        else:
            hist_df = pd.DataFrame(columns=ZSCORE_METRICS)

        z_scores = AnomalyDetector.z_score_check(metrics, hist_df)

        # Step 4: Risk scoring
        scorer = RiskScorer(current_date=datetime.now(timezone.utc))
        risk_result = scorer.score(
            rule_flags=rule_flags,
            anomaly_score=anomaly_score,
            z_score_results=z_scores,
        )
        priority_rank = risk_result["priority_rank"]

        # Step 5: Store result in inference_results
        try:
            await Database.execute(
                """
                INSERT INTO inference_results (
                    facility_id, district_id, inference_type, severity,
                    what_is_happening, why_it_happening, recommended_action,
                    confidence_score, rule_flags, llm_generated
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, FALSE)
                """,
                row["facility_id"],
                row["district_id"],
                "nightly_batch",
                priority_rank,
                f"Nightly inference for facility {row['facility_id']}",
                f"Combined rules ({len(rule_flags)} triggered), anomaly score {anomaly_score:.4f}",
                f"Priority: {priority_rank}",
                abs(anomaly_score),
                str(rule_flags),
            )
        except Exception:
            pass

        results.append({
            "facility_id": row["facility_id"],
            "priority_rank": priority_rank,
            "rules_triggered": len(rule_flags),
            "anomaly_score": round(anomaly_score, 4),
        })

    await Database.close()
    return results


@app.task(name="tasks.run_nightly_inference", bind=True, max_retries=3)
def run_nightly_inference(self):
    """
    Nightly inference task.
    Loops through all facilities, runs Rule+ML pipeline,
    stores results in inference_results.
    Runs at 00:30 every day via Celery Beat.
    """
    try:
        loop = _get_event_loop()
        results = loop.run_until_complete(_run_nightly_inference_async())

        return {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "facilities_processed": len(results),
            "results": results,
        }
    except Exception as exc:
        self.retry(exc=exc, countdown=60)


@app.task(name="tasks.warm_inference_cache", bind=True, max_retries=2)
def warm_inference_cache(self):
    """Pre-warm the four workstream Redis cache keys."""
    try:
        from backend.inference.cache_warmer import warm_sync_for_celery
        result = warm_sync_for_celery()
        # Phase 5: mark beat tick for /health/deep.
        from backend.inference.health import beat_tick_key
        from backend.database import Database
        async def write_tick():
            from backend.inference.cache import get_client
            from backend.inference.health import beat_tick_seconds
            client = get_client()
            await client.setex(beat_tick_key(), 180, beat_tick_seconds())
        import asyncio
        asyncio.run(write_tick())
        return result
    except Exception as exc:
        logger.warning("warm_inference_cache failed: %s", exc)
        self.retry(exc=exc, countdown=30)


@app.task(name="tasks.check_priority_transition", bind=True, max_retries=2)
def check_priority_transition(self):
    """Inspect the current #1 ranking; fire webhook on CRITICAL transition."""
    try:
        from backend.inference.notifier import check_sync_for_celery
        return check_sync_for_celery()
    except Exception as exc:
        logger.warning("check_priority_transition failed: %s", exc)
        self.retry(exc=exc, countdown=30)


@app.task(name="tasks.audit_prune_archive", bind=True, max_retries=2)
def audit_prune_archive(self):
    """Move inference_audit rows older than AUDIT_TTL_DAYS to archive.

    Cold archvied rows stay queryable via the same /api/v1/inference/audit
    surface — store.list_audit_rows unions both tables transparently.
    """
    try:
        from backend.inference.retention import archive_old_audits
        import asyncio
        return asyncio.run(archive_old_audits())
    except Exception as exc:
        logger.warning("audit_prune_archive failed: %s", exc)
        self.retry(exc=exc, countdown=300)
