from __future__ import annotations

import os
from pathlib import Path

import chromadb
import fitz  # PyMuPDF

from backend.rag.embedder import LocalEmbedder

CHROMA_DIR = str(Path(__file__).resolve().parent.parent.parent / "chroma_db")
COLLECTION_NAME = "hmis_policy_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def read_pdf(path: str | Path) -> str:
    doc = fitz.open(path)
    return "".join(page.get_text() for page in doc)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def ingest_pdfs(pdf_dir: str | Path) -> int:
    pdf_dir = Path(pdf_dir)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)
    embedder = LocalEmbedder()

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    total_chunks = 0

    for pdf_path in pdf_files:
        text = read_pdf(pdf_path)
        chunks = chunk_text(text)
        if not chunks:
            continue

        embeddings = embedder.embed(chunks)

        ids = [f"{pdf_path.name}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": pdf_path.name, "chunk_index": i} for i in range(len(chunks))]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        total_chunks += len(chunks)
        print(f"  Ingested {pdf_path.name}: {len(chunks)} chunks")

    return total_chunks
