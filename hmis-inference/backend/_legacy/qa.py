"""Q&A endpoint — policy-aware question answering with optional district context.

This router decides whether the user's question is a structured data lookup
(e.g. "list facilities in Bhavnagar", "how is ICU capacity in Ahmedabad") or a
freeform policy/SOP question. Structured queries are answered directly from
the database so we don't confabulate via the LLM. Freeform questions are
answered through the RAG retriever + LLM synthesizer, with a no-answer
fallback when policy documents don't cover the topic.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter
from pydantic import BaseModel

from backend.database import Database
from backend.llm.synthesizer import LLMSynthesizer
from backend.rag.retriever import NO_ANSWER_AVG_DISTANCE, PolicyRAG, RetrievedChunk

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
    # Assembled, human-readable rendering including all three structured
    # fields. Kept for backward compat with the prior contract.
    answer: str
    # Structured analysis sections. Populated when the LLM path runs.
    # Empty for structured-data handlers (intent field tells the caller
    # which handler ran).
    what_is_happening: str = ""
    why_it_happening: str = ""
    recommended_action: str = ""
    sources: list[str]
    district_id: Optional[str] = None
    confidence: Literal["low", "medium", "high"] = "medium"
    intent: str = "policy_llm"
    refused: bool = False
    timestamp: str


def _cache_key(query: str, district_id: Optional[str], intent: str) -> str:
    raw = f"{query}:{district_id}:{intent}"
    return f"qa:{hashlib.sha256(raw.encode()).hexdigest()}"


# ---------------------------------------------------------------------------
# District name normalisation — used by both structured routing and any alert
# text the LLM sees. The seed data uses exact district names; fuzzy-matching
# in precompiled forms is enough for a v1 classifier.
# ---------------------------------------------------------------------------
DISTRICT_NAMES = ["Ahmedabad", "Bhavnagar", "Rajkot", "Surat", "Vadodara"]
_DISTRICT_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in DISTRICT_NAMES) + r")\b", re.IGNORECASE
)
_LIST_FACILITY_RE = re.compile(
    r"\b(facilities|hospitals?|clinics?)\b", re.IGNORECASE
)
_CAPACITY_RE = re.compile(
    r"\b(icu|occupancy|beds?|capacity|surge|overload|critical)\b", re.IGNORECASE
)
_LIST_VERB_RE = re.compile(
    r"^\s*(list|show|which|name)\b", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Alert-context opt-in. Recent alerts were being injected unconditionally,
# which biased every answer toward the VS/Sir T alert template regardless of
# the question. We only inject when the query explicitly touches alerts.
# ---------------------------------------------------------------------------
_ALERT_KEYWORDS = re.compile(
    r"\b(alert|alerts|incidents?|surge|outbreak|flagged|warning|"
    r"recent|latest|24\s*hours?|yesterday|critical\s+alert)\b",
    re.IGNORECASE,
)


def _wants_alerts(query: str) -> bool:
    """True when the question is asking about recent alerts or incidents."""
    return bool(_ALERT_KEYWORDS.search(query))


def _extract_district_name(query: str) -> Optional[str]:
    """Pull the first matching district name out of the query, or None."""
    m = _DISTRICT_RE.search(query)
    return m.group(1).title() if m else None


async def _district_id_for_name(name: str) -> Optional[str]:
    rows = await Database.fetch(
        "SELECT id FROM districts WHERE LOWER(name) = LOWER($1) LIMIT 1",
        name,
    )
    return str(rows[0]["id"]) if rows else None


# ---------------------------------------------------------------------------
# Intent classifier
# ---------------------------------------------------------------------------
IntentKind = Literal[
    "structured_list_facilities",
    "structured_capacity_summary",
    "structured_no_match",
    "policy_llm",
]


async def _classify_intent(
    query: str, district_id: Optional[str]
) -> tuple[IntentKind, dict]:
    """Pick a routing for the question.

    Returns:
        (intent_name, kwargs). ``kwargs`` holds anything the handler needs
        (e.g. ``{"district_id": "...", "district_name": "..."}``).
    """
    q = query.strip()
    district_name = _extract_district_name(q) if not district_id else None
    resolved_district_id = district_id
    if resolved_district_id is None and district_name is not None:
        resolved_district_id = await _district_id_for_name(district_name)

    # 1. Listing facilities ("list facilities in Bhavnagar", "show hospitals in Surat",
    #    "which clinics are in Ahmedabad")
    if (
        _LIST_FACILITY_RE.search(q)
        and _LIST_VERB_RE.match(q + " ") is None  # exclude "give me a list..."
        or (_LIST_VERB_RE.match(q) and _LIST_FACILITY_RE.search(q))
    ):
        return (
            "structured_list_facilities",
            {"district_id": resolved_district_id, "district_name": district_name},
        )

    # 2. Capacity / occupancy question with a district ("how is ICU in Bhavnagar",
    #    "bed occupancy in Ahmedabad", "ICU capacity Vadodara")
    if (
        _CAPACITY_RE.search(q)
        and district_name is not None
        and resolved_district_id is not None
    ):
        return (
            "structured_capacity_summary",
            {"district_id": resolved_district_id, "district_name": district_name},
        )

    if not q:
        return "structured_no_match", {}

    return "policy_llm", {"district_id": district_id}


# ---------------------------------------------------------------------------
# Structured handlers
# ---------------------------------------------------------------------------
async def _handle_list_facilities(kwargs: dict) -> str:
    district_id = kwargs.get("district_id")
    if district_id is None:
        rows = await Database.fetch(
            """
            SELECT hf.name, hf.facility_type, d.name AS district_name
            FROM health_facilities hf
            JOIN districts d ON d.id = hf.district_id
            ORDER BY d.name, hf.name
            """
        )
        if not rows:
            return "No facilities found."
        districts: dict[str, list[str]] = {}
        for r in rows:
            districts.setdefault(r["district_name"], []).append(
                f"{r['name']} ({r['facility_type']})"
            )
        bullet = "\n".join(
            f"- **{d}**: {', '.join(fs)}" for d, fs in districts.items()
        )
        return f"Found {len(rows)} facilities across {len(districts)} districts:\n{bullet}"

    district_name = kwargs.get("district_name") or "the district"
    rows = await Database.fetch(
        """
        SELECT hf.name, hf.facility_type, hf.beds_total, hf.icu_beds
        FROM health_facilities hf
        WHERE hf.district_id = $1::uuid
        ORDER BY hf.name
        """,
        UUID(district_id),
    )
    if not rows:
        return f"No facilities found in {district_name}."
    bullet = "\n".join(
        f"- {r['name']} ({r['facility_type']}, {r['beds_total']} beds, {r['icu_beds']} ICU)"
        for r in rows
    )
    return f"Found {len(rows)} facilities in {district_name}:\n{bullet}"


async def _handle_capacity_summary(kwargs: dict) -> str:
    district_id = kwargs["district_id"]
    district_name = kwargs.get("district_name") or "the district"
    row = await Database.fetchrow(
        """
        SELECT
            COUNT(*) AS facility_count,
            SUM(hf.beds_total) AS total_beds,
            SUM(hf.icu_beds) AS total_icu_beds,
            AVG(fm.bed_occupancy_pct) AS avg_bed,
            AVG(fm.icu_occupancy_pct) AS avg_icu,
            SUM(fm.opd_visits) AS total_opd,
            SUM(fm.emergency_visits) AS total_em
        FROM health_facilities hf
        LEFT JOIN LATERAL (
            SELECT bed_occupancy_pct, icu_occupancy_pct, opd_visits,
                   emergency_visits
            FROM facility_metrics
            WHERE facility_id = hf.id
            ORDER BY reported_date DESC
            LIMIT 1
        ) fm ON TRUE
        WHERE hf.district_id = $1::uuid
        """,
        UUID(district_id),
    )
    if not row or row["facility_count"] == 0:
        return f"No capacity data available for {district_name}."
    return (
        f"**{district_name}** has {row['facility_count']} facilities with "
        f"{row['total_beds']} total beds ({row['total_icu_beds']} ICU beds). "
        f"Latest reported: avg bed occupancy {round(float(row['avg_bed'] or 0), 1)}%, "
        f"avg ICU occupancy {round(float(row['avg_icu'] or 0), 1)}%, "
        f"OPD visits {row['total_opd'] or 0}, emergencies {row['total_em'] or 0} "
        f"(last 24h snapshot from latest facility report)."
    )


# ---------------------------------------------------------------------------
# LLM/orchestration shared state (alerts, RAG chunks, district metrics)
# ---------------------------------------------------------------------------
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


def _confidence_from_chunks(chunks: list[RetrievedChunk]) -> Literal["low", "medium", "high"]:
    """Map mean retrieval distance to a 3-level confidence the caller can show."""
    if not chunks:
        return "low"
    mean = rag.mean_distance(chunks) or 0.0
    if mean < 0.70:
        return "high"
    if mean < NO_ANSWER_AVG_DISTANCE:
        return "medium"
    return "low"


def _build_prompt_context(
    query: str,
    district_id: Optional[str],
    chunks: list[RetrievedChunk],
    alerts: Optional[list[dict]] = None,
) -> tuple[dict, list[str]]:
    """Assemble the structured context the LLM sees.

    Returns ``(context_dict, chunk_prefixes)`` — the prefixes are what we
    surface as ``sources`` in the API response.

    Note: recent alerts are only injected when ``alerts`` is explicitly
    provided (caller decides based on _wants_alerts(query)). The LLM prompt
    labels alerts as ALERT CONTEXT, not "FACILITY DATA", so it doesn't conflate
    them with structured metrics.
    """
    context: dict = {"question": query, "policy_chunk_count": len(chunks)}
    if alerts is not None and alerts:
        context["recent_alerts"] = alerts
    if district_id is not None:
        # Caller passes an awaited result; we set a placeholder here and the
        # caller composes the final context so existing imports stay clean.
        context["_district_id_pending"] = district_id
    sources: list[str] = []
    for c in chunks:
        if c.source not in sources:
            sources.append(c.source)
    return context, sources


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a policy question with optional district context",
)
async def ask_question(req: AskRequest) -> AskResponse:
    # -----------------------------------------------------------------
    # 0. Cache lookup (keyed by query+district+intent so structured and
    #    freeform answers for the same query never stomp each other).
    # -----------------------------------------------------------------
    intent_pre, intent_kwargs = await _classify_intent(req.query, req.district_id)
    cache_key = _cache_key(req.query, req.district_id, intent_pre)
    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return AskResponse(**data)

    # -----------------------------------------------------------------
    # 1. Structured-data handlers
    # -----------------------------------------------------------------
    if intent_pre == "structured_list_facilities":
        answer = await _handle_list_facilities(intent_kwargs)
        return AskResponse(
            question=req.query,
            answer=answer,
            what_is_happening=answer,
            sources=[],
            district_id=intent_kwargs.get("district_id"),
            confidence="high",
            intent=intent_pre,
            refused=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    if intent_pre == "structured_capacity_summary":
        answer = await _handle_capacity_summary(intent_kwargs)
        return AskResponse(
            question=req.query,
            answer=answer,
            what_is_happening=answer,
            sources=[],
            district_id=intent_kwargs["district_id"],
            confidence="high",
            intent=intent_pre,
            refused=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    if intent_pre == "structured_no_match":
        return AskResponse(
            question=req.query,
            answer="Please provide a question.",
            sources=[],
            district_id=req.district_id,
            confidence="low",
            intent=intent_pre,
            refused=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # -----------------------------------------------------------------
    # 2. Freeform question → retrieve policy chunks.
    # -----------------------------------------------------------------
    rag_chunks: list[RetrievedChunk] = rag.retrieve(req.query, n_results=5)
    confidence = _confidence_from_chunks(rag_chunks)
    sources: list[str] = []
    for c in rag_chunks:
        if c.source not in sources:
            sources.append(c.source)

    chunk_prefixes = [c.prefix for c in rag_chunks]

    # -----------------------------------------------------------------
    # 3. No-answer fallback — if retrieval is empty or off-topic, refuse
    #    cleanly so we don't ask the LLM to hallucinate a 2-4 sentence
    #    answer from thin air.
    # -----------------------------------------------------------------
    mean_dist = rag.mean_distance(rag_chunks)
    if not rag_chunks or (mean_dist is not None and mean_dist > NO_ANSWER_AVG_DISTANCE):
        refusal = (
            "I don't have enough information in the policy documents to answer "
            "this question reliably. Please consult the relevant NVBDCP / WHO "
            "guidelines directly, or escalate to the District Malaria Officer."
        )
        return AskResponse(
            question=req.query,
            answer=refusal,
            sources=sources,
            district_id=req.district_id,
            confidence="low",
            intent="policy_llm",
            refused=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # -----------------------------------------------------------------
    # 4. Build context for the LLM.
    #    - recent_alerts only when the question explicitly asks about alerts.
    #    - district_metrics only when a district is in scope, and only fetched
    #      if the request mentions something structured (capacity, totals, etc.)
    # -----------------------------------------------------------------
    context: dict = {"question": req.query}
    if _wants_alerts(req.query):
        context["recent_alerts"] = await _fetch_recent_alerts(req.district_id)
    if req.district_id is not None:
        context["district_metrics"] = await _fetch_district_summary(req.district_id)

    llm_result = llm.synthesize(context=context, rag_chunks=chunk_prefixes)
    what = llm_result.get("what_is_happening") or "The model returned an empty analysis — please retry."
    why = llm_result.get("why_it_happening") or ""
    rec = llm_result.get("recommended_action") or ""

    # `answer` keeps the prior assembled form for backward-compat consumers.
    full_answer = what
    if why:
        full_answer += f"\n\n**Why:** {why}"
    if rec:
        full_answer += f"\n\n**Recommended action:** {rec}"

    result = {
        "question": req.query,
        "answer": full_answer,
        "what_is_happening": what,
        "why_it_happening": why,
        "recommended_action": rec,
        "sources": sources,
        "district_id": req.district_id,
        "confidence": confidence,
        "intent": "policy_llm",
        "refused": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        await redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
    except Exception:
        logger.debug("Redis cache write failed", exc_info=True)

    return AskResponse(**result)
