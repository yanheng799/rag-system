"""PDF 文档解析器（基于 pymupdf）"""

from __future__ import annotations

import logging
from typing import Optional

import fitz  # pymupdf

from ingestion.parsers.base import BaseParser, ParsedElement, ParseError

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """使用 pymupdf 解析 PDF 文档，提取文字块和表格"""

    def parse(self, file_path: str) -> list[ParsedElement]:
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise ParseError(file_path, str(e))

        elements: list[ParsedElement] = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            elements.extend(self._parse_page(page, page_num))

        doc.close()
        logger.info("PDF 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def _parse_page(self, page: fitz.Page, page_num: int) -> list[ParsedElement]:
        """解析单页，提取文字和表格"""
        elements: list[ParsedElement] = []
        page_width = page.rect.width

        # 先提取表格区域，用于过滤文字块中的表格部分
        tables = page.find_tables()
        table_bboxes = []
        table_cells_map = {}

        for table_idx, table in enumerate(tables):
            bbox = table.bbox
            table_bboxes.append(bbox)

            # 提取表格内容
            table_text = self._extract_table_text(table)
            table_cells_map[table_idx] = table.cells if hasattr(table, 'cells') else []

            elements.append(
                ParsedElement(
                    elem_type="table",
                    content=table_text,
                    page=page_num,
                    bbox=tuple(bbox),
                    style={"table_index": table_idx},
                    raw=table,
                )
            )

        # 提取文字块（排除已识别为表格的区域）
        text_elements = self._extract_text_blocks(page, page_num, table_bboxes)
        elements.extend(text_elements)

        # 按 y 坐标排序（从上到下），x 坐标为次要排序
        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

        return elements

    def _extract_text_blocks(
        self, page: fitz.Page, page_num: int, table_bboxes: list
    ) -> list[ParsedElement]:
        """提取文字块，跳过表格区域"""
        elements: list[ParsedElement] = []
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block["type"] != 0:  # 只处理文字块
                continue

            block_bbox = block["bbox"]

            # 跳过与表格重叠的文字块
            if self._is_in_table(block_bbox, table_bboxes):
                continue

            for line in block["lines"]:
                line_text = ""
                max_font_size = 0
                is_bold = False

                for span in line["spans"]:
                    line_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if "bold" in span["font"].lower():
                        is_bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                # 判断元素类型
                elem_type = self._detect_text_type(line_text, max_font_size, is_bold)

                elements.append(
                    ParsedElement(
                        elem_type=elem_type,
                        content=line_text,
                        page=page_num,
                        bbox=tuple(line["bbox"]),
                        style={
                            "font_size": max_font_size,
                            "bold": is_bold,
                        },
                    )
                )

        return elements

    def _extract_table_text(self, table) -> str:
        """将 pymupdf 表格对象提取为文字描述"""
        rows = table.extract()
        if not rows:
            return ""

        lines = []
        for row in rows:
            cells = [str(cell) if cell else "" for cell in row]
            lines.append(" | ".join(cells))

        return "\n".join(lines)

    def _is_in_table(self, bbox, table_bboxes: list) -> bool:
        """判断文字块是否在表格区域内"""
        x0, y0, x1, y1 = bbox
        for tx0, ty0, tx1, ty1 in table_bboxes:
            # 重叠检测
            if x0 < tx1 and x1 > tx0 and y0 < ty1 and y1 > ty0:
                overlap_x = min(x1, tx1) - max(x0, tx0)
                overlap_y = min(y1, ty1) - max(y0, ty0)
                block_area = (x1 - x0) * (y1 - y0)
                if block_area > 0:
                    overlap_ratio = (overlap_x * overlap_y) / block_area
                    if overlap_ratio > 0.5:
                        return True
        return False

    def _detect_text_type(
        self, text: str, font_size: float, is_bold: bool
    ) -> str:
        """根据样式判断文字类型"""
        # 标题判断：字号大于正文 或 加粗
        if font_size >= 14 or (is_bold and font_size >= 12):
            return "title"
        # 列表项判断
        if text.startswith(("•", "●", "◆", "○", "■")) or (
            len(text) > 2 and text[0].isdigit() and text[1] in ".)"
        ):
            return "list_item"
        return "text"

    def supported_types(self) -> list[str]:
        return ["pdf"]
