from __future__ import annotations

import json
import logging
import os
from typing import Any, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from groq import Groq

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a public health analytics assistant for India's HMIS. \
You MUST base your analysis ONLY on the facility data, recent alerts (if any
are present in the input), and policy documents provided. \
Do NOT invent statistics, drug names, or guidelines not present in the input. \
When a *trajectory* (a sequence of daily values over time) is provided, \
REPORT THE TREND: cite the earliest and latest values, the direction of \
movement (climbing / falling / stable), and approximate magnitude. \
When a *forecast* (a Prophet projection of future values) is provided, \
anchor any forward-looking recommendations to it. \
When *z-scores* or *anomaly scores* are provided, treat them as the \
statistical significance of current readings and reference them when \
justifying a HIGH vs MEDIUM vs LOW recommendation. \
If the data is insufficient, say so explicitly. \
When asked about recent incidents, new events, or which facilities are flagged, \
refer to the recent_alerts entries by facility name and severity level. \
Respond in valid JSON with exactly three keys: \
"what_is_happening", "why_it_happening", "recommended_action". \
Keep each value to 2-4 sentences. \
Use plain English; avoid jargon.\
"""

# Per-provider defaults. Overridable via GROQ_MODEL / OLLAMA_MODEL env vars.
_DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_OLLAMA_MODEL = "mistral"

_TIMEOUT = httpx.Timeout(connect=30, read=600, write=30, pool=30)


class LLMConfigError(RuntimeError):
    """Raised when the LLM provider is misconfigured or the call fails."""


def _build_groq_client(api_key: str) -> "Groq":
    """Lazy import so `groq` is optional when LLM_PROVIDER=ollama."""
    from groq import Groq  # noqa: WPS433

    return Groq(api_key=api_key, timeout=_TIMEOUT)


def _read_env(name: str, default: str) -> str:
    """Read a string env var, stripping whitespace; falling back to default."""
    raw = os.environ.get(name, "").strip()
    return raw or default


class LLMSynthesizer:
    """Public-health LLM analyser with two providers: ``ollama`` (default) and ``groq``.

    Provider is selected by ``LLM_PROVIDER`` env var. When ``groq`` is selected
    but configuration is invalid (missing/empty ``GROQ_API_KEY`` or a
    construction failure), failures are now raised loudly on the first call —
    we no longer silently fall back to ollama, which was hiding production bugs.
    """

    def __init__(self) -> None:
        provider = _read_env("LLM_PROVIDER", "ollama").lower()
        if provider not in {"groq", "ollama"}:
            logger.warning("Unknown LLM_PROVIDER=%r — defaulting to ollama", provider)
            provider = "ollama"

        self._provider = provider
        self._groq_model = _read_env("GROQ_MODEL", _DEFAULT_GROQ_MODEL)
        self._ollama_model = _read_env("OLLAMA_MODEL", _DEFAULT_OLLAMA_MODEL)
        self._base_url = _read_env("OLLAMA_BASE_URL", "http://localhost:11434")
        self._groq_client: Groq | None = None
        self._init_error: Exception | None = None

        if self._provider == "groq":
            api_key = _read_env("GROQ_API_KEY", "")
            if not api_key:
                self._init_error = LLMConfigError(
                    "LLM_PROVIDER=groq but GROQ_API_KEY is missing or empty. "
                    "Set GROQ_API_KEY in backend/.env or your environment."
                )
                logger.error("%s", self._init_error)
            else:
                try:
                    self._groq_client = _build_groq_client(api_key)
                    logger.info(
                        "Groq client ready (model=%s)", self._groq_model
                    )
                except Exception as exc:  # noqa: BLE001
                    self._init_error = LLMConfigError(
                        f"Failed to construct Groq client: {exc}"
                    )
                    logger.exception("Failed to build Groq client")

    @property
    def provider(self) -> str:
        """Active provider name (``"groq"`` or ``"ollama"``). Useful for /health."""
        return self._provider

    def healthy(self) -> bool:
        """True when the provider is configured and ready for use."""
        if self._provider == "groq":
            return self._groq_client is not None and self._init_error is None
        return True  # ollama is "ready"; failures surface per-call

    def _call_ollama(self, prompt: str, system_prompt: str = SYSTEM_PROMPT) -> str:
        payload = {
            "model": self._ollama_model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
        }
        try:
            resp = httpx.post(
                f"{self._base_url}/api/generate",
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except Exception:
            logger.exception("Ollama call failed")
            return ""

    def _call_groq(
        self, prompt: str, system_prompt: str = SYSTEM_PROMPT
    ) -> str:
        if self._init_error is not None:
            raise self._init_error
        if self._groq_client is None:
            raise LLMConfigError("Groq client is not initialized")

        try:
            chat = self._groq_client.chat.completions.create(
                model=self._groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                # Force JSON output — Groq enforces schema-side, no client-side
                # parsing required when this is honoured.
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Groq call failed")
            raise LLMConfigError(f"Groq API call failed: {exc}") from exc

        if not chat.choices:
            raise LLMConfigError("Groq returned no choices")
        return chat.choices[0].message.content or ""

    @staticmethod
    def _fallback_unavailable() -> dict[str, Any]:
        return {
            "what_is_happening": (
                "LLM unavailable — analysis could not be generated."
            ),
            "why_it_happening": "",
            "recommended_action": "",
        }

    def synthesize(
        self, context: dict[str, Any], rag_chunks: list[str]
    ) -> dict[str, Any]:
        # Build the prompt with named sections. The previous implementation
        # json.dumps'd the entire context and sliced at 2000 chars, which
        # routinely truncated mid-JSON mid-alert-list — the LLM would then
        # confabulate against a half-cut snapshot of the database.
        #
        # Groq's llama-3.3-70b has a 128k context window, so we no longer
        # need to truncate. We just trim the chunk list to the top 5 most
        # relevant (the retriever already enforces the distance gate) and
        # pass everything through verbatim.
        #
        # ``rag_chunks`` may be either bare strings (legacy chunk format)
        # or ``RetrievedChunk`` objects with a ``text`` attribute (current
        # retriever contract). Normalise to strings here so the join
        # below never blows up.
        def _coerce(chunk: Any) -> str:
            if isinstance(chunk, str):
                return chunk
            return getattr(chunk, "text", str(chunk))

        chunks_text = "\n".join(_coerce(c) for c in rag_chunks[:5]) if rag_chunks else "(none found)"

        prompt = (
            f"QUESTION:\n{context.get('question', '')}\n\n"
            f"FACILITY DATA (structured database rows from HMIS):\n"
            f"{json.dumps(context, default=str, indent=2)}\n\n"
            f"RELEVANT POLICY DOCUMENT EXCERPTS:\n{chunks_text}\n\n"
            f"Generate analysis in JSON format with exactly these three keys:\n"
            f'"what_is_happening", "why_it_happening", "recommended_action".'
        )

        if self._provider == "groq":
            # _call_groq raises on any failure. NO silent fallback.
            raw = self._call_groq(prompt)
        else:
            raw = self._call_ollama(prompt)
            if not raw:
                return self._fallback_unavailable()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "LLM returned non-JSON despite response_format=json_object: %s",
                raw[:200],
            )
            raise LLMConfigError(
                f"LLM returned non-JSON response: {raw[:200]}"
            ) from exc

        return {
            "what_is_happening": parsed.get("what_is_happening", raw),
            "why_it_happening": parsed.get("why_it_happening", ""),
            "recommended_action": parsed.get("recommended_action", ""),
        }
