"""HMIS LLM synthesizer — public-health analysis with Groq or Ollama.

Importing from this package is the supported way to reach the synthesizer::

    from backend.llm import LLMSynthesizer, LLMConfigError
"""
from backend.llm.synthesizer import LLMConfigError, LLMSynthesizer

__all__ = ["LLMConfigError", "LLMSynthesizer"]
