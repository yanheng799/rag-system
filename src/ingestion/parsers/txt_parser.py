"""TXT 纯文本解析器"""

from __future__ import annotations

import logging

from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError, read_text_file

logger = logging.getLogger(__name__)

# 单个元素最大字符数，超过则按行二次拆分
MAX_ELEMENT_SIZE = 8192


class TxTParser(BaseParser):
    """纯文本文件解析器，按空行分段落，超长段落按行二次拆分"""

    def parse(self, file_path: str) -> list[ParsedElement]:
        try:
            text = read_text_file(file_path)
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(file_path, str(e)) from e

        if not text.strip():
            return []

        elements: list[ParsedElement] = []
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(para) <= MAX_ELEMENT_SIZE:
                elements.append(
                    ParsedElement(
                        elem_type="text",
                        content=para,
                        page=1,
                        bbox=(0, 0, 0, 0),
                        style={"paragraph_break": True},
                    )
                )
            else:
                elements.extend(self._split_long_paragraph(para))

        logger.info("TXT 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def _split_long_paragraph(self, para: str) -> list[ParsedElement]:
        """超长段落按行拆分为多个元素，每段不超过 MAX_ELEMENT_SIZE。"""
        elements: list[ParsedElement] = []
        lines = para.split("\n")
        buffer: list[str] = []

        for line in lines:
            # 单行超长时，先 flush buffer，再按字符硬切
            if len(line) > MAX_ELEMENT_SIZE:
                if buffer:
                    elements.append(self._make_elem("\n".join(buffer)))
                    buffer = []
                for i in range(0, len(line), MAX_ELEMENT_SIZE):
                    elements.append(self._make_elem(line[i : i + MAX_ELEMENT_SIZE]))
                continue

            if buffer and len("\n".join(buffer)) + len(line) + 1 > MAX_ELEMENT_SIZE:
                elements.append(self._make_elem("\n".join(buffer)))
                buffer = []
            buffer.append(line)

        if buffer:
            elements.append(self._make_elem("\n".join(buffer)))

        return elements

    @staticmethod
    def _make_elem(content: str) -> ParsedElement:
        return ParsedElement(
            elem_type="text",
            content=content,
            page=1,
            bbox=(0, 0, 0, 0),
            style={"paragraph_break": True},
        )

    def supported_types(self) -> list[str]:
        return ["txt"]
