"""
FastAPI router for facility insights endpoint.
Combines rules engine, anomaly detection, Z-score analysis, and forecasting
into a single unified inference result per facility.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database import Database
from backend.llm.synthesizer import LLMSynthesizer
from backend.ml.anomaly import AnomalyDetector, ZSCORE_METRICS
from backend.ml.forecaster import DiseaseForecaster
from backend.ml.risk_scorer import RiskScorer
from backend.rag.retriever import PolicyRAG
from backend.rules_engine import HMISRulesEngine


router = APIRouter(prefix="/api/v1/insights", tags=["insights"])

rules_engine = HMISRulesEngine()
rag = PolicyRAG()
llm = LLMSynthesizer()


class InsightResponse(BaseModel):
    facility_id: str
    rule_flags: list[dict]
    anomaly_score: float
    z_scores: dict
    priority_rank: str
    forecast_7day: list[dict]
    timestamp: str
    what_is_happening: Optional[str] = None
    why_it_happening: Optional[str] = None
    recommended_action: Optional[str] = None
    llm_generated: bool = False
    icu_occupancy_pct: Optional[float] = None
    bed_occupancy_pct: Optional[float] = None
    opd_visits: Optional[int] = None


async def _fetch_latest_metrics(facility_id: UUID) -> dict:
    """Fetch the latest facility_metrics row for a facility."""
    row = await Database.fetchrow(
        """
        SELECT
            fm.id,
            fm.facility_id,
            fm.reported_date,
            fm.opd_visits,
            fm.icu_occupancy_pct,
            fm.bed_occupancy_pct,
            fm.emergency_visits,
            fm.maternal_deaths,
            fm.deliveries,
            hf.district_id,
            hf.name as facility_name
        FROM facility_metrics fm
        JOIN health_facilities hf ON hf.id = fm.facility_id
        WHERE fm.facility_id = $1
        ORDER BY fm.reported_date DESC
        LIMIT 1
        """,
        facility_id,
    )
    if not row:
        return None
    return dict(row)


async def _fetch_trajectory(facility_id: UUID, days: int = 14) -> dict:
    """Fetch last N days of facility_metrics as parallel time-series lists.

    Returned dict shape (each list aligns by index, one entry per day):
        {"dates":          ["2026-06-13", ...],
         "icu_pct":        [83.0, ...],
         "bed_pct":        [78.5, ...],
         "opd_visits":     [310, ...],
         "emergency_visits":[50,  ...]}

    The LLM gets these verbatim so it can reason about trends, not just
    single-point snapshots.
    """
    rows = await Database.fetch(
        """
        SELECT
            reported_date,
            icu_occupancy_pct,
            bed_occupancy_pct,
            opd_visits,
            emergency_visits
        FROM facility_metrics
        WHERE facility_id = $1
          AND reported_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY reported_date ASC
        """ % days,
        facility_id,
    )
    out = {
        "dates":           [],
        "icu_pct":         [],
        "bed_pct":         [],
        "opd_visits":      [],
        "emergency_visits":[],
    }
    for r in rows:
        d = dict(r)
        out["dates"].append(d["reported_date"].isoformat())
        out["icu_pct"].append(float(d["icu_occupancy_pct"]) if d["icu_occupancy_pct"] is not None else None)
        out["bed_pct"].append(float(d["bed_occupancy_pct"]) if d["bed_occupancy_pct"] is not None else None)
        out["opd_visits"].append(int(d["opd_visits"]) if d["opd_visits"] is not None else None)
        out["emergency_visits"].append(int(d["emergency_visits"]) if d["emergency_visits"] is not None else None)
    return out


def _summarize_trajectory(traj: dict) -> dict:
    """Compute per-metric summary stats over the trajectory window.

    ``len(window)`` covers the latest reading; ``earliest`` and ``latest``
    come from the first and last non-None values in each series. The
    z-score column is computed against the 30-day window of values that
    appear in the trajectory itself (so the LLM can see the spread).
    """
    import numpy as np
    summary = {}
    for key in ("icu_pct", "bed_pct", "opd_visits", "emergency_visits"):
        series = [v for v in traj.get(key, []) if v is not None]
        if len(series) < 2:
            summary[key] = {}
            continue
        delta = round(series[-1] - series[0], 2)
        direction = "climbing" if delta > 1 else ("falling" if delta < -1 else "stable")
        summary[key] = {
            "earliest":  round(series[0], 2),
            "latest":    round(series[-1], 2),
            "delta":     delta,
            "direction": direction,
            "mean":      round(float(np.mean(series)), 2),
            "std":       round(float(np.std(series, ddof=1)) if len(series) > 1 else 0.0, 2),
            "n_days":    len(series),
        }
        if summary[key]["std"]:
            summary[key]["z_score_latest"] = round(
                (series[-1] - summary[key]["mean"]) / summary[key]["std"], 2
            )
    return summary


async def _fetch_recent_alerts_for_facility(facility_id: UUID, limit: int = 5) -> list[dict]:
    """Fetch the latest inference_results rows for a facility — gives the LLM
    the operational history so it can correlate the current reading with
    what has been flagged recently."""
    rows = await Database.fetch(
        """
        SELECT severity, inference_type, what_is_happening, recommended_action, created_at
        FROM inference_results
        WHERE facility_id = $1
        ORDER BY created_at DESC
        LIMIT %d
        """ % limit,
        facility_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        out.append({
            "severity":            d.get("severity"),
            "inference_type":      d.get("inference_type"),
            "what_is_happening":   d.get("what_is_happening"),
            "recommended_action":  d.get("recommended_action"),
            "created_at":          d["created_at"].isoformat() if d.get("created_at") else None,
        })
    return out


async def _fetch_historical_metrics(facility_id: UUID, days: int = 30) -> pd.DataFrame:
    """Fetch last N days of facility_metrics for Z-score computation."""
    rows = await Database.fetch(
        """
        SELECT
            reported_date,
            opd_visits,
            icu_occupancy_pct
        FROM facility_metrics
        WHERE facility_id = $1
          AND reported_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY reported_date
        """ % days,
        facility_id,
    )
    if not rows:
        return pd.DataFrame(columns=["opd_visits", "icu_occupancy_pct"])
    df = pd.DataFrame([dict(r) for r in rows])
    for col in ["opd_visits", "icu_occupancy_pct"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


async def _fetch_top_disease(district_id: UUID) -> Optional[str]:
    """Fetch the disease with the highest case count in the last 30 days for a district.

    Note: 30 days (not 7) because realistic Indian HMIS disease_reports are
    sparse — many districts report weekly or biweekly. A 7-day window would
    frequently return nothing and starve the insight of a forecast. 30 days
    captures the meaningful top-disease signal without losing recency.
    """
    row = await Database.fetchrow(
        """
        SELECT disease_name
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE hf.district_id = $1
          AND dr.reported_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY disease_name
        ORDER BY SUM(dr.case_count) DESC
        LIMIT 1
        """,
        district_id,
    )
    if not row:
        return None
    return row["disease_name"]


async def _get_forecast(disease_name: str, district_id: UUID) -> list[dict]:
    """Get 7-day disease forecast."""
    rows = await Database.fetch(
        """
        SELECT dr.reported_date as ds, SUM(dr.case_count) as y
        FROM disease_reports dr
        JOIN health_facilities hf ON hf.id = dr.facility_id
        WHERE dr.disease_name = $1
          AND hf.district_id = $2
        GROUP BY dr.reported_date
        ORDER BY dr.reported_date
        LIMIT 90
        """,
        disease_name,
        district_id,
    )
    if not rows:
        return []

    df = pd.DataFrame([dict(r) for r in rows], columns=["ds", "y"])
    if df.empty or len(df) < 14:
        return []

    df["ds"] = pd.to_datetime(df["ds"])
    df["y"] = df["y"].astype(float)
    df = df.sort_values("ds")

    forecaster = DiseaseForecaster(
        weekly_seasonality=True,
        yearly_seasonality=False,
        interval_width=0.95,
    )
    forecaster.fit(df, disease_name)
    return forecaster.forecast_7day(7)


@router.get(
    "/{facility_id}",
    response_model=InsightResponse,
    summary="Get unified facility insight",
    description="Combines rules engine, anomaly detection, Z-score analysis, and disease forecasting for a facility.",
)
async def get_insight(facility_id: UUID) -> InsightResponse:
    """
    Get a unified inference result for a facility.

    Steps:
        1. Fetch latest facility_metrics from DB
        2. Run HMISRulesEngine.evaluate() → rule_flags
        3. Load Isolation Forest → score metrics → anomaly_score
        4. Compute Z-scores against last 30 days of data
        5. Combine via RiskScorer → priority_rank
        6. Fetch disease forecast for top disease in this district
        7. Store result in inference_results
    """
    # Step 1: Fetch latest metrics
    metrics_row = await _fetch_latest_metrics(facility_id)
    if not metrics_row:
        raise HTTPException(
            status_code=404,
            detail=f"No facility_metrics found for facility_id={facility_id}",
        )

    district_id = metrics_row.get("district_id")
    facility_name = metrics_row.get("facility_name", "")

    metrics = {
        "icu_occupancy_pct": float(metrics_row["icu_occupancy_pct"]) if metrics_row["icu_occupancy_pct"] else 0,
        "bed_occupancy_pct": float(metrics_row["bed_occupancy_pct"]) if metrics_row["bed_occupancy_pct"] else 0,
        "opd_visits": metrics_row["opd_visits"] or 0,
        "emergency_visits": metrics_row["emergency_visits"] or 0,
        "maternal_deaths": metrics_row["maternal_deaths"] or 0,
        "deliveries": metrics_row["deliveries"] or 0,
        "case_count": getattr(metrics_row, "case_count", 0) or 0,
    }

    # Step 2: Run rules engine
    rule_flags = rules_engine.evaluate(metrics)

    # Step 3: Anomaly detection
    try:
        detector = AnomalyDetector()
        detector.load()
        anomaly_score = detector.score(metrics)
    except (FileNotFoundError, RuntimeError):
        anomaly_score = 0.0

    # Step 4: Z-score analysis
    historical_df = await _fetch_historical_metrics(facility_id, days=30)
    # Only use metrics that exist in facility_metrics
    z_score_metrics = ["opd_visits", "icu_occupancy_pct"]
    z_scores = {}
    for metric in z_score_metrics:
        if metric in historical_df.columns and not historical_df.empty:
            hist_values = historical_df[metric].dropna().values
            if len(hist_values) >= 2:
                import numpy as np
                from scipy import stats
                mean = np.mean(hist_values)
                std = np.std(hist_values, ddof=1)
                current_val = metrics.get(metric, 0)
                z_score = float((current_val - mean) / std) if std > 0 else 0.0
                percentile = int(stats.percentileofscore(hist_values, current_val))
                z_scores[metric] = {
                    "z_score": round(z_score, 4),
                    "is_anomalous": abs(z_score) > 2.5,
                    "percentile": percentile,
                }
            else:
                z_scores[metric] = {"z_score": 0.0, "is_anomalous": False, "percentile": 50}
        else:
            z_scores[metric] = {"z_score": 0.0, "is_anomalous": False, "percentile": 50}

    # Step 5: Risk scoring
    scorer = RiskScorer(current_date=datetime.now(timezone.utc))
    risk_result = scorer.score(
        rule_flags=rule_flags,
        anomaly_score=anomaly_score,
        z_score_results=z_scores,
    )
    priority_rank = risk_result["priority_rank"]

    # Step 6: Disease forecast
    forecast_7day: list[dict] = []
    if district_id:
        top_disease = await _fetch_top_disease(district_id)
        if top_disease:
            forecast_7day = await _get_forecast(top_disease, district_id)

    # Step 6.5: LLM synthesis for HIGH *or* MEDIUM priority (anything where
    # statistical or rules signals exist). LOW-priority facilities still
    # get a forecast + anomaly score, but don't burn an LLM call.
    what_is_happening = None
    why_it_happening = None
    recommended_action = None
    llm_generated = False

    if priority_rank in {"HIGH", "MEDIUM"}:
        # Build a rich, trend-aware context for the LLM instead of just
        # passing today's snapshot. The LLM is then asked (via the
        # synthesizer's SYSTEM_PROMPT) to cite the trajectory.
        trajectory = await _fetch_trajectory(facility_id, days=14)
        trajectory_summary = _summarize_trajectory(trajectory)
        recent_alerts = await _fetch_recent_alerts_for_facility(facility_id, limit=5)

        context = {
            "facility":      facility_name,
            "district_id":   str(district_id) if district_id else None,
            "today":         metrics,
            "trajectory_14d": trajectory,
            "trajectory_summary": trajectory_summary,
            "z_scores":      z_scores,
            "anomaly_score": round(anomaly_score, 4),
            "rule_flags":    [r.get("rule_name") for r in rule_flags],
            "recent_alerts": recent_alerts,
            "top_disease_in_district_last_7d": top_disease,
            "forecast_7day": forecast_7day,
        }

        rag_query = (
            f"{facility_name} "
            f"{', '.join(f.get('rule_name', '') for f in rule_flags)} "
            f"{top_disease or ''}"
        )
        rag_chunks = rag.retrieve(rag_query)
        llm_result = llm.synthesize(context=context, rag_chunks=rag_chunks)
        what_is_happening = llm_result.get("what_is_happening")
        why_it_happening = llm_result.get("why_it_happening")
        recommended_action = llm_result.get("recommended_action")
        llm_generated = bool(what_is_happening)

    # Step 7: Store result in inference_results
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        await Database.execute(
            """
            INSERT INTO inference_results (
                facility_id, district_id, inference_type, severity,
                what_is_happening, why_it_happening, recommended_action,
                confidence_score, rule_flags, llm_generated
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            facility_id,
            district_id,
            "unified_insight",
            priority_rank,
            what_is_happening or f"Unified insight for facility {facility_id}",
            why_it_happening or "Combined rules, anomaly, Z-score, and forecast analysis",
            recommended_action or f"Priority: {priority_rank}",
            abs(anomaly_score),
            str(rule_flags),
            llm_generated,
        )
    except Exception:
        pass  # Non-critical: insight still returned even if storage fails

    return InsightResponse(
        facility_id=str(facility_id),
        rule_flags=rule_flags,
        anomaly_score=round(anomaly_score, 4),
        z_scores=z_scores,
        priority_rank=priority_rank,
        forecast_7day=forecast_7day,
        timestamp=timestamp,
        what_is_happening=what_is_happening,
        why_it_happening=why_it_happening,
        recommended_action=recommended_action,
        llm_generated=llm_generated,
        icu_occupancy_pct=metrics.get("icu_occupancy_pct"),
        bed_occupancy_pct=metrics.get("bed_occupancy_pct"),
        opd_visits=metrics.get("opd_visits"),
    )
