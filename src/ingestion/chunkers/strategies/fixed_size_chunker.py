"""固定大小分块策略 — 按字符数滑窗切割，支持 overlap"""

from __future__ import annotations

import logging

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.utils import merge_small_chunks
from src.ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


class FixedSizeChunker(BaseChunker):
    """固定大小分块：纯按字符数切割，可选 overlap"""

    def chunk(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        doc_id: str,
        max_chunk_size: int = 1024,
        **kwargs,
    ) -> list[tuple[list[ParsedElement], str]]:
        overlap = kwargs.get("overlap", 0)
        min_chunk_size = kwargs.get("min_chunk_size", 50)

        if not elements:
            return []

        if max_chunk_size <= 0:
            return [(elements, "")]

        result: list[tuple[list[ParsedElement], str]] = []
        group_counter = 0
        current: list[ParsedElement] = []
        current_size = 0

        for elem in elements:
            elem_size = len(elem.content)

            # 单个元素超限 → 单独成组
            if elem_size > max_chunk_size and current:
                gid = f"{doc_id}_g{group_counter}" if doc_id else f"g{group_counter}"
                result.append((current, gid))
                group_counter += 1
                current = [elem]
                current_size = elem_size
                continue

            if current_size + elem_size > max_chunk_size and current:
                gid = f"{doc_id}_g{group_counter}" if doc_id else f"g{group_counter}"
                result.append((current, gid))
                group_counter += 1

                # overlap：回溯部分元素作为下一组开头
                if overlap > 0:
                    overlap_elems = _get_overlap_elements(current, overlap)
                    current = overlap_elems + [elem]
                    current_size = sum(len(e.content) for e in current)
                else:
                    current = [elem]
                    current_size = elem_size
                continue

            current.append(elem)
            current_size += elem_size

        if current:
            if result and sum(len(e.content) for e in current) < min_chunk_size:
                prev_elems, prev_gid = result.pop()
                result.append((prev_elems + current, prev_gid))
            else:
                gid = f"{doc_id}_g{group_counter}" if doc_id else f"g{group_counter}"
                result.append((current, gid))

        logger.info("固定大小分块: %d 个元素 → %d 个分块 (overlap=%d)", len(elements), len(result), overlap)

        if min_chunk_size > 0:
            result = merge_small_chunks(result, min_chunk_size)

        return result


def _get_overlap_elements(group: list[ParsedElement], overlap_chars: int) -> list[ParsedElement]:
    """从组末尾回溯 overlap_chars 个字符的元素"""
    if overlap_chars <= 0:
        return []

    overlap_elems: list[ParsedElement] = []
    chars = 0
    for elem in reversed(group):
        chars += len(elem.content)
        overlap_elems.insert(0, elem)
        if chars >= overlap_chars:
            break
    return overlap_elems
