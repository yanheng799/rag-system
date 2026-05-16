"""QA 分块策略 — 逐行拆分 CSV/Excel 表格数据"""

from __future__ import annotations

import logging

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.parsers.base import ParsedElement, format_rows

logger = logging.getLogger(__name__)


class QaChunker(BaseChunker):
    """QA 分块：将 table 元素逐行拆分为独立 chunk，适用于 FAQ/知识条目场景。"""

    def chunk(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        doc_id: str,
        max_chunk_size: int = 1024,
        **kwargs,
    ) -> list[tuple[list[ParsedElement], str]]:
        result: list[tuple[list[ParsedElement], str]] = []

        for elem in elements:
            if elem.is_table and isinstance(elem.raw, dict) and "rows" in elem.raw:
                headers = elem.raw["headers"]
                rows = elem.raw["rows"]
                sheet_name = elem.style.get("sheet_name", "")

                for row in rows:
                    content = format_rows(headers, [row], sheet_name)
                    row_elem = ParsedElement(
                        elem_type="table",
                        content=content,
                        page=elem.page,
                        bbox=(0, 0, 0, 0),
                        style=elem.style.copy(),
                        raw={"headers": headers, "rows": [row]},
                    )
                    result.append(([row_elem], ""))
            else:
                # 非 table 元素保留为独立 chunk
                result.append(([elem], ""))

        logger.info("QA 分块完成: %d 个元素 → %d 个 chunk", len(elements), len(result))
        return result
