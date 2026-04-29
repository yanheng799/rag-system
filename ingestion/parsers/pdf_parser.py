"""PDF 文档解析器（基于 pymupdf）"""

from __future__ import annotations

import logging
from typing import Optional

import fitz  # pymupdf

from ingestion.chunkers.heading_patterns import is_heading_combined
from ingestion.chunkers.layout_detector import (
    detect_header_footer_zones,
    detect_page_layout,
    detect_toc_pages,
    is_in_header_footer,
    reorder_elements_for_layout,
)
from ingestion.parsers.base import BaseParser, ParsedElement, ParseError

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """使用 pymupdf 解析 PDF 文档，提取文字块和表格"""

    def parse(self, file_path: str) -> list[ParsedElement]:
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            raise ParseError(file_path, str(e))

        hf_zones = detect_header_footer_zones(doc)
        toc_pages = detect_toc_pages(doc)
        elements: list[ParsedElement] = []
        page_sizes: dict[int, tuple[float, float]] = {}

        for page_num in range(len(doc)):
            if page_num in toc_pages:
                continue

            page = doc[page_num]
            page_sizes[page_num] = (page.rect.width, page.rect.height)
            layout = detect_page_layout(page)
            elements.extend(self._parse_page(page, page_num, layout, hf_zones))

        doc.close()

        # 后处理：跨页/跨列表格合并
        from ingestion.chunkers.merge_cross_page import (
            merge_cross_column_tables,
            merge_cross_page_tables,
        )

        elements = merge_cross_page_tables(elements, page_sizes)
        elements = merge_cross_column_tables(elements, page_sizes)

        logger.info("PDF 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def _parse_page(
        self,
        page: fitz.Page,
        page_num: int,
        layout: str = "single",
        hf_zones: list | None = None,
    ) -> list[ParsedElement]:
        """解析单页，提取文字和表格"""
        elements: list[ParsedElement] = []
        page_width = page.rect.width

        # 先提取表格区域，用于过滤文字块中的表格部分
        tables = page.find_tables()
        table_bboxes = []

        for table_idx, table in enumerate(tables):
            bbox = table.bbox
            table_bboxes.append(bbox)

            # 提取表格内容
            table_text = self._extract_table_text(table)

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

        # 提取文字块（排除已识别为表格的区域和页眉页脚）
        text_elements = self._extract_text_blocks(page, page_num, table_bboxes, hf_zones)
        elements.extend(text_elements)

        # 按 y 坐标排序（从上到下），x 坐标为次要排序
        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

        # 根据排版格式重排元素（双栏：左列→右列）
        elements = reorder_elements_for_layout(elements, page_width, layout)

        return elements

    def _extract_text_blocks(
        self,
        page: fitz.Page,
        page_num: int,
        table_bboxes: list,
        hf_zones: list | None = None,
    ) -> list[ParsedElement]:
        """提取文字块，跳过表格区域和页眉页脚"""
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
                line_bbox = tuple(line["bbox"])

                # 跳过页眉页脚
                if hf_zones and is_in_header_footer(line_bbox, hf_zones):
                    continue

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
                        bbox=line_bbox,
                        style={
                            "font_size": max_font_size,
                            "bold": is_bold,
                        },
                    )
                )

        return elements

    def _extract_table_text(self, table) -> str:
        """将 pymupdf 表格对象提取为 Markdown 表格"""
        rows = table.extract()
        if not rows:
            return ""

        md_lines = []
        for i, row in enumerate(rows):
            cells = [str(cell).replace("|", "｜") if cell else "" for cell in row]
            md_lines.append("| " + " | ".join(cells) + " |")
            # 表头后插入分隔行
            if i == 0:
                md_lines.append("|" + "|".join("---" for _ in cells) + "|")

        return "\n".join(md_lines)

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
        """根据样式和正则判断文字类型"""
        # 标题判断：样式（字号/加粗）OR 正则匹配
        if is_heading_combined(text, font_size, is_bold):
            return "title"
        # 列表项判断
        if text.startswith(("•", "●", "◆", "○", "■")) or (
            len(text) > 2 and text[0].isdigit() and text[1] in ".)"
        ):
            return "list_item"
        return "text"

    def supported_types(self) -> list[str]:
        return ["pdf"]
