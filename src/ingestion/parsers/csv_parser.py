"""CSV 文档解析器"""

from __future__ import annotations

import csv
import io
import logging

from src.ingestion.parsers.base import BaseParser, ParsedElement, ParseError, format_rows, read_text_file

logger = logging.getLogger(__name__)

MAX_ROWS_PER_ELEMENT = 100
_SNIFFER_SAMPLE_LINES = 50
_DELIMITER_CANDIDATES = [",", ";", "\t"]


def _detect_delimiter(text: str, hint: str | None = None) -> tuple[str, list[list[str]]]:
    """检测分隔符并解析所有行。

    优先使用 hint（API 传入），其次 csv.Sniffer，最后按优先级尝试。
    返回 (delimiter, rows)。
    """
    sample = "\n".join(text.split("\n")[:_SNIFFER_SAMPLE_LINES])

    if hint:
        reader = csv.reader(io.StringIO(text), delimiter=hint)
        rows = [row for row in reader]
        return hint, rows

    # csv.Sniffer 尝试
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITER_CANDIDATES))
        reader = csv.reader(io.StringIO(text), dialect=dialect)
        rows = [row for row in reader]
        if rows and max(len(r) for r in rows) > 1:
            return dialect.delimiter, rows
    except csv.Error:
        pass

    # 按优先级尝试
    best_delimiter = ","
    best_rows: list[list[str]] = []
    best_stable_cols = 1

    for delim in _DELIMITER_CANDIDATES:
        reader = csv.reader(io.StringIO(text), delimiter=delim)
        rows = [row for row in reader]
        if not rows:
            continue
        col_counts = [len(r) for r in rows]
        max_cols = max(col_counts)
        # 稳定性：大多数行列数一致且 > 1
        if max_cols <= 1:
            continue
        from collections import Counter

        mode_cols = Counter(col_counts).most_common(1)[0][0]
        if mode_cols > best_stable_cols:
            best_delimiter = delim
            best_rows = rows
            best_stable_cols = mode_cols

    if not best_rows:
        best_rows = list(csv.reader(io.StringIO(text)))

    return best_delimiter, best_rows


def _detect_has_header(rows: list[list[str]]) -> bool:
    """检测首行是否为表头。"""
    if len(rows) < 2:
        return False
    try:
        sample = "\n".join(",".join(r) for r in rows[:10])
        return csv.Sniffer().has_header(sample)
    except csv.Error:
        return False


class CsvParser(BaseParser):
    """CSV 文档解析器，支持自动检测分隔符和表头"""

    def __init__(self, delimiter: str | None = None):
        self._delimiter = delimiter

    def parse(self, file_path: str) -> list[ParsedElement]:
        try:
            text = read_text_file(file_path)
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(file_path, str(e)) from e

        if not text.strip():
            return []

        delimiter, rows = _detect_delimiter(text, self._delimiter)

        if not rows:
            return []

        # 表头检测
        has_header = _detect_has_header(rows)
        if has_header:
            headers = [h.strip() or f"列{i + 1}" for i, h in enumerate(rows[0])]
            data_rows = rows[1:]
        else:
            max_cols = max(len(r) for r in rows) if rows else 0
            headers = [f"列{i + 1}" for i in range(max_cols)]
            data_rows = rows

        # 清理行数据
        clean_rows = []
        for row in data_rows:
            clean_row = [str(cell).strip() if cell is not None else "" for cell in row]
            # 补齐列数
            while len(clean_row) < len(headers):
                clean_row.append("")
            clean_rows.append(clean_row)

        # 按 MAX_ROWS_PER_ELEMENT 分块
        elements: list[ParsedElement] = []
        for chunk_index, i in enumerate(range(0, len(clean_rows), MAX_ROWS_PER_ELEMENT)):
            chunk_rows = clean_rows[i : i + MAX_ROWS_PER_ELEMENT]
            content = format_rows(headers, chunk_rows)

            elements.append(
                ParsedElement(
                    elem_type="table",
                    content=content,
                    page=1,
                    bbox=(0, 0, 0, 0),
                    raw={"headers": headers, "rows": chunk_rows},
                )
            )

        logger.info("CSV 解析完成: %s, 共 %d 个元素 (分隔符=%r)", file_path, len(elements), delimiter)
        return elements

    def supported_types(self) -> list[str]:
        return ["csv"]
