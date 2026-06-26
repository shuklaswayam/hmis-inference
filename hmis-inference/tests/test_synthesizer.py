"""Tests for backend.llm.synthesizer.

These cover the failures we used to hide with the silent ``groq → ollama``
fallback. After these changes:
    * Groq init errors must be raised at first call, not silenced.
    * Groq runtime errors must be raised, not returned as a placeholder.
    * Groq JSON-mode must be requested on every call.
    * Per-provider model env vars must not bleed across each other.
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """Strip all LLM_* / GROQ_* / OLLAMA_* env vars before each test."""
    for key in list(os.environ):
        if key.startswith(("LLM_", "GROQ_", "OLLAMA_")):
            monkeypatch.delenv(key, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def test_default_provider_is_ollama(clean_env):
    from backend.llm.synthesizer import LLMSynthesizer

    llm = LLMSynthesizer()
    assert llm.provider == "ollama"
    assert llm.healthy() is True


def test_unknown_provider_falls_back_to_ollama(clean_env):
    from backend.llm.synthesizer import LLMSynthesizer

    clean_env.setenv("LLM_PROVIDER", "openai")
    llm = LLMSynthesizer()
    assert llm.provider == "ollama"


def test_per_provider_model_env_vars_do_not_leak(clean_env):
    """The OLLAMA_MODEL bug: previously the same `_model` was used for both
    providers regardless of LLM_PROVIDER."""
    from backend.llm.synthesizer import LLMSynthesizer

    clean_env.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    clean_env.setenv("OLLAMA_MODEL", "llama3.2")
    llm = LLMSynthesizer()  # default provider = ollama
    assert llm._groq_model == "llama-3.1-8b-instant"
    assert llm._ollama_model == "llama3.2"
    assert llm._groq_model != llm._ollama_model


# ---------------------------------------------------------------------------
# Groq init: success vs misconfiguration
# ---------------------------------------------------------------------------

def test_groq_with_key_builds_client(clean_env):
    from backend.llm.synthesizer import LLMSynthesizer

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "gsk-test-key")
    llm = LLMSynthesizer()
    assert llm.provider == "groq"
    assert llm.healthy() is True
    assert llm._groq_client is not None


def test_groq_missing_key_records_init_error_and_is_unhealthy(clean_env):
    from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "")
    llm = LLMSynthesizer()
    assert llm.provider == "groq"  # requested provider is preserved
    assert llm.healthy() is False
    assert isinstance(llm._init_error, LLMConfigError)
    assert "GROQ_API_KEY" in str(llm._init_error)


def test_groq_client_construction_failure_records_init_error(clean_env):
    from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "gsk-test-key")

    with patch(
        "backend.llm.synthesizer._build_groq_client",
        side_effect=RuntimeError("boom"),
    ):
        llm = LLMSynthesizer()

    assert isinstance(llm._init_error, LLMConfigError)
    assert "boom" in str(llm._init_error)


# ---------------------------------------------------------------------------
# Fail-loud on first synthesize() call
# ---------------------------------------------------------------------------

def test_groq_synthesize_raises_loudly_when_init_failed(clean_env):
    from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "")
    llm = LLMSynthesizer()

    with pytest.raises(LLMConfigError):
        llm.synthesize(context={"q": "x"}, rag_chunks=[])


def test_groq_runtime_error_is_raised_not_swallowed(clean_env):
    from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError(
        "network flake"
    )

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "gsk-test-key")

    with patch(
        "backend.llm.synthesizer._build_groq_client", return_value=fake_client
    ):
        llm = LLMSynthesizer()

    with pytest.raises(LLMConfigError, match="Groq API call failed"):
        llm.synthesize(context={"q": "x"}, rag_chunks=[])


# ---------------------------------------------------------------------------
# Happy path: Groq response_format honoured, JSON parsed into the schema
# ---------------------------------------------------------------------------

def test_groq_synthesize_uses_json_mode_and_parses(clean_env):
    from backend.llm.synthesizer import LLMSynthesizer

    fake_choice = MagicMock()
    fake_choice.message.content = json.dumps(
        {
            "what_is_happening": "Surge in dengue cases.",
            "why_it_happening": "Monsoon season.",
            "recommended_action": "Increase vector control.",
        }
    )
    fake_response = MagicMock(choices=[fake_choice])
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "gsk-test-key")

    with patch(
        "backend.llm.synthesizer._build_groq_client", return_value=fake_client
    ):
        llm = LLMSynthesizer()
        result = llm.synthesize(context={"q": "x"}, rag_chunks=[])

    call_kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["temperature"] == 0.2
    messages = call_kwargs["messages"]
    assert any(m["role"] == "system" for m in messages)
    assert any(m["role"] == "user" for m in messages)

    assert result["what_is_happening"] == "Surge in dengue cases."
    assert result["why_it_happening"] == "Monsoon season."
    assert result["recommended_action"] == "Increase vector control."


def test_groq_non_json_response_raises_loudly(clean_env):
    """If the model ever returns non-JSON, fail loudly — do not silently
    dump the prose into ``what_is_happening``."""
    from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

    fake_choice = MagicMock()
    fake_choice.message.content = "Sure, here is some prose without JSON."
    fake_response = MagicMock(choices=[fake_choice])
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    clean_env.setenv("LLM_PROVIDER", "groq")
    clean_env.setenv("GROQ_API_KEY", "gsk-test-key")

    with patch(
        "backend.llm.synthesizer._build_groq_client", return_value=fake_client
    ):
        llm = LLMSynthesizer()

        with pytest.raises(LLMConfigError, match="non-JSON"):
            llm.synthesize(context={"q": "x"}, rag_chunks=[])
