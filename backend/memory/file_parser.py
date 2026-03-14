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


def chunk_text(
    text: str,
    max_chars: int = 500,   # 优化为500，提高提取粒度（参考MiroFish）
    overlap: int = 50,      # 减少到50，适配更小的块大小
    min_chunk_size: int = 100  # 最小块大小，避免碎片
) -> list[str]:
    """Split text into overlapping chunks with semantic-aware boundaries.

    优先级策略:
    1. 段落边界 (\n\n)
    2. 句子边界 (。！？.!?)
    3. 标点符号 (，、,;)
    4. 硬切分
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        # 目标结束位置
        end = min(start + max_chars, len(text))

        # 如果不是最后一块，尝试找语义边界
        if end < len(text):
            # 优先级1: 段落边界 (在后半段查找，避免块太小)
            search_start = start + max_chars // 2
            para_break = text.rfind("\n\n", search_start, end)
            if para_break != -1:
                end = para_break + 2

            # 优先级2: 句子边界
            elif True:
                for sep in ["。\n", "！\n", "？\n", ".\n", "!\n", "?\n",
                           "。", "！", "？", ".", "!", "?"]:
                    last_sep = text.rfind(sep, search_start, end)
                    if last_sep != -1:
                        end = last_sep + len(sep)
                        break

            # 优先级3: 其他标点
            if end == min(start + max_chars, len(text)):
                for sep in ["，", "、", ",", ";", ":", "："]:
                    last_sep = text.rfind(sep, search_start, end)
                    if last_sep != -1:
                        end = last_sep + len(sep)
                        break

        chunk = text[start:end].strip()

        # 只添加有意义的块
        if len(chunk) >= min_chunk_size:
            chunks.append(chunk)

        # 计算下一个起点（带重叠）
        if end >= len(text):
            break
        start = max(end - overlap, start + min_chunk_size)

    return chunks
