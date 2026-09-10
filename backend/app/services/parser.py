import fitz  # pymupdf
from pathlib import Path
from typing import Generator


CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


def extract_chunks(file_path: str) -> Generator[dict, None, None]:
    doc = fitz.open(file_path)
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if not text:
            continue
        chunks = _split_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        for idx, chunk in enumerate(chunks):
            yield {
                "page_number": page_num,
                "chunk_index": idx,
                "content": chunk,
            }
    doc.close()


def get_page_count(file_path: str) -> int:
    doc = fitz.open(file_path)
    count = doc.page_count
    doc.close()
    return count


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += size - overlap
    return chunks
