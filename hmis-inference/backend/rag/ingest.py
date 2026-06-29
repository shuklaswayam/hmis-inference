from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import chromadb
import fitz  # PyMuPDF

from backend.rag.embedder import LocalEmbedder

logger = logging.getLogger(__name__)

CHROMA_DIR = str(Path(__file__).resolve().parent.parent.parent / "chroma_db")
COLLECTION_NAME = "hmis_policy_docs"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# Filter pass tunables. Chunks failing these checks are dropped before
# they're embedded or inserted, which keeps retrieval from returning
# page headers, TOCs, page numbers, and ~50-char fragments that used
# to dominate the top-k for many policy questions.
MIN_CHUNK_CHARS = 250            # filter absolute noise
MIN_ALPHA_RATIO = 0.55            # drop chunks dominated by digits / punctuation
MIN_WORD_LEN = 4                 # drop chunks where the longest word is tiny

# Header / footer / running-title patterns commonly leaked by sliding-window
# chunking of WHO / NVBDCP PDFs. Case-insensitive.
_HEADER_LINE_RE = re.compile(
    r"""(?ix)
    (?:                                 # one of:
      ^\s*Page\s+\d+\b                 # "Page 12"
    | ^\s*\d+\s+of\s+\d+\s*$           # "42 of 210"
    | WHO\s+Guidelines\s+for\s+\S
    | NVBDCP\s+Operational\s+Manual
    | Guidelines?\s+for\s+\w+[\s-]+\d+/\d+/\d+
    | World\s+Health\s+Organization\b.{0,40}\d+\s+of\s+\d+
    )\b
    """
)
_TOC_LINE_RE = re.compile(r"(?i)^\s*\d+(\.\d+){0,3}\s+\S")  # "7.3 Surveillance"
_DOT_LINE_RE = re.compile(r"\.{4,}\s*\d+\s*$")              # "...157"
# Title stripper applied INSIDE otherwise-good chunks so the running-title
# text embedded in the middle of a chunk doesn't bleed into retrievals.
_RUNNING_TITLE_RE = re.compile(
    r"""(?ix)
    WHO\s+Guidelines\s+for\s+\S.{0,80}?World\s+Health\s+Organization\s*\(?\s*WHO\s*\)?
        (?:.*?\d+\s+of\s+\d+)?
    | World\s+Health\s+Organization\s*\(?\s*WHO\s*\)?\s*[-:,]?\s*\d+\s+of\s+\d+
    | \b\d+\s+of\s+\d+\s*$
    """
)


def read_pdf(path: str | Path) -> str:
    """Page-aware PDF reader — strips first/last non-empty lines of each
    page so recurring page headers and footers don't repeat across the
    extracted text. Documents without such running headers are unaffected."""
    doc = fitz.open(path)
    out: list[str] = []
    for page in doc:
        raw = page.get_text()
        lines = raw.splitlines()
        non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
        if not non_empty:
            continue
        first, last = non_empty[0], non_empty[-1]
        if first == last:
            continue
        # Drop the very first non-empty line (running header) and the very
        # last non-empty line (page number / footer), but keep any blank
        # lines and intermediate content intact.
        trimmed = lines[:first] + lines[first + 1 : last] + lines[last + 1 :]
        out.append("\n".join(trimmed))
    return "".join(out)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sliding window chunker. Sentences are intentionally not detected —
    chunking is dumb by design; the post-filter (``filter_chunks``) is what
    drops noise on the way into ChromaDB."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _is_header_or_footer(line: str) -> bool:
    s = line.strip()
    if not s:
        return False  # empty lines aren't headers — handled separately
    if _HEADER_LINE_RE.search(s):
        return True
    if _TOC_LINE_RE.match(s):
        return True
    if _DOT_LINE_RE.search(s):
        return True
    return False


def _is_quality(chunk: str) -> bool:
    """Heuristic: drop chunks that look like running headers, page-number
    fragments, or near-empty pages."""
    text = chunk.strip()
    if len(text) < MIN_CHUNK_CHARS:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    # If every non-empty line is a header/footer line, drop the whole chunk.
    if all(_is_header_or_footer(ln) for ln in lines):
        return False
    # If alpha ratio is too low, drop — these are digit-heavy pages.
    alpha = sum(c.isalpha() for c in text)
    if alpha / max(len(text), 1) < MIN_ALPHA_RATIO:
        return False
    # If the longest word is suspiciously short, drop — that's fragments.
    longest = max((len(w) for w in re.findall(r"\b\w+\b", text)), default=0)
    if longest < MIN_WORD_LEN:
        return False
    return True


def _normalize_for_hash(chunk: str) -> str:
    """Normalize whitespace so cosmetic variants hash to the same key."""
    return re.sub(r"\s+", " ", chunk.strip()).lower()


def _strip_running_titles(text: str) -> str:
    """Drop lines (and orphan fragments) that match running-title patterns.

    Operating line-by-line so we keep real prose paragraphs intact. The
    running-title regex is meant to match e.g.
      'WHO Guidelines for malaria - 16 February 2021 - World Health
       Organization (WHO) 42 of 210'
    which appears on every page of the WHO Guidelines PDF.
    """
    cleaned_lines: list[str] = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if not stripped:
            cleaned_lines.append(ln)
            continue
        if _RUNNING_TITLE_RE.search(stripped):
            continue
        cleaned_lines.append(ln)
    # Collapse runs of blank lines left by the strip.
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def filter_chunks(chunks: list[str]) -> tuple[list[str], dict]:
    """Post-chunking filter pass.

    Returns:
        (kept_chunks, stats_dict). Stats counters are useful for logging
        how much noise the filter dropped.
    """
    stats = {"input": len(chunks), "kept": 0, "dropped_short": 0,
             "dropped_header": 0, "dropped_alpha": 0, "dropped_longword": 0,
             "dropped_dedupe": 0, "stripped_titles": 0}
    seen: set[str] = set()
    kept: list[str] = []
    for c in chunks:
        # Strip embedded running-title noise first so length / quality checks
        # are measured against meaningful content, not against header lines.
        stripped = _strip_running_titles(c)
        if len(stripped) < len(c):
            stats["stripped_titles"] += 1
        text = stripped.strip()
        if len(text) < MIN_CHUNK_CHARS:
            stats["dropped_short"] += 1
            continue
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if lines and all(_is_header_or_footer(ln) for ln in lines):
            stats["dropped_header"] += 1
            continue
        alpha = sum(ch.isalpha() for ch in text)
        if alpha / max(len(text), 1) < MIN_ALPHA_RATIO:
            stats["dropped_alpha"] += 1
            continue
        longest = max((len(w) for w in re.findall(r"\b\w+\b", text)), default=0)
        if longest < MIN_WORD_LEN:
            stats["dropped_longword"] += 1
            continue
        key = hashlib.sha256(_normalize_for_hash(text).encode()).hexdigest()
        if key in seen:
            stats["dropped_dedupe"] += 1
            continue
        seen.add(key)
        kept.append(text)
    stats["kept"] = len(kept)
    return kept, stats


def ingest_pdfs(pdf_dir: str | Path) -> int:
    """Ingest every PDF in ``pdf_dir`` into the ChromaDB collection.

    Re-running this drops the existing collection first so the rebuilt index
    is deterministic. Returns the number of chunks written."""
    pdf_dir = Path(pdf_dir)
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Always start fresh — the previous upsert-keyed scheme left stale chunks
    # behind when PDFs changed or were re-chunked.
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        logger.info("Dropping existing collection '%s' for clean re-ingest", COLLECTION_NAME)
        client.delete_collection(name=COLLECTION_NAME)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    embedder = LocalEmbedder()

    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    total_in = 0
    total_kept = 0

    for pdf_path in pdf_files:
        text = read_pdf(pdf_path)
        raw_chunks = chunk_text(text)
        kept_chunks, stats = filter_chunks(raw_chunks)
        total_in += stats["input"]
        total_kept += stats["kept"]
        logger.info(
            "[%s] chunks: %d raw → %d kept (titles-stripped: %d, dropped short=%d hdr=%d alpha=%d lw=%d dedupe=%d)",
            pdf_path.name,
            stats["input"], stats["kept"],
            stats["stripped_titles"],
            stats["dropped_short"], stats["dropped_header"],
            stats["dropped_alpha"], stats["dropped_longword"],
            stats["dropped_dedupe"],
        )
        if not kept_chunks:
            continue

        embeddings = embedder.embed(kept_chunks)
        ids = [f"{pdf_path.name}_chunk_{i}" for i in range(len(kept_chunks))]
        metadatas = [{"source": pdf_path.name, "chunk_index": i} for i in range(len(kept_chunks))]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=kept_chunks,
            metadatas=metadatas,
        )

    logger.info(
        "Done — ingested %d chunks (kept %d / %d). collection size: %d",
        total_kept,
        total_kept,
        total_in,
        collection.count(),
    )
    return collection.count()
