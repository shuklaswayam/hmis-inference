"""Q&A endpoint — policy-aware question answering with optional district context."""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

from backend.database import Database
from backend.llm.synthesizer import LLMSynthesizer
from backend.rag.retriever import PolicyRAG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["qa"])

rag = PolicyRAG()
llm = LLMSynthesizer()

# Same env-driven pattern as alerts.py / websocket.py — the container sees
# Redis at the compose service hostname, not localhost.
_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
redis_client = aioredis.from_url(_REDIS_URL, db=0, decode_responses=True)
CACHE_TTL = 300  # 5 minutes


class AskRequest(BaseModel):
    query: str
    district_id: Optional[str] = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]
    district_id: Optional[str] = None
    timestamp: str


def _cache_key(query: str, district_id: Optional[str]) -> str:
    raw = f"{query}:{district_id}"
    return f"qa:{hashlib.sha256(raw.encode()).hexdigest()}"


async def _fetch_district_summary(district_id: str) -> dict:
    """Fetch aggregated 7-day metrics for a district."""
    rows = await Database.fetch(
        """
        SELECT
            d.name AS district_name,
            d.state,
            d.population,
            COUNT(DISTINCT hf.id) AS facility_count,
            SUM(fm.opd_visits) AS total_opd,
            SUM(fm.emergency_visits) AS total_emergency,
            SUM(fm.maternal_deaths) AS total_maternal_deaths,
            SUM(fm.deliveries) AS total_deliveries,
            AVG(fm.bed_occupancy_pct) AS avg_bed_occupancy,
            AVG(fm.icu_occupancy_pct) AS avg_icu_occupancy
        FROM districts d
        JOIN health_facilities hf ON hf.district_id = d.id
        JOIN facility_metrics fm ON fm.facility_id = hf.id
        WHERE d.id = $1::uuid
          AND fm.reported_date >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY d.id, d.name, d.state, d.population
        """,
        UUID(district_id),
    )
    if not rows:
        return {"district_id": district_id, "note": "No data found for this district in the last 7 days."}
    row = dict(rows[0])
    return {k: float(v) if isinstance(v, (int, float)) else v for k, v in row.items()}


ALERTS_IN_ASK_LIMIT = 10


async def _fetch_recent_alerts(district_id: Optional[str], limit: int = ALERTS_IN_ASK_LIMIT) -> list[dict]:
    """Fetch the most recent active alerts so the AI Assistant can answer
    questions about new incidents. Optionally scoped to a district."""
    base_sql = """
        SELECT
            ir.severity, ir.inference_type, ir.what_is_happening,
            ir.why_it_happening, ir.recommended_action, ir.created_at,
            hf.name AS facility_name,
            d.name  AS district_name
        FROM inference_results ir
        JOIN health_facilities hf ON hf.id = ir.facility_id
        JOIN districts d ON d.id = ir.district_id
        WHERE ir.expires_at IS NULL OR ir.expires_at > NOW()
    """
    if district_id:
        rows = await Database.fetch(
            base_sql + " AND ir.district_id = $1::uuid ORDER BY ir.created_at DESC LIMIT $2",
            UUID(district_id), limit,
        )
    else:
        rows = await Database.fetch(
            base_sql + " ORDER BY ir.created_at DESC LIMIT $1", limit,
        )
    return [dict(r) for r in rows]


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a policy question with optional district context",
)
async def ask_question(req: AskRequest) -> AskResponse:
    # Step 0: Check cache
    cache_key = _cache_key(req.query, req.district_id)
    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return AskResponse(**data)

    # Step 1-2: Retrieve relevant policy chunks
    rag_chunks = rag.retrieve(req.query, n_results=5)
    sources = []
    for chunk in rag_chunks:
        if "]:" in chunk:
            src = chunk.split("]:")[0].lstrip("[")
            if src not in sources:
                sources.append(src)

    # Step 3-5: Build context — district metrics + recent alerts so the LLM
    # can answer questions about the latest events in the state / district.
    context: dict = {"question": req.query}
    recent_alerts = await _fetch_recent_alerts(req.district_id)
    if recent_alerts:
        context["recent_alerts"] = recent_alerts
    if req.district_id is not None:
        district_metrics = await _fetch_district_summary(req.district_id)
        context["district_metrics"] = district_metrics

    # Step 5: LLM synthesis
    llm_result = llm.synthesize(context=context, rag_chunks=rag_chunks)
    answer = llm_result.get("what_is_happening", "")

    # Build response
    result = {
        "question": req.query,
        "answer": answer,
        "sources": sources,
        "district_id": req.district_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Cache in Redis
    try:
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
    except Exception:
        logger.debug("Redis cache write failed", exc_info=True)

    return AskResponse(**result)
