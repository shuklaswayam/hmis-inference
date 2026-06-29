"""Memo Synthesizer — LLM call for the Policy Insight Narrator (WS4).

Distinct from ``backend.llm.synthesizer.LLMSynthesizer``: the memo
prompt contracts the model into a structured 3-field object:

    {
      "headline":   "<= 1 sentence>",
      "body_md":    "<= 350 words markdown body>",
      "recommended_actions": [
        {"action": "...", "owner": "...", "sla_hours": N}, ...
      ]
}

Failures (LLM unavailable, JSON invalid, etc.) fall back to a
deterministic structured template derived from the same KPI bundle
that would have gone to the model. That way a Redis/LLM outage never
silences the Commissioner's daily brief.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are the Policy Insight Narrator for the Gujarat Health
Commissioner. Your output is a daily briefing derived ONLY from the
KPI bundle below. \
Strict rules: \
- Do not invent statistics, facilities, or interventions not present
  in the bundle. \
- Actions MUST reference a specific item from priority_top5 — never
  propose something absent from that list. \
- Each action carries a single owner and an SLA in hours. Owners come
  from the dispatch table supplied; do not propose new ones. \
- Markdown formatting in body_md only. No HTML. \
- Plain English; avoid jargon. \
Output JSON with exactly these keys:
{ "headline": str, "body_md": str, "recommended_actions":
  [ { "action": str, "owner": str, "sla_hours": int } ] }
recommended_actions must contain 3-5 items.
"""

_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_OLLAMA_MODEL = "mistral"

_TIMEOUT = httpx.Timeout(connect=30, read=600, write=30, pool=30)


@dataclass(frozen=True)
class MemoResult:
    headline: str
    body_md: str
    recommended_actions: list[dict[str, Any]]
    llm_generated: bool


def _read_env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


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
                headline=str(data.get("headline", "")).strip()[:280],
                body_md=str(data.get("body_md", "")).strip()[:4000],
                recommended_actions=list(data.get("recommended_actions", []))[:5],
                llm_generated=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("memo LLM call failed (%s); falling back.", exc)
            return self._structured_template(kpi_bundle)

    # ------------------------------------------------------------------
    # Internal: HTTP / SDK calls
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: str) -> str:
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

        headline = "Daily public-health brief for the Commissioner."
        body_parts: list[str] = [
            "### What needs attention\n",
        ]
        if outbreaks:
            body_parts.append(
                "**Outbreaks** (" + str(len(outbreaks)) + " active signals):\n"
                + "\n".join(f"- {o['one_liner']}" for o in outbreaks)
                + "\n"
            )
        if pressures:
            body_parts.append(
                "**Hospital pressure** (worst " + str(len(pressures)) + " facilities):\n"
                + "\n".join(f"- {p['one_liner']}" for p in pressures)
                + "\n"
            )
        body_parts.append(
            "### What to do\nTop 5 ranked actions are listed below — "
            "execute the highest-severity items inside their SLA.\n"
        )
        body_md = "\n".join(body_parts)

        recommended = [
            {
                "action": a.get("headline", ""),
                "owner": a.get("recommended_owner", "State Health Commissioner"),
                "sla_hours": int(a.get("sla_hours", 24)),
            }
            for a in actions
        ]
        if not recommended:
            recommended = [
                {
                    "action": "No critical signals — continue standard surveillance.",
                    "owner": "District Surveillance Officer",
                    "sla_hours": 72,
                }
            ]
        return MemoResult(
            headline=headline,
            body_md=body_md,
            recommended_actions=recommended,
            llm_generated=False,
        )

    # Tests can swap implementations without touching instance state.
    def _call_for_test(self, prompt: str) -> str:  # pragma: no cover
        return self._call_llm(prompt)
