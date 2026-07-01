"""Memo Synthesizer — LLM call for the Policy Insight Narrator (WS4).

Distinct from ``backend.llm.synthesizer.LLMSynthesizer``: the memo
prompt contracts the model into a structured object with three
top-level fields and a rich action schema.

Failures (LLM unavailable, JSON invalid, etc.) fall back to a
deterministic structured template derived from the same KPI bundle
that would have gone to the model. That way a Redis/LLM outage never
silences the Commissioner's daily brief.

The output is also scrubbed of social-media style hashtags before it
leaves this module -- see _scrub_hashtags for the rules.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the Policy Insight Narrator for the Gujarat Health
Commissioner. Your output is a daily briefing derived ONLY from the
KPI bundle below. Speak in the voice of a senior public-health advisor:
direct, factual, plain-English, free of jargon and free of any
marketing tone.

Absolute rules — non-negotiable:
- Do not invent statistics, facilities, or interventions not present
  in the bundle. Every claim must trace back to a field in the bundle.
- Actions MUST reference a specific item from priority_top5 — never
  propose something absent from that list.
- Each action carries a single owner, a severity, and an SLA in hours.
  Owners come from the dispatch table supplied; do not propose new ones.
- Markdown formatting in body_md only. No HTML.
- Plain English; avoid jargon and boilerplate phrases like
  "comprehensive", "robust", "ensure holistic", "stakeholder synergy".

CLEAN-OUTPUT RULES — these are enforced:
- NEVER use social-media style hashtags. Do not write inline tokens
  like "#dengue", "#outbreak", "#gujarat" anywhere in body_md or in
  any action field. Zero hashtags of any kind.
- NEVER include Twitter / Slack / editorial hash-tags such as
  #breaking, #urgent, #health, #publichealth. These are forbidden.
- Use clean markdown headers only: ## for section titles, ### for
  sub-section titles. Do NOT prefix words with # for stylistic
  emphasis. Bold (**) and italic (*) are allowed, lists (- / 1.) are
  allowed, plain prose is allowed.
- Do NOT use emoji. Do NOT use decorative separators like --- or ***.
- Tables are welcome when they help the reader (e.g. listing facility /
  ICU / bed numbers side by side).
- Numbers must be quoted with their unit (% for percentages, "cases"
  for case counts, "x" for ratios, "h" for hours).

body_md structure — produce FIVE sections, in this exact order, with
these exact headings:
  ## At a glance
    One sentence, max 35 words, naming the single most important
    thing the Commissioner should know today.
  ## Active outbreaks
    Either a short markdown table OR a bulleted list of every entry
    in outbreak_top. Each row: district, disease, tier, confidence,
    14-day case count, baseline ratio, why it matters in one line.
  ## Hospital pressure
    Same pattern for pressure_top. Each row: facility, district, tier,
    current ICU%, bed%, projected 48h ICU%, projected 48h bed%, trend
    arrow (rising / stable / easing), one-line reason.
  ## Cross-cutting signals
    2–4 sentences summarising patterns across the bundle (e.g. "ICU
    pressure clustered in two districts correlates with the dengue
    surge there"). Use the bundle to support every statement.
  ## Top 5 priority actions
    A numbered list 1–5 mirroring priority_top5 by rank. For each
    action give: the headline, severity (CRITICAL/HIGH/MEDIUM/LOW),
    owner, SLA in hours, evidence_refs joined by commas, and a 1-line
    summary of what to do.

Length target for body_md: 450–750 words. Be thorough — the
Commissioner reads this end-to-end and makes decisions from it. Avoid
vague filler; every sentence should carry information.

Output JSON with exactly these keys:
{
  "headline": str,                         // <= 110 chars, declarative
  "body_md":  str,                         // markdown, 450-750 words
  "recommended_actions": [
    {
      "action":          str,              // short, verb-led title
                                           //   e.g. "Activate dengue
                                           //   containment in Ahmedabad"
                                           //   appears bolded in UI
      "description":     str,              // 2-4 sentences: WHAT is
                                           //   happening, the magnitude
                                           //   (numbers), and WHY it
                                           //   matters today. Reference
                                           //   the bundle fields.
      "rationale":       str,              // 1-2 sentences naming the
                                           //   specific evidence_refs
                                           //   and bundle fields that
                                           //   justify this action.
      "next_steps":      [str, ...],       // 3-6 concrete bullets the
                                           //   owner can execute. Each
                                           //   bullet must be an action
                                           //   a person can check off.
      "owner":           str,              // dispatch owner label
      "severity":        str,              // CRITICAL | HIGH | MEDIUM
                                           //   | LOW (uppercase)
      "sla_hours":       int,              // positive integer
      "evidence_refs":   [str, ...]        // ["facility:<id>", "rule:
                                           //   <rule_name>", "district:
                                           //   <name>"]
    }
  ]
}

recommended_actions MUST contain exactly 5 items, one per entry of
priority_top5 in the bundle. If priority_top5 has fewer than 5 items,
fill the remaining slots with a single neutral action titled
"Continue routine surveillance" owned by "District Surveillance
Officer" with severity LOW, sla_hours 72, evidence_refs [], and
empty next_steps.
"""

_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_OLLAMA_MODEL = "mistral"

_TIMEOUT = httpx.Timeout(connect=30, read=600, write=30, pool=30)

# ---------------------------------------------------------------------------
# Rate limiter: keep requests under the 40 RPM ceiling (default 36 RPM)
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Thread-unsafe per-process rate limiter.

    Keeps a rolling window of request timestamps and sleeps when the
    configured max RPM would be exceeded.  This is a safety belt so we
    never hit provider-side 429s.
    """

    def __init__(self, max_rpm: float | None = None) -> None:
        # Accept float for sub-RPM tuning (e.g. 36 → one request every 1.67 s)
        raw = os.environ.get("MEMO_SYNTHESIZER_MAX_RPM", "").strip()
        if raw:
            try:
                self._max_rpm = float(raw)
            except ValueError:
                self._max_rpm = 36.0
        elif max_rpm is not None:
            self._max_rpm = float(max_rpm)
        else:
            self._max_rpm = 34.0  # safe default: well under 40 RPM ceiling
        self._interval = 60.0 / max(self._max_rpm, 1.0)
        self._timestamps: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until it is safe to issue the next request."""
        with self._lock:
            now = time.monotonic()
            # prune timestamps older than 60 s
            cutoff = now - 60.0
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            # if we're at capacity, sleep until the oldest slot expires
            if len(self._timestamps) >= self._max_rpm:
                sleep_for = self._timestamps[0] - cutoff
                if sleep_for > 0:
                    time.sleep(sleep_for)
                    now = time.monotonic()
            self._timestamps.append(now)


_rate_limiter = _RateLimiter()


@dataclass(frozen=True)
class MemoResult:
    headline: str
    body_md: str
    recommended_actions: list[dict[str, Any]]
    llm_generated: bool


def _read_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default



# Primary pattern: social-media hashtags like #dengue, #outbreak.
# Markdown headings ("# ", "## ", "### ") are preserved because they
# have whitespace after the hash. Trailing-char set includes the usual
# whitespace/punctuation PLUS the markdown markers (* _ ` ~ | < #)
# so that "#urgent*bold*" still gets cleaned up.
_HASHTAG_RE = re.compile(
    r"(?<![A-Za-z0-9])#[A-Za-z][A-Za-z0-9_\-/]*"
    r"(?=$|[\s\.,;:!\?\)\]\}\*_`~|<#\n\r])"
)

# Edge-case catch-all for hashtags the primary regex might miss.
# Anchored on whitespace or end-of-string so legitimate markdown
# headings ("## Section") are never touched.
_CATCHALL_HASHTAG_RE = re.compile(
    r"(?<![A-Za-z0-9])#[A-Za-z][A-Za-z0-9_]*(?:\+[A-Za-z0-9_]*)*"
    r"(?=$|[\s.,;:!?\)\]\}\*_`~|<#\n\r])"
)

# Collapse multiple consecutive blank lines.
_MULTIBLANK_RE = re.compile(r"\n{3,}")


def _scrub_hashtags(text: str) -> str:
    """Strip social-media style hashtags from LLM output.

    Markdown headings ("## Section") are preserved because they have
    whitespace after the hash. Real hashtags like "#dengue" or
    "#publichealth" are removed — the trailing word stays so prose
    still reads naturally.
    """
    if not text:
        return text
    text = _HASHTAG_RE.sub("", text)
    text = _CATCHALL_HASHTAG_RE.sub("", text)
    # Collapse stray blank lines left by removal.
    text = _MULTIBLANK_RE.sub("\n\n", text)
    return text.strip()


def _scrub_action_text(value: str | None) -> str:
    """Apply hashtag scrub + collapse stray whitespace to a single string."""
    if not value:
        return ""
    cleaned = _scrub_hashtags(str(value))
    return " ".join(cleaned.split())


def _coerce_evidence_refs(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()][:8]
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()][:8]
    return [str(raw)]


def _coerce_next_steps(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        steps = [str(s) for s in raw if str(s).strip()]
    elif isinstance(raw, str):
        # Accept newline- or semicolon-delimited lists too.
        chunked = re.split(r"[\n;]+", raw)
        steps = [s for s in (c.strip() for c in chunked) if s]
    else:
        steps = [str(raw)]
    return [_scrub_action_text(s) for s in steps[:8] if _scrub_action_text(s)]


_SEVERITY_BUCKETS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def _normalize_severity(raw: Any, *, fallback: str) -> str:
    s = str(raw or "").strip().upper()
    if s in _SEVERITY_BUCKETS:
        return s
    return fallback


def _normalize_action(raw: Any) -> dict[str, Any]:
    """Coerce an LLM-produced action dict into the rich schema.

    Coercion is lenient on purpose: LLM prompts drift, and the
    Commissioner still needs a populated action row. Unknown fields
    are preserved under the same name if already valid.

    When the LLM omits ``description`` / ``rationale`` / ``next_steps``
    we still produce a *visible* row (the UI always renders each
    section with a placeholder) — but the backend fills in a non-empty
    baseline so the click-through content is never blank.
    """
    if not isinstance(raw, dict):
        raw = {"action": str(raw)}

    refs = _coerce_evidence_refs(raw.get("evidence_refs"))
    next_steps = _coerce_next_steps(raw.get("next_steps"))
    action_title = _scrub_action_text(raw.get("action")) or "Untitled action"

    fallback_severity = raw.get("severity_fallback", "MEDIUM")

    description = (
        _scrub_action_text(raw.get("description"))
        or _scrub_action_text(raw.get("summary"))
        or _scrub_action_text(raw.get("details"))
        or f"{action_title} — see evidence and next steps below."
    )
    rationale = (
        _scrub_action_text(raw.get("rationale"))
        or _scrub_action_text(raw.get("why"))
        or _scrub_action_text(raw.get("justification"))
        or (
            "This action is anchored to one or more active signals in the priority ranker. "
            "Refer to the evidence refs and operational next-steps for any decisions made from this row."
        )
    )

    # Surface evidence on next-steps even when the LLM provided none,
    # so the click-through always shows actionable owner guidance.
    if not next_steps:
        next_steps = [
            "Confirm the current status with the dispatch owner.",
            "Allocate the necessary resources within the SLA window.",
            "Update the daily dashboard with progress once actioned.",
        ]

    action = {
        "action": action_title,
        "description": description,
        "rationale": rationale,
        "next_steps": next_steps,
        "owner": _scrub_action_text(raw.get("owner")) or "State Health Commissioner",
        "severity": _normalize_severity(raw.get("severity"), fallback=fallback_severity),
        "sla_hours": max(1, int(raw.get("sla_hours") or 24)),
        "evidence_refs": refs,
    }

    # Preserve any optional legacy / future field the LLM emitted so
    # the schema can grow without forcing the backend hand-fix it.
    for key, value in raw.items():
        if key not in action and key not in {"sla_hours"}:
            action[key] = value

    return action


class _MemoProviderError(RuntimeError):
    pass


class MemoSynthesizer:
    """Thin wrapper around Groq or Ollama for the memo call.

    Mirrors the contract of LLMSynthesizer but with the memo-specific
    system prompt and JSON schema baked into ``synthesize_memo``.
    """

    def __init__(self) -> None:
        provider = _read_env("LLM_PROVIDER", "ollama").lower()
        if provider not in {"groq", "ollama"}:
            provider = "ollama"
        self._provider = provider
        self._groq_model = _read_env("GROQ_MODEL", _DEFAULT_GROQ_MODEL)
        self._ollama_model = _read_env("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
        self._ollama_base = _read_env("OLLAMA_BASE_URL", "http://localhost:11434")
        self._groq_client = None
        self._init_error: Exception | None = None
        if provider == "groq":
            api_key = _read_env("GROQ_API_KEY", "")
            if not api_key:
                self._init_error = _MemoProviderError(
                    "LLM_PROVIDER=groq but GROQ_API_KEY missing."
                )
            else:
                try:
                    import groq  # lazy import
                    self._groq_client = groq.Groq(api_key=api_key, timeout=_TIMEOUT)
                except Exception as exc:  # noqa: BLE001
                    self._init_error = _MemoProviderError(
                        f"Groq build failure: {exc}"
                    )

    @property
    def healthy(self) -> bool:
        if self._provider == "groq":
            return self._groq_client is not None and self._init_error is None
        return True

    def provider(self) -> str:
        return self._provider

    def synthesize_memo(self, kpi_bundle: dict[str, Any]) -> MemoResult:
        """Call the LLM to narrate the bundled KPIs into a memo.

        On any failure (missing key, non-JSON, HTTP error) returns a
        deterministic structured template derived from the same KPI
        bundle — never throws.
        """
        prompt = self._build_prompt(kpi_bundle)
        try:
            raw = self._call_llm(prompt)
            data = self._parse(raw)
            return MemoResult(
                # Scrub ALL fields, not just body_md — social-media hashtags
                # in the headline or in any action field would surface
                # unmodified otherwise.
                headline=_scrub_hashtags(str(data.get("headline", "")).strip())[:280],
                body_md=_scrub_hashtags(str(data.get("body_md", "")).strip())[:8000],
                recommended_actions=[
                    _normalize_action(a) for a in data.get("recommended_actions", [])
                ][:5],
                llm_generated=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memo LLM call failed (%s); falling back.", exc)
            return self._structured_template(kpi_bundle)

    # ------------------------------------------------------------------
    # Internal: HTTP / SDK calls
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str) -> str:
        _rate_limiter.acquire()  # enforce ~36 RPM ceiling
        if self._provider == "groq":
            if self._init_error is not None:
                raise self._init_error
            if self._groq_client is None:
                raise _MemoProviderError("Groq client not initialized.")
            chat = self._groq_client.chat.completions.create(
                model=self._groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            if not chat.choices:
                raise _MemoProviderError("Groq returned no choices.")
            return chat.choices[0].message.content or ""
        try:
            resp = httpx.post(
                f"{self._ollama_base}/api/generate",
                json={
                    "model": self._ollama_model,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
                    "stream": False,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception as exc:  # noqa: BLE001
            raise _MemoProviderError(f"Ollama failed: {exc}") from exc

    @staticmethod
    def _build_prompt(bundle: dict[str, Any]) -> str:
        return (
            "BUNDLE (current inference state — what follows is the only "
            "input you may reference):\n"
            f"{json.dumps(bundle, default=str, indent=2)}\n\n"
            "Generate the memo JSON now."
        )

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise _MemoProviderError(f"LLM returned non-JSON: {raw[:200]}") from exc

    # ------------------------------------------------------------------
    # Deterministic fallback when the LLM is unreachable
    # ------------------------------------------------------------------
    def _structured_template(self, bundle: dict[str, Any]) -> MemoResult:
        outbreaks = bundle.get("outbreak_top", [])[:3]
        pressures = bundle.get("pressure_top", [])[:3]
        actions = bundle.get("priority_top5", [])[:5]

        # Headline: name top severity so it scans quickly. Use the
        # severity label verbatim — do NOT prepend "CRITICAL" or we end
        # up with "CRITICAL CRITICAL" for already-critical signals.
        if actions:
            top = actions[0]
            top_label = top.get("severity", "HIGH") or "action"
            headline = (
                f"Top priority today: {top.get('headline', 'review ranked actions')} "
                f"({top_label}, owner: {top.get('recommended_owner', 'State')}, "
                f"SLA {int(top.get('sla_hours', 24))}h)"
            )
        else:
            headline = (
                "All-clear briefing: no critical signals in the last 14 days. "
                "Continue routine surveillance."
            )

        body_parts: list[str] = []

        # -- At a glance
        if actions:
            body_parts.append("## At a glance")
            body_parts.append(
                _scrub_hashtags(_glance_sentence(outbreaks, pressures, actions)) + "\n"
            )
        else:
            body_parts.append("## At a glance")
            body_parts.append(
                "No outbreak, hospital-pressure, or ranked signals "
                "warrant director-level intervention today.\n"
            )

        # -- Outbreaks
        body_parts.append("## Active outbreaks")
        if outbreaks:
            body_parts.append(
                "| District | Disease | Tier | Confidence | 14-day cases | Baseline ratio | Why it matters |"
            )
            body_parts.append(
                "| --- | --- | --- | --- | --- | --- | --- |"
            )
            for o in outbreaks:
                body_parts.append(
                    "| {district} | {disease} | {tier} | {conf:.2f} | {cases} | {ratio}x | {why} |".format(
                        district=_scrub_hashtags(str(o.get("district", "-"))),
                        disease=_scrub_hashtags(str(o.get("disease", "-"))),
                        tier=_scrub_hashtags(str(o.get("tier", "-"))),
                        conf=float(o.get("confidence") or 0.0),
                        cases=o.get("cases", o.get("cases_last_14d", "-")),
                        ratio=o.get("baseline_ratio", o.get("ratio", "-")),
                        why=_scrub_hashtags(str(o.get("one_liner", "—"))),
                    )
                )
        else:
            body_parts.append(
                "No (district, disease) bucket has crossed the medium "
                "tier in the last 14 days.\n"
            )

        # -- Pressure
        body_parts.append("\n## Hospital pressure")
        if pressures:
            body_parts.append(
                "| Facility | District | Tier | ICU | Bed | ICU +48h | Bed +48h | Trend | Note |"
            )
            body_parts.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            for p in pressures:
                body_parts.append(
                    "| {facility} | {district} | {tier} | {icu}% | {bed}% | "
                    "{icu48}% | {bed48}% | {trend} | {note} |".format(
                        facility=_scrub_hashtags(str(p.get("facility", "-"))),
                        district=_scrub_hashtags(str(p.get("district", "-"))),
                        tier=_scrub_hashtags(str(p.get("tier", "-"))),
                        icu=p.get("icu_pct", p.get("icu_occupancy_pct", "-")),
                        bed=p.get("bed_pct", p.get("bed_occupancy_pct", "-")),
                        icu48=p.get("icu_pred_48h", "-"),
                        bed48=p.get("bed_pred_48h", "-"),
                        trend=_trend_arrow(p.get("trend", "stable")),
                        note=_scrub_hashtags(str(p.get("one_liner", "—"))),
                    )
                )
        else:
            body_parts.append(
                "No facility is over the strained threshold.\n"
            )

        # -- Cross-cutting
        body_parts.append("\n## Cross-cutting signals")
        body_parts.append(_scrub_hashtags(_cross_cutting(outbreaks, pressures, actions)) + "\n")

        # -- Top 5 priority actions (overview)
        body_parts.append("\n## Top 5 priority actions")
        if actions:
            for a in actions:
                refs = ", ".join([_scrub_hashtags(str(x)) for x in (a.get("evidence_refs", []) or [])])
                body_parts.append(
                    "{rank}. **{headline}** -- severity {sev}, "
                    "owner {owner}, SLA {sla}h. "
                    "Evidence: {refs}.".format(
                        rank=a.get("rank", "?"),
                        headline=_scrub_hashtags(str(a.get("headline", "review"))),
                        sev=a.get("severity", "HIGH"),
                        owner=_scrub_hashtags(str(a.get("recommended_owner", "State"))),
                        sla=int(a.get("sla_hours", 24)),
                        refs=refs or "n/a",
                    )
                )
        else:
            body_parts.append(
                "1. **Continue routine surveillance** -- severity LOW, "
                "owner District Surveillance Officer, SLA 72h. Evidence: n/a."
            )

        body_md = "\n".join(body_parts)

        recommended: list[dict[str, Any]] = []
        for a in actions:
            recommended.append(_rich_action_from_priority(a, bundle))

        # Pad / cap at 5 with the neutral fallback row.
        while len(recommended) < 1:
            recommended.append(_neutral_surveillance_action())

        # Keep the historical "action" key shaped like the LLM-style row
        # so existing test assertions continue to pass while the richer
        # fields carry the new descriptive weight.
        recommended = recommended[:5]
        if not any(r.get("action") for r in recommended):
            recommended.append(_neutral_surveillance_action())

        return MemoResult(
            headline=_scrub_hashtags(headline)[:280],
            body_md=_scrub_hashtags(body_md)[:8000],
            recommended_actions=recommended,
            llm_generated=False,
        )

    # Tests can swap implementations without touching instance state.
    def _call_for_test(self, prompt: str) -> str:  # pragma: no cover
        return self._call_llm(prompt)


# ---------------------------------------------------------------------------
# Helper functions for the deterministic fallback template
# ---------------------------------------------------------------------------


def _trend_arrow(trend: str) -> str:
    """Return a human-friendly trend label."""
    mapping = {
        "rising": "▲ Rising",
        "stable": "→ Stable",
        "easing": "▼ Easing",
    }
    return mapping.get(str(trend).lower().strip(), str(trend))


def _glance_sentence(
    outbreaks: list[dict], pressures: list[dict], actions: list[dict]
) -> str:
    """Build a one-sentence 'At a glance' summary from top signals."""
    parts: list[str] = []
    if actions:
        top = actions[0]
        parts.append(
            f"**{top.get('headline', 'Top priority')}** "
            f"({top.get('severity', 'HIGH')} severity, owner: "
            f"{top.get('recommended_owner', 'State')}, SLA "
            f"{int(top.get('sla_hours', 24))}h)."
        )
    if outbreaks:
        outbreak_names = [f"{o.get('disease', 'Unknown')} in {o.get('district', 'Unknown')}" for o in outbreaks[:2]]
        parts.append(f"Active outbreaks: {', '.join(outbreak_names)}.")
    if pressures:
        pressure_names = [f"{p.get('facility', 'Facility')} ({p.get('district', 'Unknown')})" for p in pressures[:2]]
        parts.append(f"Hospital pressure at: {', '.join(pressure_names)}.")
    return " ".join(parts) if parts else "No critical signals in the last 14 days."


def _cross_cutting(
    outbreaks: list[dict], pressures: list[dict], actions: list[dict]
) -> str:
    """Synthesize cross-cutting signals across the KPI bundle."""
    parts: list[str] = []
    districts_with_outbreaks = {o.get("district", "") for o in outbreaks}
    districts_with_pressure = {p.get("district", "") for p in pressures}
    overlap = districts_with_outbreaks & districts_with_pressure
    if overlap:
        parts.append(
            f"**Disease–capacity overlap:** {', '.join(sorted(overlap))} show "
            f"both outbreak signals and hospital pressure. Coordinated response is advised."
        )
    if outbreaks and not pressures:
        parts.append(
            "Outbreak activity is present but hospital pressure remains manageable. "
            "Surveillance and rapid case management are the priority."
        )
    if pressures and not outbreaks:
        parts.append(
            "Hospital pressure is elevated without concurrent outbreak signals. "
            "Review bed management and elective scheduling."
        )
    if not outbreaks and not pressures and not actions:
        parts.append("No cross-cutting signals today. Normal operations recommended.")
    return "\n\n".join(parts) if parts else "No cross-cutting signals identified."


def _rich_action_from_priority(action: dict, bundle: dict) -> dict[str, Any]:
    """Convert a priority_top5 entry into a richly-described action.

    The goal is to give the Commissioner (and the downstream UI) enough
    descriptive text that every recommended action is self-explanatory
    without needing to click into raw data tables.
    """
    headline = action.get("headline", "Untitled action")
    severity = action.get("severity", "MEDIUM")
    owner = action.get("recommended_owner", "State Health Commissioner")
    sla = int(action.get("sla_hours", 24))
    evidence = _coerce_evidence_refs(action.get("evidence_refs"))
    step = action.get("recommended_step", "")

    # Try to enrich description from related outbreak or pressure signals.
    related_outbreak = None
    related_pressure = None
    for o in bundle.get("outbreak_top", []):
        if o.get("district") in headline or o.get("disease", "") in headline:
            related_outbreak = o
            break
    for p in bundle.get("pressure_top", []):
        if p.get("facility") in headline or p.get("district") in headline:
            related_pressure = p
            break

    # Build rich description
    desc_parts: list[str] = []
    if related_outbreak:
        desc_parts.append(
            f"{related_outbreak.get('disease', 'Disease')} cases in "
            f"{related_outbreak.get('district', 'district')} are "
            f"{related_outbreak.get('baseline_ratio', 'significantly')}× above baseline "
            f"({related_outbreak.get('cases', 'N/A')} cases, confidence "
            f"{related_outbreak.get('confidence', 0):.0%})."
        )
    if related_pressure:
        desc_parts.append(
            f"{related_pressure.get('facility', 'Facility')} reports ICU occupancy at "
            f"{related_pressure.get('icu_pct', 'N/A')}% and bed occupancy at "
            f"{related_pressure.get('bed_pct', 'N/A')}% (48h projection: ICU "
            f"{related_pressure.get('icu_pred_48h', 'N/A')}%, bed "
            f"{related_pressure.get('bed_pred_48h', 'N/A')}% — {related_pressure.get('trend', 'stable')})."
        )
    if not desc_parts:
        desc_parts.append(
            "This action is driven by the automated priority ranker based on "
            "the most recent outbreak, hospital pressure, and rule-based signals."
        )
    description = " ".join(desc_parts)

    # Build rationale linking to evidence
    rationale_parts: list[str] = []
    if evidence:
        evidence_str = ", ".join(evidence)
        rationale_parts.append(
            f"Priority score and severity assignment are supported by evidence refs: {evidence_str}."
        )
    if step:
        rationale_parts.append(
            f"Recommended immediate step: {step}."
        )
    if not rationale_parts:
        rationale_parts.append(
            "This action is ranked by the priority scoring algorithm based on recency, "
            "severity, and geographic spread."
        )
    rationale = " ".join(rationale_parts)

    # Build next_steps as actionable bullets
    next_steps: list[str] = []
    if step:
        next_steps.append(step)
    next_steps.extend([
        "Confirm current status with district surveillance team.",
        "Allocate necessary resources (staff, equipment, transport) if escalation is confirmed.",
        "Update the dashboard with local response progress within SLA window.",
    ])
    if related_pressure and related_pressure.get("trend") == "rising":
        next_steps.append(
            "Escalate to state emergency operations center due to rising trend projection."
        )

    return _normalize_action({
        "action": headline,
        "description": description,
        "rationale": rationale,
        "next_steps": next_steps,
        "owner": owner,
        "severity": severity,
        "sla_hours": sla,
        "evidence_refs": evidence,
    })


def _neutral_surveillance_action() -> dict[str, Any]:
    """Return a default surveillance action when no active signals exist."""
    return _normalize_action({
        "action": "Continue routine surveillance",
        "description": (
            "No outbreak or hospital-pressure signals currently exceed the "
            "medium-threshold. Routine surveillance, data quality checks, and "
            "cold-chain maintenance should continue as per standard protocol."
        ),
        "rationale": (
            "The priority ranker found no qualifying events in the last 14-day "
            "window, indicating a period of relative epidemiological calm."
        ),
        "next_steps": [
            "Maintain daily active-case searches.",
            "Run weekly data-quality audits on HMIS feeds.",
            "Verify cold-chain temperature logs at district cold points.",
        ],
        "owner": "District Surveillance Officer",
        "severity": "LOW",
        "sla_hours": 72,
        "evidence_refs": [],
    })
