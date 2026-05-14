"""段落分块策略 — 包装现有 group_elements_by_paragraph()"""

from __future__ import annotations

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.paragraph_grouper import group_elements_by_paragraph
from src.ingestion.chunkers.utils import merge_small_chunks
from src.ingestion.parsers.base import ParsedElement


class ParagraphChunker(BaseChunker):
    """段落分块：自适应行距 + 首行缩进 + 段末短行"""

    def chunk(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        doc_id: str,
        max_chunk_size: int = 1024,
        **kwargs,
    ) -> list[tuple[list[ParsedElement], str]]:
        vertical_gap = kwargs.get("vertical_gap", 15.0)
        min_chunk_size = kwargs.get("min_chunk_size", 50)

        groups = group_elements_by_paragraph(
            elements,
            vertical_gap_threshold=vertical_gap,
            max_chunk_size=max_chunk_size,
            page_sizes=page_sizes,
            doc_id=doc_id,
        )

        if min_chunk_size > 0:
            groups = merge_small_chunks(groups, min_chunk_size)

        return groups
