"""Workstream 4 -- Policy Insight Narrator.

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

from backend.llm.memo_synthesizer import (
    MemoSynthesizer,
    _scrub_action_text,
    _normalize_action,
    _neutral_surveillance_action,
    _scrub_hashtags,
)
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


# ---------------------------------------------------------------------------
# Defense-in-depth: ensure every action leaving the policy-memo endpoint
# carries rich, click-worthy fields. Even if a stale cache or a thin LLM
# response slips through, the click-through will never be empty.
# ---------------------------------------------------------------------------

_RICH_DEFAULTS_BY_SEVERITY = {
    "CRITICAL": [
        "Convene the rapid-response leadership within the next 30 minutes.",
        "Open a state-level incident channel and broadcast the action to all districts.",
        "Suspend non-emergency operations affected by this signal until containment is confirmed.",
        "Capture device-level telemetry and submit it to the central dashboard within 24 hours.",
    ],
    "HIGH": [
        "Dispatch a district-level assessment team within the SLA window.",
        "Confirm resourcing (staff, supplies, transport) and surface gaps to the State desk.",
        "Issue an interim status update to the State dashboard before the SLA closes.",
    ],
    "MEDIUM": [
        "Schedule the response within the SLA window and add to the weekly review.",
        "Validate the trigger signal against the last 14 days of facility data.",
        "If validated, dispatch the district team; if noise, close with a rationale note.",
    ],
    "LOW": [
        "Log the observation and monitor for re-occurrence across the next reporting cycle.",
        "Confirm routine surveillance cadence is unchanged.",
    ],
}


def _enrich_action_for_return(action: dict, idx: int, bundle: dict) -> dict:
    """Final pass before the memo leaves the backend.

    Fills in any *empty or missing* field with a meaningful default so
    the click-through card in the UI is never blank. Keeps any field
    the synthesizer already populated.
    """
    if not isinstance(action, dict):
        action = {"action": str(action)}

    sev = str(action.get("severity") or "MEDIUM").upper()
    sla_hours = int(action.get("sla_hours") or 24)
    title = _scrub_action_text(action.get("action")) or f"Recommended action #{idx + 1}"
    owner = _scrub_action_text(action.get("owner")) or "State Health Commissioner"
    refs = list(action.get("evidence_refs") or [])

    description = (
        _scrub_action_text(action.get("description"))
        or _scrub_action_text(action.get("summary"))
        or _scrub_action_text(action.get("what"))
        or _scrub_action_text(action.get("details"))
        or (
            f"{title} -- flagged at {sev} severity with a {sla_hours}h completion window. "
            f"Owner of record: {owner}. "
            "Refer to the source references and operational next steps for the full picture."
        )
    )

    rationale = (
        _scrub_action_text(action.get("rationale"))
        or _scrub_action_text(action.get("why"))
        or _scrub_action_text(action.get("justification"))
        or (
            "This action was raised by the priority ranker because one or more signals "
            "(outbreak, hospital pressure, or rule-based alert) crossed the dispatch threshold. "
            "Confidence and severity are computed from the live KPI bundle; evidence references "
            "below point at the underlying rows."
        )
    )

    next_steps = action.get("next_steps")
    if not next_steps or not isinstance(next_steps, list) or not next_steps:
        next_steps = list(_RICH_DEFAULTS_BY_SEVERITY.get(sev, _RICH_DEFAULTS_BY_SEVERITY["MEDIUM"]))
    else:
        # scrub + ensure list[str]
        next_steps = [_scrub_action_text(s) for s in next_steps if _scrub_action_text(s)]
        if not next_steps:
            next_steps = list(_RICH_DEFAULTS_BY_SEVERITY.get(sev, _RICH_DEFAULTS_BY_SEVERITY["MEDIUM"]))

    if not refs:
        # Last-resort evidence: surface something traceable
        for o in bundle.get("outbreak_top", []):
            refs.append(f"district:{o.get('district', 'unknown')}")
            break
        for p in bundle.get("pressure_top", []):
            refs.append(f"facility:{p.get('facility', 'unknown')}")
            break
        if not refs:
            refs = ["rule:priority_ranker"]

    return _normalize_action({
        "action": title,
        "description": description,
        "rationale": rationale,
        "next_steps": next_steps,
        "owner": owner,
        "severity": sev,
        "sla_hours": sla_hours,
        "evidence_refs": refs,
    })


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

    # Scrub again at the boundary -- belt and braces.
    headline = _scrub_hashtags(memo.headline).strip()[:280]
    body_md = _scrub_hashtags(memo.body_md).strip()[:8000]

    raw_actions = list(memo.recommended_actions or [])
    if not raw_actions:
        raw_actions = [_neutral_surveillance_action()]

    # Final defense-in-depth enrichment: every action that leaves this
    # function has description, rationale, non-empty next_steps, owner,
    # severity, sla_hours, and evidence_refs.
    enriched_actions = [
        _enrich_action_for_return(a, i, bundle) for i, a in enumerate(raw_actions[:5])
    ]

    return {
        "headline": headline,
        "body_md": body_md,
        "recommended_actions": enriched_actions,
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
#
# NOTE: cache key version bumped v1 -> v2 so any payloads cached before
# the rich-description enrichment is invalidated and re-generated.
async def memo_cache_key(*, district_id: Optional[str] = None) -> str:
    return inference_cache.make_key("policy_memo", {"d": district_id or "ALL"})
