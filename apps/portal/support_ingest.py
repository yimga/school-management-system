"""
Sliding-window text chunking for KB / docs ingestion (batch 1334).
"""

from __future__ import annotations


def chunk_text_sliding_window(
    text: str,
    *,
    chunk_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[str]:
    """
    Approximate token windows (~4 chars per token) with overlap for continuity.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    chunk_chars = max(200, chunk_tokens * 4)
    overlap_chars = max(0, min(overlap_tokens * 4, chunk_chars // 2))
    if len(raw) <= chunk_chars:
        return [raw]
    chunks: list[str] = []
    start = 0
    while start < len(raw):
        end = min(len(raw), start + chunk_chars)
        piece = raw[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(raw):
            break
        start = end - overlap_chars
    return chunks
