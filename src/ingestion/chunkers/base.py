"""分块策略基类"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.ingestion.parsers.base import ParsedElement


class BaseChunker(ABC):
    """分块器基类，定义分块接口"""

    @abstractmethod
    def chunk(
        self,
        elements: list[ParsedElement],
        page_sizes: dict[int, tuple[float, float]],
        doc_id: str,
        max_chunk_size: int = 1024,
        **kwargs,
    ) -> list[tuple[list[ParsedElement], str]]:
        """将元素列表分块。

        Args:
            elements: 解析后的扁平元素列表
            page_sizes: 每页尺寸 {page: (width, height)}
            doc_id: 文档 ID
            max_chunk_size: 最大分块字符数
            **kwargs: 策略专属参数

        Returns:
            [(elements, group_id), ...] — 未拆分的段落 group_id 为空串
        """
