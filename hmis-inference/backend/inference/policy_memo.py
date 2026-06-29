"""Workstream 4 — Policy Insight Narrator.

Aggregator that:
  1. Reads WS1 (outbreak) + WS2 (pressure) + WS3 (priority rank) state
     (cached when available, freshly computed otherwise).
  2. Builds the KPI bundle.
  3. Calls ``MemoSynthesizer`` to narrate.

The memo endpoint returns the structured memo + the bundle it was
generated from, so the dashboard can render either view.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.llm.memo_synthesizer import MemoSynthesizer
from backend.inference import (
    cache as inference_cache,
    hospital_pressure,
    outbreak_risk,
    priority_rank,
)

logger = logging.getLogger(__name__)


async def _bundle(
    *,
    outbreak_signals: Optional[list[dict]] = None,
    pressure_signals: Optional[list[dict]] = None,
    ranked: Optional[list[dict]] = None,
) -> dict:
    """Compose the KPI bundle fed to the LLM and exposed in the response."""
    outbreak_signals = outbreak_signals or await outbreak_risk.score()
    pressure_signals = pressure_signals or await hospital_pressure.score()
    ranked = ranked or await priority_rank.rank(
        outbreak_signals=outbreak_signals,
        pressure_signals=pressure_signals,
    )
    return {
        "outbreak_top": [
            {
                "district": s["district_name"],
                "disease": s["disease_name"],
                "tier": s["tier"],
                "confidence": s["confidence"],
                "one_liner": s["one_liner"],
            }
            for s in outbreak_signals
            if s["tier"] in {"High", "Critical"}
        ][:3],
        "pressure_top": [
            {
                "facility": s["facility_name"],
                "district": s["district_name"],
                "tier": s["tier"],
                "icu_pct": s["icu_occupancy_pct"],
                "bed_pct": s["bed_occupancy_pct"],
                "icu_pred_48h": s.get("icu_pred_48h"),
                "bed_pred_48h": s.get("bed_pred_48h"),
                "trend": s["trend_48h"],
                "one_liner": s["one_liner"],
            }
            for s in pressure_signals
            if s["tier"] in {"Strained", "Critical"}
        ][:3],
        "priority_top5": ranked[:5],
        "context_window": "last 14 days (outbreaks), 48h ahead (pressure)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def compose(
    *,
    outbreak_signals: Optional[list[dict]] = None,
    pressure_signals: Optional[list[dict]] = None,
    ranked: Optional[list[dict]] = None,
    synthesizer: Optional[MemoSynthesizer] = None,
) -> dict:
    """Compose and narrate the policy memo.

    Optional pre-computed signals let the caller share work between the
    memo endpoint and the dashboard widgets.
    """
    bundle = await _bundle(
        outbreak_signals=outbreak_signals,
        pressure_signals=pressure_signals,
        ranked=ranked,
    )
    synth = synthesizer or MemoSynthesizer()
    memo = synth.synthesize_memo(bundle)
    return {
        "headline": memo.headline,
        "body_md": memo.body_md,
        "recommended_actions": memo.recommended_actions,
        "generated_from": bundle,
        "llm_generated": memo.llm_generated,
    }


def aggregate_severity(ranked: list[dict]) -> tuple[str, float]:
    if not ranked:
        return ("LOW", 0.0)
    sev = ranked[0]["severity"]
    if sev == "CRITICAL":
        return ("CRITICAL", float(ranked[0]["severity_score"]))
    if sev == "HIGH":
        return ("HIGH", float(ranked[0]["severity_score"]))
    return ("MEDIUM", float(ranked[0]["severity_score"]))


# The Redis cache for the memo endpoint piggybacks on the priorities
# call so memo freshness is inherited from WS3 ranking changes.
async def memo_cache_key(*, district_id: Optional[str] = None) -> str:
    return inference_cache.make_key("policy_memo", {"d": district_id or "ALL"})
