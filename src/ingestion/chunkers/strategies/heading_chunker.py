"""标题分块策略 — 按标题（章节）边界拆分，保持章节完整"""

from __future__ import annotations

import logging

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.heading_patterns import is_heading_by_pattern, is_section_heading
from src.ingestion.chunkers.utils import merge_small_chunks, split_oversized_groups
from src.ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


class HeadingChunker(BaseChunker):
    """标题分块：仅按标题边界拆分，保持章节完整"""

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

        # 阶段 1：按标题边界分组
        paragraphs: list[list[ParsedElement]] = []
        current_group: list[ParsedElement] = []

        for elem in elements:
            if _is_heading_boundary(elem) and current_group:
                paragraphs.append(current_group)
                current_group = [elem]
            else:
                current_group.append(elem)

        if current_group:
            paragraphs.append(current_group)

        logger.info("标题分块: %d 个元素 → %d 个段落组", len(elements), len(paragraphs))

        # 阶段 2：超长分组拆分
        if max_chunk_size > 0:
            result = split_oversized_groups(paragraphs, max_chunk_size, doc_id)
        else:
            result = [(p, "") for p in paragraphs]

        if min_chunk_size > 0:
            result = merge_small_chunks(result, min_chunk_size)

        return result


def _is_heading_boundary(elem: ParsedElement) -> bool:
    """判断元素是否为标题边界"""
    if elem.is_title:
        return True
    if is_section_heading(elem.content):
        return True
    return is_heading_by_pattern(elem.content)
