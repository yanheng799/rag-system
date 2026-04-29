"""PDF 排版格式检测 — 单栏/双栏识别、页眉页脚清洗、目录检测、元素重排"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

import fitz

from ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 页眉页脚检测
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """将文本中数字和多余空白去除，用于跨页比较。"""
    text = re.sub(r"\d+", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def _bbox_in_table(bbox: tuple, table_bboxes: list[tuple]) -> bool:
    """判断 bbox 是否落在任一表格区域内。"""
    x0, y0, x1, y1 = bbox
    for tx0, ty0, tx1, ty1 in table_bboxes:
        if x0 < tx1 and x1 > tx0 and y0 < ty1 and y1 > ty0:
            return True
    return False


def detect_header_footer_zones(
    doc: fitz.Document,
    min_repeat: int = 3,
) -> list[tuple[float, float]]:
    """检测文档中页眉 / 页脚的 y 坐标区间。

    仅在页面顶部 8% 和底部 10% 范围内搜索跨页重复的文本行。

    Returns:
        [(y_min, y_max), ...] — 应被过滤的 y 坐标区间列表
    """
    if len(doc) < min_repeat:
        return []

    page_height = doc[0].rect.height
    y_tolerance = page_height * 0.02  # 2 % 页面高度
    header_limit = page_height * 0.08  # 顶部 8%
    footer_limit = page_height * 0.90  # 底部 10%

    # 仅收集页面顶部和底部边缘、且不在表格内的文字行
    all_lines: list[tuple[int, float, str, str]] = []  # (page, y, norm, raw)
    for pn in range(len(doc)):
        page = doc[pn]
        # 收集本页表格区域
        table_bboxes = [tuple(t.bbox) for t in page.find_tables()]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip()
                if not text or len(text) < 3:
                    continue
                y0 = line["bbox"][1]
                # 仅保留页眉/页脚候选区域
                if y0 > header_limit and y0 < footer_limit:
                    continue
                # 跳过表格内的行
                line_bbox = tuple(line["bbox"])
                if _bbox_in_table(line_bbox, table_bboxes):
                    continue
                norm = _normalize_text(text)
                if len(norm) < 2:
                    continue
                all_lines.append((pn, y0, norm, text))

    # 按 y 坐标分桶
    y_buckets: list[tuple[float, list[tuple[int, float, str, str]]]] = []
    for item in all_lines:
        pn, y, norm, text = item
        placed = False
        for i, (avg_y, items) in enumerate(y_buckets):
            if abs(y - avg_y) <= y_tolerance:
                items.append(item)
                new_avg = sum(it[1] for it in items) / len(items)
                y_buckets[i] = (new_avg, items)
                placed = True
                break
        if not placed:
            y_buckets.append((y, [item]))

    # 识别重复行：在每个 y 桶内，按归一化文本二次分组
    zones: list[tuple[float, float]] = []
    for avg_y, items in y_buckets:
        by_norm: dict[str, list[tuple[int, float, str, str]]] = defaultdict(list)
        for it in items:
            by_norm[it[2]].append(it)

        for norm, norm_items in by_norm.items():
            unique_pages = {it[0] for it in norm_items}
            if len(unique_pages) < min_repeat:
                continue

            # 归一化文本在多页同一 y 坐标出现 → 页眉/页脚
            y_min = min(it[1] for it in norm_items)
            y_max = max(it[1] for it in norm_items) + 16
            zones.append((y_min, y_max))

    if zones:
        logger.info("检测到 %d 个页眉/页脚区间: %s", len(zones), zones)

    return zones


def is_in_header_footer(
    bbox: tuple,
    zones: list[tuple[float, float]],
) -> bool:
    """判断元素是否位于页眉 / 页脚区间内。"""
    y0 = bbox[1]
    for z_min, z_max in zones:
        if z_min <= y0 <= z_max:
            return True
    return False


# ---------------------------------------------------------------------------
# 排版格式检测
# ---------------------------------------------------------------------------

def detect_page_layout(page: fitz.Page) -> str:
    """检测单页排版格式。

    采用二维分析法:
    1. 检查页面中线两侧是否都有充足的内容（词数 + 垂直跨度）
    2. 在中线附近寻找连续低密度间隔，确认存在栏间距

    Returns:
        "single" 或 "double"
    """
    page_width = page.rect.width
    page_height = page.rect.height
    if page_width <= 0 or page_height <= 0:
        return "single"

    words = page.get_text("words")
    if not words or len(words) < 20:
        return "single"

    mid = page_width / 2

    # 按中线分左右两侧
    left_words = [w for w in words if w[2] <= mid]
    right_words = [w for w in words if w[0] >= mid]
    left_count = len(left_words)
    right_count = len(right_words)

    # 计算两侧垂直跨度
    left_vext = (
        max(w[3] for w in left_words) - min(w[1] for w in left_words)
        if left_words
        else 0
    )
    right_vext = (
        max(w[3] for w in right_words) - min(w[1] for w in right_words)
        if right_words
        else 0
    )

    # 两侧都需有足够词数和垂直跨度
    min_words = max(len(words) * 0.1, 10)
    min_vext = page_height * 0.3
    if (
        left_count < min_words
        or right_count < min_words
        or left_vext < min_vext
        or right_vext < min_vext
    ):
        return "single"

    # 在中线附近寻找连续低密度间隔 (直方图验证)
    num_bins = 100
    bin_width = page_width / num_bins
    histogram = [0] * num_bins
    for w in words:
        bin_idx = int(w[0] / bin_width)
        bin_idx = max(0, min(num_bins - 1, bin_idx))
        histogram[bin_idx] += 1

    # 在 35%-65% 区域搜索最长连续低密度段
    search_start = int(num_bins * 0.35)
    search_end = int(num_bins * 0.65)
    overall_avg = sum(histogram) / num_bins
    low_threshold = max(overall_avg * 0.15, 0.5)

    max_gap_len = 0
    cur_gap_len = 0
    for i in range(search_start, search_end):
        if histogram[i] <= low_threshold:
            cur_gap_len += 1
            if cur_gap_len > max_gap_len:
                max_gap_len = cur_gap_len
        else:
            cur_gap_len = 0

    # 至少 3 个连续空 bin（约 3% 页面宽度）才认定为栏间距
    if max_gap_len >= 3:
        return "double"

    return "single"


# ---------------------------------------------------------------------------
# 元素重排
# ---------------------------------------------------------------------------

def reorder_elements_for_layout(
    elements: list[ParsedElement],
    page_width: float,
    layout: str,
) -> list[ParsedElement]:
    """根据排版格式重排元素阅读顺序。

    单栏：按 (y, x) 排序（默认）
    双栏：左列从上到下，然后右列从上到下，全宽元素按 y 插入正确位置
    """
    if layout != "double" or page_width <= 0:
        return elements

    mid = page_width / 2
    full_width_threshold = page_width * 0.8

    # 分离全宽元素（表格等跨越双栏的元素）和普通元素
    full_width = [e for e in elements if (e.bbox[2] - e.bbox[0]) >= full_width_threshold]
    normal = [e for e in elements if (e.bbox[2] - e.bbox[0]) < full_width_threshold]

    left = sorted([e for e in normal if e.bbox[0] < mid], key=lambda e: (e.bbox[1], e.bbox[0]))
    right = sorted([e for e in normal if e.bbox[0] >= mid], key=lambda e: (e.bbox[1], e.bbox[0]))

    if not full_width:
        return left + right

    # 将全宽元素按 y 坐标与左右列元素交错插入
    return _interleave_full_width(left, right, full_width)


def _interleave_full_width(
    left: list[ParsedElement],
    right: list[ParsedElement],
    full_width: list[ParsedElement],
) -> list[ParsedElement]:
    """将全宽元素按 y 坐标插入左右列元素序列的正确位置。

    阅读顺序：左列元素(全宽y以下) → 全宽元素 → 右列元素(全宽y以下) → ...
    """
    full_width.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

    result: list[ParsedElement] = []
    fw_idx = 0

    for fw_elem in full_width:
        fw_y = fw_elem.bbox[1]

        # 取出左列中 y < 全宽元素 y 的部分
        remaining_left = []
        while left and left[0].bbox[1] < fw_y:
            result.append(left.pop(0))

        # 取出右列中 y < 全宽元素 y 的部分
        while right and right[0].bbox[1] < fw_y:
            result.append(right.pop(0))

        # 插入全宽元素
        result.append(fw_elem)

    # 追加剩余的左右列元素
    result.extend(left)
    result.extend(right)

    return result


# ---------------------------------------------------------------------------
# 目录页检测
# ---------------------------------------------------------------------------

# 目录条目中连续点号的最少数量
_DOT_LEADER_MIN = 10


def detect_toc_pages(doc: fitz.Document) -> set[int]:
    """检测 PDF 文档中的目录页。

    通过点号引导线（dot leader）特征识别目录页：
    每行有 span 包含大量连续 '.' 字符，且点号 span 的 x1 接近右边距。

    Returns:
        目录页页码集合（0-indexed）
    """
    total = len(doc)
    if total == 0:
        return set()

    # 只扫描文档前 20% 页面
    max_check = max(total // 5, 10)

    toc_pages: set[int] = set()
    for pn in range(min(max_check, total)):
        page = doc[pn]
        if _is_toc_page(page):
            toc_pages.add(pn)

    # 如果检测到目录页，检查相邻页是否也是目录页（可能目录跨越多页）
    if toc_pages:
        min_pn = min(toc_pages)
        max_pn = max(toc_pages)
        # 扩展连续范围（前后各检查1页）
        for pn in range(max(0, min_pn - 1), min(max_pn + 2, total)):
            if pn not in toc_pages:
                page = doc[pn]
                if _is_toc_page(page, threshold=3):
                    toc_pages.add(pn)

    if toc_pages:
        logger.info("检测到目录页: %s", sorted(toc_pages))

    return toc_pages


def _is_toc_page(page: fitz.Page, threshold: int = 5) -> bool:
    """判断页面是否为目录页。

    Args:
        page: pymupdf 页面对象
        threshold: 目录条目行的最少数量
    """
    blocks = page.get_text("dict")["blocks"]

    total_lines = 0
    toc_entry_count = 0

    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            line_text = "".join(s["text"] for s in line["spans"]).strip()
            if not line_text:
                continue
            total_lines += 1

            if _is_toc_entry_line(line):
                toc_entry_count += 1

    if total_lines == 0:
        return False

    # 匹配行数 ≥ 阈值 或 ≥ 总行数 40%
    if toc_entry_count >= threshold:
        return True
    if total_lines >= 3 and toc_entry_count / total_lines >= 0.4:
        return True

    return False


def _is_toc_entry_line(line: dict) -> bool:
    """判断一行是否为目录条目（含点号引导线）。

    检测条件：行中存在一个 span，连续 '.' 字符超过阈值数量。
    """
    for span in line["spans"]:
        text = span["text"]
        dot_count = text.count(".")
        if dot_count >= _DOT_LEADER_MIN:
            return True
    return False
