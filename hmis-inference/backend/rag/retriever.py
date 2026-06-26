from __future__ import annotations

import logging
from pathlib import Path

import chromadb

from backend.rag.embedder import LocalEmbedder

logger = logging.getLogger(__name__)

CHROMA_DIR = str(Path(__file__).resolve().parent.parent.parent / "chroma_db")
COLLECTION_NAME = "hmis_policy_docs"
DISTANCE_THRESHOLD = 1.2


class PolicyRAG:
    def __init__(self) -> None:
        self._embedder = LocalEmbedder()
        self._client = chromadb.PersistentClient(path=CHROMA_DIR)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
        if self._collection.count() == 0:
            logger.warning("ChromaDB collection '%s' is empty — no documents to retrieve.", COLLECTION_NAME)

    def embed_query(self, query: str) -> list[float]:
        return self._embedder.embed([query])[0]

    def retrieve(self, query: str, n_results: int = 5) -> list[str]:
        if self._collection.count() == 0:
            logger.warning("ChromaDB collection '%s' is empty — returning no results.", COLLECTION_NAME)
            return []

        query_embedding = self.embed_query(query)
        results = self._collection.query(query_embeddings=[query_embedding], n_results=n_results)

        docs: list[str] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            if dist > DISTANCE_THRESHOLD:
                continue
            source = meta.get("source", "unknown")
            docs.append(f"[{source}]: {doc}")

        return docs
