"""File parsing utilities for ingesting documents into episodes."""

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str | Path) -> str:
    """Extract text content from a PDF file."""
    doc = fitz.open(str(file_path))
    pages = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text.strip())
    doc.close()
    return "\n\n".join(pages)


def parse_text(file_path: str | Path, encoding: str | None = None) -> str:
    """Read a plain text file with auto-detected encoding."""
    path = Path(file_path)
    raw = path.read_bytes()

    if encoding is None:
        import charset_normalizer

        result = charset_normalizer.from_bytes(raw).best()
        if result is None:
            raise ValueError(f"Cannot detect encoding for {file_path}")
        return str(result)

    return raw.decode(encoding)


def parse_file(file_path: str | Path) -> str:
    """Parse a file based on its extension. Returns extracted text."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return parse_pdf(path)
    elif suffix in (".txt", ".md", ".csv", ".log", ".json", ".xml", ".html"):
        return parse_text(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks for processing."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars

        # Try to break at a sentence boundary
        if end < len(text):
            for sep in ["\n\n", "\n", "。", ".", "！", "!", "？", "?"]:
                last_sep = text.rfind(sep, start + max_chars // 2, end)
                if last_sep != -1:
                    end = last_sep + len(sep)
                    break

        chunks.append(text[start:end].strip())
        start = end - overlap

    return [c for c in chunks if c]
