"""跨页/跨列表格合并后处理"""

from __future__ import annotations

import logging

from src.ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


def _count_columns(md_content: str) -> int:
    """从 Markdown 表格内容中统计列数（基于分隔行 |---| 的段数）。"""
    for line in md_content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and "---" in stripped:
            return stripped.count("|") - 1
    # 回退：取第一行的 | 段数
    first = md_content.split("\n")[0].strip()
    if first.startswith("|"):
        return first.count("|") - 1
    return 0


def _split_header_body(md_content: str) -> tuple[str, list[str]]:
    """将 Markdown 表格拆分为表头部分和数据行。

    Returns:
        (header_text, body_lines) — 表头含表头行+分隔行，body_lines 为纯数据行
    """
    lines = md_content.strip().split("\n")
    if len(lines) < 2:
        return md_content, []

    header_lines = [lines[0]]  # 表头行
    body_start = 1

    # 查找分隔行
    for i in range(1, len(lines)):
        if "---" in lines[i]:
            header_lines.append(lines[i])
            body_start = i + 1
            break

    header = "\n".join(header_lines)
    body = lines[body_start:]
    return header, body


def merge_cross_page_tables(
    elements: list[ParsedElement],
    page_sizes: dict[int, tuple[float, float]],
) -> list[ParsedElement]:
    """合并跨页断裂的表格。

    检测条件：
    - 两个表格页码相邻（page N 和 page N+1）
    - 列数相同
    - 表 N 的 y1 接近页面底部，表 N+1 的 y0 接近页面顶部
    """
    if not elements or not page_sizes:
        return elements

    tables = [(i, e) for i, e in enumerate(elements) if e.is_table]
    if len(tables) < 2:
        return elements

    # 标记需要删除的索引
    merged_away: set[int] = set()

    for ti in range(len(tables) - 1):
        idx_a, elem_a = tables[ti]
        if idx_a in merged_away:
            continue

        # 追踪合并后的有效末页，支持多页连续合并
        last_page_a = elem_a.page
        last_page_a_y1 = elem_a.bbox[3]

        for tj in range(ti + 1, len(tables)):
            idx_b, elem_b = tables[tj]
            if idx_b in merged_away:
                continue

            if not _is_cross_page_continuation(elem_a, elem_b, page_sizes, last_page_a, last_page_a_y1):
                continue

            # 列数匹配
            cols_a = _count_columns(elem_a.content)
            cols_b = _count_columns(elem_b.content)
            if cols_a == 0 or cols_b == 0 or cols_a != cols_b:
                continue

            # 合并：移除表 B 的表头，数据行追加到表 A
            _, body_b = _split_header_body(elem_b.content)
            merged_content = elem_a.content.rstrip()
            for row in body_b:
                if row.strip():
                    merged_content += "\n" + row

            # 更新表 A（y1 取第一页高度，避免跨页坐标混合导致 y0 > y1）
            size_a = page_sizes.get(elem_a.page)
            if not size_a:
                continue
            _, height_a = size_a
            new_bbox = (
                min(elem_a.bbox[0], elem_b.bbox[0]),
                elem_a.bbox[1],
                max(elem_a.bbox[2], elem_b.bbox[2]),
                height_a,
            )
            elem_a.content = merged_content
            elem_a.bbox = new_bbox

            # 记录被合并页信息，供截图时为每页各截一张
            if not isinstance(elem_a.raw, dict):
                elem_a.raw = {}
            merged_pages = elem_a.raw.setdefault("_merged_pages", [])
            merged_pages.append({"page": elem_b.page, "bbox": tuple(elem_b.bbox)})

            merged_away.add(idx_b)
            last_page_a = elem_b.page
            last_page_a_y1 = elem_b.bbox[3]
            logger.info(
                "跨页表格合并: page %d + page %d (列数=%d)",
                elem_a.page,
                elem_b.page,
                cols_a,
            )

    if merged_away:
        elements = [e for i, e in enumerate(elements) if i not in merged_away]

    return elements


def _is_cross_page_continuation(
    elem_a: ParsedElement,
    elem_b: ParsedElement,
    page_sizes: dict[int, tuple[float, float]],
    last_page_a: int | None = None,
    last_page_a_bbox_y1: float | None = None,
) -> bool:
    """判断 elem_b 是否是 elem_a 的跨页续表。

    last_page_a: 合并后 elem_a 的有效末页页码（用于多页连续合并）。
    last_page_a_bbox_y1: 有效末页表格的 y1 坐标（用于判断末页表格是否到底）。
    """
    # 页码必须相邻（用有效末页判断，而非 elem_a 原始页码）
    effective_page_a = last_page_a if last_page_a is not None else elem_a.page
    if elem_b.page != effective_page_a + 1:
        return False

    size_a = page_sizes.get(effective_page_a)
    size_b = page_sizes.get(elem_b.page)
    if not size_a or not size_b:
        return False

    _, height_a = size_a
    _, height_b = size_b

    # 末页表格的 y1（多页合并时用最后一页的 y1，否则用 elem_a 原始 y1）
    a_y1 = last_page_a_bbox_y1 if last_page_a_bbox_y1 is not None else elem_a.bbox[3]
    # 表 A 接近页底（y1 > 页面高度 × 0.85）
    if a_y1 < height_a * 0.85:
        return False

    # 表 B 接近页顶（y0 < 页面高度 × 0.15）
    return not elem_b.bbox[1] > height_b * 0.15


def merge_cross_column_tables(
    elements: list[ParsedElement],
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> list[ParsedElement]:
    """合并同一页面中被双栏排版拆分为左右两部分的表格。

    检测条件：
    - 两个表格在同一页
    - 分别在中线左右两侧
    - y 坐标相近
    - 列数相同
    """
    if len(elements) < 2:
        return elements

    # 按页分组表格
    page_tables: dict[int, list[tuple[int, ParsedElement]]] = {}
    for i, e in enumerate(elements):
        if e.is_table:
            page_tables.setdefault(e.page, []).append((i, e))

    merged_away: set[int] = set()

    for page, tables in page_tables.items():
        if len(tables) < 2:
            continue

        # 获取页面尺寸
        page_width = None
        page_height = None
        if page_sizes and page in page_sizes:
            page_width = page_sizes[page][0]
            page_height = page_sizes[page][1]

        if not page_width:
            # 从元素 bbox 推算
            max_x = max(t[1].bbox[2] for t in tables)
            page_width = max_x * 1.05  # 留余量

        mid = page_width / 2

        for ti in range(len(tables)):
            idx_a, elem_a = tables[ti]
            if idx_a in merged_away:
                continue

            for tj in range(ti + 1, len(tables)):
                idx_b, elem_b = tables[tj]
                if idx_b in merged_away:
                    continue

                if not _is_cross_column_pair(elem_a, elem_b, mid, page_width, page_height):
                    continue

                # 列数匹配
                cols_a = _count_columns(elem_a.content)
                cols_b = _count_columns(elem_b.content)
                if cols_a == 0 or cols_b == 0 or cols_a != cols_b:
                    continue

                # 合并：将右表数据行追加到左表
                _, body_b = _split_header_body(elem_b.content)
                merged_content = elem_a.content.rstrip()
                for row in body_b:
                    if row.strip():
                        merged_content += "\n" + row

                # 更新表 A bbox
                new_bbox = (
                    min(elem_a.bbox[0], elem_b.bbox[0]),
                    min(elem_a.bbox[1], elem_b.bbox[1]),
                    max(elem_a.bbox[2], elem_b.bbox[2]),
                    max(elem_a.bbox[3], elem_b.bbox[3]),
                )
                elem_a.content = merged_content
                elem_a.bbox = new_bbox

                merged_away.add(idx_b)
                logger.info(
                    "跨列表格合并: page %d, 列数=%d",
                    page,
                    cols_a,
                )

    if merged_away:
        elements = [e for i, e in enumerate(elements) if i not in merged_away]

    return elements


def _is_cross_column_pair(
    elem_a: ParsedElement,
    elem_b: ParsedElement,
    mid: float,
    page_width: float,
    page_height: float | None = None,
) -> bool:
    """判断两个表格是否为同一表格被双栏拆分的左右两部分。"""
    # 一个在中线左侧，一个在中线右侧
    a_center = (elem_a.bbox[0] + elem_a.bbox[2]) / 2
    b_center = (elem_b.bbox[0] + elem_b.bbox[2]) / 2

    a_is_left = a_center < mid
    b_is_left = b_center < mid

    if a_is_left == b_is_left:
        return False

    # y 坐标相近（y 差值 < 页面纵向尺寸 × 0.1）
    y_diff = abs(elem_a.bbox[1] - elem_b.bbox[1])
    tolerance = (page_height or page_width) * 0.1
    return not y_diff > tolerance
