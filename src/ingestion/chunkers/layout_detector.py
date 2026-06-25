"""PDF 排版格式检测 — 单栏/双栏识别、页眉页脚清洗、目录检测、元素重排"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter

import fitz

from src.ingestion.parsers.base import ParsedElement

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
    return any(x0 < tx1 and x1 > tx0 and y0 < ty1 and y1 > ty0 for tx0, ty0, tx1, ty1 in table_bboxes)


def detect_header_footer_zones(
    doc: fitz.Document,
    min_repeat: int = 3,
    max_pages: int | None = None,
    scan_n: int = 15,
) -> list[tuple[float, float, frozenset[str], bool]]:
    """检测文档中页眉 / 页脚的 y 坐标区间。

    策略:取前 scan_n 页,读取每页顶部(页眉)和底部(页脚)的"第一行",
    若文本完全相同、或文本中的数字呈常数步长递增(差分恒定且非零),
    则判定为页眉 / 页脚区间。跳过无候选行的页(封面 / 空白页)。

    Args:
        doc: pymupdf 文档
        min_repeat: 绝对最少命中页数(同时作为短文档保护阈值)
        max_pages: 扫描页数上限(pdf_parser 切片解析时传入)
        scan_n: 前 N 页的 N(默认 15,覆盖封面 + 目录 + 多页正文)
            8 页时若文档前部含较多封面/目录页,正文页眉样本不足无法命中阈值,
            故放宽到 15 页以确保正文页眉/页脚有足够重复样本。

    Returns:
        [(y_min, y_max, {norm_texts}, is_numeric), ...] — 应被过滤的 y 坐标区间、
        归一化文本集合，以及是否为纯数字页码区（is_numeric=True 时区域内短数字行直接剔除）
    """
    if len(doc) < min_repeat:
        return []

    effective_n = min(scan_n, len(doc))
    if max_pages is not None:
        effective_n = min(effective_n, max_pages)

    page_height = doc[0].rect.height
    header_limit = page_height * 0.08  # 顶部 8%
    footer_limit = page_height * 0.88  # 底部 12%（页码常贴着 90% 线，0.90 会把页码 y 卡在候选区外）

    # 收集每页 header / footer 候选行:(page, y0, raw_text)
    header_candidates: list[tuple[int, float, str]] = []
    footer_candidates: list[tuple[int, float, str]] = []

    for pn in range(effective_n):
        page = doc[pn]
        try:
            table_bboxes = [tuple(t.bbox) for t in page.find_tables()]
        except Exception:
            logger.debug("find_tables 失败: page %d，跳过表格过滤", pn)
            table_bboxes = []

        header_lines: list[tuple[float, str]] = []  # (y0, text) 候选区域内的行
        footer_lines: list[tuple[float, str]] = []
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"]).strip()
                if not text:
                    continue
                # 页码常为 1~3 位纯数字，不能被通用最小长度过滤掉
                if len(text) < 3 and not text.isdigit():
                    continue
                line_bbox = tuple(line["bbox"])
                if _bbox_in_table(line_bbox, table_bboxes):
                    continue
                y0 = line["bbox"][1]
                if y0 < header_limit:
                    header_lines.append((y0, text))
                elif y0 > footer_limit:
                    footer_lines.append((y0, text))

        # 页眉取 y 最小的第一行,页脚取 y 最大的第一行
        if header_lines:
            header_lines.sort(key=lambda x: x[0])
            header_candidates.append((pn, header_lines[0][0], header_lines[0][1]))
        if footer_lines:
            footer_lines.sort(key=lambda x: x[0], reverse=True)
            footer_candidates.append((pn, footer_lines[0][0], footer_lines[0][1]))

    zones: list[tuple[float, float, frozenset[str]]] = []
    for candidates in (header_candidates, footer_candidates):
        zone = _detect_zone_from_candidates(candidates, min_repeat)
        if zone:
            zones.append(zone)

    if zones:
        logger.info("检测到 %d 个页眉/页脚区间: %s", len(zones), [(z[0], z[1]) for z in zones])

    return zones


def _detect_zone_from_candidates(
    candidates: list[tuple[int, float, str]],
    min_repeat: int,
) -> tuple[float, float, frozenset[str], bool] | None:
    """对一组候选行(页眉或页脚)判定是否构成页眉 / 页脚区间。

    阈值 threshold = max(min_repeat, ceil(V * 0.6)),V 为候选页数,
    允许约 40% 的页偏离(如章节首页无页眉 / 表格页无页码)。

    分支 A(优先):strip 后文本完全相同的页数 >= threshold。
    分支 B:页码递增 —— 编号与页码呈常数偏移(number - page_index = 常数),
    按偏移众数判定,容忍表格页等缺页造成的候选间隙(不依赖相邻候选差分恒定)。

    Returns:
        (y_min, y_max, {norm}, is_numeric) 或 None。
        is_numeric 为 True 表示该区为纯数字页码区(归一化样本不足 2 字符)。
    """
    v = len(candidates)
    if v < min_repeat:
        return None
    threshold = max(min_repeat, math.ceil(v * 0.6))

    # 分支 A:文本完全相同
    same_text, same_count = Counter(c[2].strip() for c in candidates).most_common(1)[0]
    if same_count >= threshold:
        hit = [c for c in candidates if c[2].strip() == same_text]
        y_min = min(c[1] for c in hit)
        y_max = max(c[1] for c in hit) + 8
        norm = _normalize_text(same_text)
        return (y_min, y_max, frozenset({norm}) if norm else frozenset(), len(norm) < 2)

    # 分支 B:页码递增(number - page_index = 常数),按偏移众数判定,容忍缺页间隙
    nums: list[tuple[int, int]] = []  # (page, number)
    for pn, _y, text in candidates:
        m = re.search(r"\d+", text)
        if m:
            nums.append((pn, int(m.group())))
    if len(nums) >= threshold:
        offset_counter: Counter[int] = Counter(n - pn for pn, n in nums)
        dom_offset, dom_count = offset_counter.most_common(1)[0]
        if dom_count >= threshold:
            hit_pages = {pn for pn, n in nums if n - pn == dom_offset}
            hit = [c for c in candidates if c[0] in hit_pages]
            y_min = min(c[1] for c in hit)
            y_max = max(c[1] for c in hit) + 8
            sample = next(c[2] for c in candidates if c[0] in hit_pages)
            norm = _normalize_text(sample)
            return (y_min, y_max, frozenset({norm}) if norm else frozenset(), len(norm) < 2)

    return None


def is_in_header_footer(
    bbox: tuple,
    zones: list[tuple],
    text: str = "",
) -> bool:
    """判断元素是否位于页眉 / 页脚区间内。

    除 y 坐标匹配外，还需验证文本归一化形式落在 zone 的已知页眉/页脚文本集合中，
    避免章节标题因 y 恰好落在 zone 范围内而被误杀。

    纯数字页码区(zone 第 4 位 is_numeric=True)例外：区域内 1~3 位纯数字行
    (即页码本身)直接剔除——页码归一化后为空，无法走文本匹配分支。
    兼容历史 3 元组 zone(无 is_numeric 位，按文本匹配处理)。
    """
    y0 = bbox[1]
    norm = _normalize_text(text) if text else ""
    stripped = text.strip() if text else ""
    for zone in zones:
        z_min, z_max, norm_set = zone[0], zone[1], zone[2]
        is_numeric = zone[3] if len(zone) > 3 else False
        if not (z_min <= y0 <= z_max):
            continue
        if is_numeric:
            # 页码区：区域内短数字行(页码)直接剔除
            if stripped.isdigit() and len(stripped) <= 3:
                return True
            continue
        if norm and len(norm) >= 2 and norm in norm_set:
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
    left_vext = max(w[3] for w in left_words) - min(w[1] for w in left_words) if left_words else 0
    right_vext = max(w[3] for w in right_words) - min(w[1] for w in right_words) if right_words else 0

    # 两侧都需有足够词数和垂直跨度
    min_words = max(len(words) * 0.1, 10)
    min_vext = page_height * 0.3
    if left_count < min_words or right_count < min_words or left_vext < min_vext or right_vext < min_vext:
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

    for fw_elem in full_width:
        fw_y = fw_elem.bbox[1]

        # 取出左列中 y < 全宽元素 y 的部分
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

    # 只扫描文档前 20% 页面（最多 20 页）
    max_check = min(max(total // 5, 10), 20)

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
    return total_lines >= 3 and toc_entry_count / total_lines >= 0.4


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
