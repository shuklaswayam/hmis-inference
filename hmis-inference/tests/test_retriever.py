from backend.rag.retriever import PolicyRAG


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
