from __future__ import annotations

import logging
from pathlib import Path

import chromadb

from backend.rag.embedder import LocalEmbedder

logger = logging.getLogger(__name__)

CHROMA_DIR = str(Path(__file__).resolve().parent.parent.parent / "chroma_db")
COLLECTION_NAME = "hmis_policy_docs"
# Distance threshold for cosine similarity on MiniLM-L6-v2 normalized
# embeddings. ~0.85 keeps chunks that are semantically on-topic; chunks above
# this are tangential (headers, TOCs, fragments) and used to leak garbage.
# Pushed down from 1.2 because retrieval was returning junk for policy questions.
DISTANCE_THRESHOLD = 0.85
# Above this mean distance we treat retrieval as "no relevant policy data"
# and the QA router returns a clean refusal instead of asking the LLM.
NO_ANSWER_AVG_DISTANCE = 0.95


class RetrievedChunk:
    """One retrieved chunk plus the metadata a caller needs to weight it."""

    __slots__ = ("text", "source", "distance")

    def __init__(self, text: str, source: str, distance: float) -> None:
        self.text = text
        self.source = source
        self.distance = distance

    @property
    def prefix(self) -> str:
        return f"[{self.source}]: {self.text}"


class PolicyRAG:
    def __init__(self) -> None:
        self._embedder = LocalEmbedder()
        self._client = chromadb.PersistentClient(path=CHROMA_DIR)
        self._collection = self._client.get_or_create_collection(name=COLLECTION_NAME)
        if self._collection.count() == 0:
            logger.warning("ChromaDB collection '%s' is empty — no documents to retrieve.", COLLECTION_NAME)

    def embed_query(self, query: str) -> list[float]:
        return self._embedder.embed([query])[0]

    def retrieve(self, query: str, n_results: int = 5) -> list[RetrievedChunk]:
        """Retrieve up to ``n_results`` relevant chunks within DISTANCE_THRESHOLD.

        Returned objects expose distance so callers can score retrieval quality
        (mean distance > NO_ANSWER_AVG_DISTANCE means policy docs don't cover
        the question — skip LLM, return clean refusal).
        """
        if self._collection.count() == 0:
            logger.warning("ChromaDB collection '%s' is empty — returning no results.", COLLECTION_NAME)
            return []

        query_embedding = self.embed_query(query)
        results = self._collection.query(query_embeddings=[query_embedding], n_results=n_results)

        chunks: list[RetrievedChunk] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            if dist > DISTANCE_THRESHOLD:
                continue
            chunks.append(
                RetrievedChunk(
                    text=doc,
                    source=meta.get("source", "unknown"),
                    distance=float(dist),
                )
            )
        return chunks

    def mean_distance(self, chunks: list[RetrievedChunk]) -> float | None:
        """Average distance across accepted chunks, or None if no chunks."""
        if not chunks:
            return None
        return sum(c.distance for c in chunks) / len(chunks)

