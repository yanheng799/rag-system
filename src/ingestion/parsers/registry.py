"""解析器插件注册表"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

from src.ingestion.parsers.base import (
    BaseParser,
    UnsupportedFileTypeError,
)
from src.ingestion.parsers.excel_parser import ExcelParser
from src.ingestion.parsers.pdf_parser import PDFParser
from src.ingestion.parsers.word_parser import WordParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """根据文件扩展名自动选择对应 Parser"""

    _parsers: ClassVar[dict[str, BaseParser]] = {}

    @classmethod
    def register(cls, parser: BaseParser) -> None:
        """注册解析器"""
        for file_type in parser.supported_types():
            cls._parsers[file_type] = parser
            logger.info("注册解析器: %s -> %s", file_type, parser.__class__.__name__)

    @classmethod
    def get(cls, file_type: str) -> BaseParser:
        """获取解析器"""
        file_type = file_type.lower().lstrip(".")
        if file_type not in cls._parsers:
            raise UnsupportedFileTypeError(file_type)
        return cls._parsers[file_type]

    @classmethod
    def get_for_file(cls, file_path: str) -> BaseParser:
        """根据文件路径获取解析器"""
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        return cls.get(ext)

    @classmethod
    def supported_types(cls) -> list[str]:
        """返回所有支持的文件类型"""
        return list(cls._parsers.keys())


def init_parsers() -> None:
    """初始化并注册所有 Phase 1 解析器"""
    ParserRegistry.register(PDFParser())
    ParserRegistry.register(WordParser())
    ParserRegistry.register(ExcelParser())
