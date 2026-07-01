"""
Unit tests for Workstream 4 — Policy Memo synthesizer.

We focus on the deterministic fallback template (the LLM path is
unreachable in unit tests; covered by integration tests instead).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from backend.llm.memo_synthesizer import MemoSynthesizer


def _bundle(**overrides) -> dict:
    base = {
        "outbreak_top": [
            {
                "district": "Ahmedabad",
                "disease": "Dengue",
                "tier": "High",
                "confidence": 0.83,
                "one_liner": "Dengue in Ahmedabad: High (4.1× baseline)",
            }
        ],
        "pressure_top": [
            {
                "facility": "Civil Hospital Ahmedabad",
                "district": "Ahmedabad",
                "tier": "Critical",
                "icu_pct": 92.0,
                "bed_pct": 96.0,
                "icu_pred_48h": 95.0,
                "bed_pred_48h": 97.0,
                "trend": "rising",
                "one_liner": "Civil Hospital Ahmedabad: Critical (ICU 92% / bed 96%)",
            }
        ],
        "priority_top5": [
            {
                "rank": 1,
                "headline": "ICU emergency at Civil Hospital Ahmedabad",
                "severity": "CRITICAL",
                "severity_score": 9.5,
                "recommended_owner": "Facility In-Charge + State",
                "sla_hours": 4,
                "evidence_refs": ["facility:abc-123", "rule:icu_critical"],
                "recommended_step": "Declare ICU emergency; halt electives.",
            }
        ],
        "context_window": "last 14 days / 48h ahead",
        "generated_at": "2026-06-27T18:14:00Z",
    }
    base.update(overrides)
    return base


def test_synthesizer_falls_back_when_provider_empty():
    # We exercise the structured-template path by invoking the same
    # private method that handles exceptions — keeps CI hermetic.
    synth = MemoSynthesizer()
    fallback = synth._structured_template(_bundle())
    assert fallback.llm_generated is False
    assert fallback.headline
    assert "outbreaks" in fallback.body_md.lower()
    assert "Hospital pressure" in fallback.body_md
    actions = fallback.recommended_actions
    assert any(a["sla_hours"] == 4 for a in actions)
    # richer fallback fields
    top = actions[0]
    assert top.get("description")
    assert top.get("rationale")
    assert top.get("next_steps")
    assert top.get("evidence_refs")


def test_synthesizer_fallback_handles_empty_priority_top5():
    synth = MemoSynthesizer()
    bundle = _bundle()
    bundle["priority_top5"] = []
    bundle["outbreak_top"] = []
    bundle["pressure_top"] = []
    fallback = synth._structured_template(bundle)
    assert fallback.llm_generated is False
    # At least one default action must always be present.
    assert len(fallback.recommended_actions) >= 1
    assert fallback.recommended_actions[0]["owner"]


def test_synthesizer_marker_for_ai_generated_true_remains():
    # The path that returns success uses llm_generated=True. We tap the
    # fallback which should always be False — guard against future
    # regressions marking fallback as LLM-generated.
    synth = MemoSynthesizer()
    fallback = synth._structured_template(_bundle())
    assert fallback.llm_generated is False


def test_synthesizer_fallback_takes_top_5_actions():
    """The structured template caps recommended_actions at 5 (the
    Commissioner's daily brief is bounded)."""
    synth = MemoSynthesizer()
    bundle = _bundle()
    bundle["priority_top5"] = [
        {"rank": i, "headline": f"a-{i}", "severity": "HIGH",
         "severity_score": 5.0, "recommended_owner": "X",
         "sla_hours": 12, "evidence_refs": [], "recommended_step": "step"}
        for i in range(1, 9)
    ]
    fallback = synth._structured_template(bundle)
    assert len(fallback.recommended_actions) == 5
    # Order is preserved from input.
    assert fallback.recommended_actions[0]["action"] == "a-1"


def test_synthesizer_provider_field_returns_string():
    synth = MemoSynthesizer()
    name = synth.provider()
    assert name in ("groq", "ollama")
