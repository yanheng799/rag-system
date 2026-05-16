"""TXT 纯文本解析器"""

from __future__ import annotations

import logging

from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError, read_text_file

logger = logging.getLogger(__name__)


class TxTParser(BaseParser):
    """纯文本文件解析器，按空行分段落"""

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

            elements.append(
                ParsedElement(
                    elem_type="text",
                    content=para,
                    page=1,
                    bbox=(0, 0, 0, 0),
                    style={"paragraph_break": True},
                )
            )

        logger.info("TXT 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def supported_types(self) -> list[str]:
        return ["txt"]
