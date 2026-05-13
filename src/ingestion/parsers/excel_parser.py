"""Excel (.xlsx) 文档解析器（基于 openpyxl）"""

from __future__ import annotations

import logging
from typing import Optional

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError

logger = logging.getLogger(__name__)

# 每个 Element 的最大行数，避免单条 element 过长
MAX_ROWS_PER_ELEMENT = 100


class ExcelParser(BaseParser):
    """使用 openpyxl 解析 Excel 文档，按 sheet 逐块提取数据"""

    def parse(self, file_path: str) -> list[ParsedElement]:
        try:
            wb = load_workbook(file_path, read_only=True, data_only=True)
        except Exception as e:
            raise ParseError(file_path, str(e))

        elements: list[ParsedElement] = []

        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]
            sheet_elements = self._parse_sheet(ws, sheet_idx, sheet_name)
            elements.extend(sheet_elements)

        wb.close()
        logger.info("Excel 解析完成: %s, 共 %d 个元素", file_path, len(elements))
        return elements

    def _parse_sheet(
        self, ws, sheet_idx: int, sheet_name: str
    ) -> list[ParsedElement]:
        """解析单个 Sheet"""
        elements: list[ParsedElement] = []

        # 读取所有非空行
        rows_data = []
        for row in ws.iter_rows(values_only=True):
            # 跳过全空行
            if all(cell is None or str(cell).strip() == "" for cell in row):
                continue
            rows_data.append([str(cell) if cell is not None else "" for cell in row])

        if not rows_data:
            return elements

        # 第一行作为表头
        headers = rows_data[0]

        # 检测合并单元格区域（用于样式标记）
        merged_ranges = []
        if hasattr(ws, 'merged_cells') and ws.merged_cells:
            for merged_range in ws.merged_cells.ranges:
                merged_ranges.append(str(merged_range))

        # 按行数分组为多个 ParsedElement
        data_rows = rows_data[1:]
        chunk_index = 0

        for i in range(0, len(data_rows), MAX_ROWS_PER_ELEMENT):
            chunk_rows = data_rows[i : i + MAX_ROWS_PER_ELEMENT]
            content = self._format_rows(headers, chunk_rows, sheet_name)

            elements.append(
                ParsedElement(
                    elem_type="table",
                    content=content,
                    page=sheet_idx,  # Excel 使用 sheet index 作为 page
                    bbox=(0, chunk_index, 0, chunk_index + 1),
                    style={
                        "sheet_name": sheet_name,
                        "headers": headers,
                        "has_merged_cells": len(merged_ranges) > 0,
                    },
                )
            )
            chunk_index += 1

        return elements

    def _format_rows(
        self, headers: list[str], rows: list[list[str]], sheet_name: str
    ) -> str:
        """将行列数据格式化为自然语言描述"""
        lines = [f"工作表: {sheet_name}"]
        lines.append(f"表头: {' | '.join(headers)}")

        for row in rows:
            parts = []
            for idx, (header, value) in enumerate(
                zip(headers, row)
            ):
                if value.strip():
                    col_name = header.strip() if header.strip() else f"列{idx + 1}"
                    parts.append(f"{col_name}: {value.strip()}")
            if parts:
                lines.append("; ".join(parts))

        return "\n".join(lines)

    def supported_types(self) -> list[str]:
        return ["xlsx"]
