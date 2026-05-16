"""Markdown (.md) 文档解析器"""

from __future__ import annotations

import logging
import re

from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError, read_text_file

logger = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+")
_FENCED_CODE_RE = re.compile(r"^(`{3,}|~{3,})")
_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_TABLE_SEP_RE = re.compile(r"^\|[-:\s]+(\|[-:\s]+)*\|$")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"\*(.+?)\*|_(.+?)_(?![^<]*>)")
_STRIKETHROUGH_RE = re.compile(r"~~(.+?)~~")


def _strip_inline_formatting(text: str) -> str:
    """剥离行内格式标记，保留反引号。"""
    text = _IMAGE_RE.sub(lambda m: m.group(1) or "[图片]", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _ITALIC_RE.sub(lambda m: m.group(1) or m.group(2), text)
    text = _STRIKETHROUGH_RE.sub(r"\1", text)
    return text


class MarkdownParser(BaseParser):
    """Markdown 文档解析器，顶层状态机逐行解析"""

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
        lines = text.split("\n")

        in_code_block = False
        code_buffer: list[str] = []
        in_table = False
        table_buffer: list[str] = []
        text_buffer: list[str] = []

        for line in lines:
            # --- 围栏代码块（优先级最高）---
            fence_match = _FENCED_CODE_RE.match(line)
            if fence_match:
                if in_code_block:
                    self._emit_code_block(code_buffer, elements)
                    code_buffer = []
                    in_code_block = False
                else:
                    self._flush_text(text_buffer, elements)
                    text_buffer = []
                    self._flush_table(table_buffer, elements)
                    table_buffer = []
                    in_table = False
                    in_code_block = True
                continue

            if in_code_block:
                code_buffer.append(line)
                continue

            # --- 标题 ---
            heading_match = _HEADING_RE.match(line)
            if heading_match:
                self._flush_text(text_buffer, elements)
                text_buffer = []
                self._flush_table(table_buffer, elements)
                table_buffer = []
                in_table = False
                level = len(heading_match.group(1))
                title_text = _strip_inline_formatting(heading_match.group(2).strip())
                elements.append(
                    ParsedElement(
                        elem_type="title",
                        content=title_text,
                        page=1,
                        bbox=(0, 0, 0, 0),
                        style={"heading_level": level},
                    )
                )
                continue

            # --- 表格 ---
            if _TABLE_ROW_RE.match(line):
                if _TABLE_SEP_RE.match(line):
                    # 分隔行：在表格内则跳过，不在表格内则忽略
                    continue
                self._flush_text(text_buffer, elements)
                text_buffer = []
                in_table = True
                table_buffer.append(line)
                continue

            # --- 列表 ---
            if _LIST_RE.match(line):
                self._flush_text(text_buffer, elements)
                text_buffer = []
                self._flush_table(table_buffer, elements)
                table_buffer = []
                in_table = False
                item_text = _strip_inline_formatting(_LIST_RE.sub("", line).strip())
                elements.append(
                    ParsedElement(
                        elem_type="list_item",
                        content=item_text,
                        page=1,
                        bbox=(0, 0, 0, 0),
                    )
                )
                continue

            # --- 普通文本 / 空行 ---
            self._flush_table(table_buffer, elements)
            table_buffer = []
            in_table = False

            stripped = line.strip()
            if stripped:
                text_buffer.append(_strip_inline_formatting(stripped))
            else:
                self._flush_text(text_buffer, elements)
                text_buffer = []

        # flush 残余
        if in_code_block and code_buffer:
            self._emit_code_block(code_buffer, elements)
        self._flush_table(table_buffer, elements)
        self._flush_text(text_buffer, elements)

        logger.info("Markdown 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    @staticmethod
    def _emit_code_block(lines: list[str], elements: list[ParsedElement]) -> None:
        if not lines:
            return
        elements.append(
            ParsedElement(
                elem_type="text",
                content="\n".join(lines),
                page=1,
                bbox=(0, 0, 0, 0),
                style={"code_block": True},
            )
        )

    @staticmethod
    def _flush_table(buffer: list[str], elements: list[ParsedElement]) -> None:
        if not buffer:
            return
        elements.append(
            ParsedElement(
                elem_type="table",
                content="\n".join(buffer),
                page=1,
                bbox=(0, 0, 0, 0),
            )
        )
        buffer.clear()

    @staticmethod
    def _flush_text(buffer: list[str], elements: list[ParsedElement]) -> None:
        if not buffer:
            return
        elements.append(
            ParsedElement(
                elem_type="text",
                content="\n".join(buffer),
                page=1,
                bbox=(0, 0, 0, 0),
            )
        )
        buffer.clear()

    def supported_types(self) -> list[str]:
        return ["md"]
