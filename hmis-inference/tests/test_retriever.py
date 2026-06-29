"""
RAG retrieval tests — guarded by ``pytest.importorskip`` so they're
invisible-but-skipped on CI runners without an offline
SentenceTransformer model + ChromaDB available.

The retriever itself stays production-grade: when both are installed
and a model is cached, the tests run end-to-end. Otherwise they're
skipped with a clear reason instead of failing with the cryptic
"Connection error on HuggingFace" message many environments hit.
"""
import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")


def _have_local_model() -> bool:
    """True when a local SentenceTransformer model is already cached.

    We deliberately avoid *triggering* a download — the tests are
    skipped on envs where the model has never been pulled, preventing
    flaky CI runs that hang on HuggingFace network access.
    """
    try:
        from sentence_transformers import SentenceTransformer
        # HuggingFace cache root lives under ~/.cache/huggingface. We
        # check for any subdir matching the all-MiniLM-L6-v2 model.
        import os
        from pathlib import Path
        cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface")))
        return any(cache.glob("**/sentence-transformers__all-MiniLM-L6-v2*"))
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _have_local_model(),
    reason="SentenceTransformer model not cached locally — run scripts/ingest_policies.py to seed RAG and warm the model cache",
)


from backend.rag.retriever import PolicyRAG  # noqa: E402  (must come after pytestmark)


def get_rag() -> PolicyRAG:
    return PolicyRAG()


def test_retrieve_dengue_returns_chunks() -> None:
    rag = get_rag()
    results = rag.retrieve("dengue outbreak response")
    assert len(results) >= 1


def test_retrieve_irrelevant_returns_few() -> None:
    rag = get_rag()
    results = rag.retrieve("Python programming tutorial")
    assert len(results) <= 1


def test_embed_query_length() -> None:
    rag = get_rag()
    vec = rag.embed_query("test query")
    assert len(vec) == 384
