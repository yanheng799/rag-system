"""分块策略注册表"""

from __future__ import annotations

import logging
from typing import ClassVar

from src.ingestion.chunkers.base import BaseChunker
from src.ingestion.chunkers.strategies.fixed_size_chunker import FixedSizeChunker
from src.ingestion.chunkers.strategies.heading_chunker import HeadingChunker
from src.ingestion.chunkers.strategies.page_chunker import PageChunker
from src.ingestion.chunkers.strategies.paragraph_chunker import ParagraphChunker
from src.ingestion.chunkers.strategies.qa_chunker import QaChunker

logger = logging.getLogger(__name__)

_VALID_STRATEGIES = {"paragraph", "heading", "fixed_size", "page", "qa"}


class ChunkerRegistry:
    """分块策略注册表：策略名 → 分块器实例"""

    _chunkers: ClassVar[dict[str, BaseChunker]] = {}

    @classmethod
    def register(cls, name: str, chunker: BaseChunker) -> None:
        cls._chunkers[name] = chunker
        logger.info("注册分块策略: %s -> %s", name, chunker.__class__.__name__)

    @classmethod
    def get(cls, strategy: str) -> BaseChunker:
        if strategy not in cls._chunkers:
            raise ValueError(f"未知的分块策略: {strategy}，可选: {list(cls._chunkers.keys())}")
        return cls._chunkers[strategy]

    @classmethod
    def available_strategies(cls) -> list[str]:
        return list(cls._chunkers.keys())

    @classmethod
    def reset(cls) -> None:
        """清空已注册的分块策略（主要用于测试隔离）"""
        cls._chunkers.clear()


def init_chunkers() -> None:
    """初始化并注册所有分块策略"""
    ChunkerRegistry.register("paragraph", ParagraphChunker())
    ChunkerRegistry.register("heading", HeadingChunker())
    ChunkerRegistry.register("fixed_size", FixedSizeChunker())
    ChunkerRegistry.register("page", PageChunker())
    ChunkerRegistry.register("qa", QaChunker())
