"""逐页分块策略 — 按页码聚合，超限再按大小拆分"""

from __future__ import annotations

import logging

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.utils import merge_small_chunks, split_oversized_groups
from src.ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


class PageChunker(BaseChunker):
    """逐页分块：每页元素聚合为一组，超限再按大小拆分"""

    def chunk(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        doc_id: str,
        max_chunk_size: int = 1024,
        **kwargs,
    ) -> list[tuple[list[ParsedElement], str]]:
        min_chunk_size = kwargs.get("min_chunk_size", 50)

        if not elements:
            return []

        # 按页码分组
        page_groups: dict[int, list[ParsedElement]] = {}
        for elem in elements:
            page_groups.setdefault(elem.page, []).append(elem)

        paragraphs = list(page_groups[page] for page in sorted(page_groups.keys()))

        logger.info("逐页分块: %d 个元素 → %d 页", len(elements), len(paragraphs))

        # 超长页拆分
        if max_chunk_size > 0:
            result = split_oversized_groups(paragraphs, max_chunk_size, doc_id)
        else:
            result = [(p, "") for p in paragraphs]

        if min_chunk_size > 0:
            result = merge_small_chunks(result, min_chunk_size)

        return result
