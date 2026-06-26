"""Ingest all policy PDFs into ChromaDB."""
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.rag.ingest import ingest_pdfs

PDF_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "policy_docs"


def main() -> None:
    if not PDF_DIR.exists():
        print(f"Error: PDF directory not found at {PDF_DIR}")
        sys.exit(1)

    pdfs = list(PDF_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {PDF_DIR}")
        sys.exit(1)

    print(f"Found {len(pdfs)} PDFs in {PDF_DIR}")
    total = ingest_pdfs(PDF_DIR)
    print(f"Done — ingested {total} chunks into ChromaDB.")


if __name__ == "__main__":
    main()
