"""段落边界识别模块：将扁平 Element 列表按语义段落边界聚合"""

from __future__ import annotations

import logging

from ingestion.chunkers.heading_patterns import is_heading_by_pattern
from ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)

# 默认垂直间距阈值（像素），超过此值认为是新段落
DEFAULT_VERTICAL_GAP_THRESHOLD = 15.0
# 默认最大分块字符数
DEFAULT_MAX_CHUNK_SIZE = 1024


def is_heading_element(elem: ParsedElement) -> bool:
    """判断元素是否为标题（elem_type 或正则匹配）"""
    if elem.is_title:
        return True
    return is_heading_by_pattern(elem.content)


def is_new_paragraph_boundary(
    elem: ParsedElement,
    group: list[ParsedElement],
    vertical_gap_threshold: float = DEFAULT_VERTICAL_GAP_THRESHOLD,
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> bool:
    """
    判断当前元素是否为新段落边界。

    规则：
    1. 当前 group 为空 → 新段落
    2. 跨页 → 如果是页底→页顶的连续文本则不拆分，否则新段落
    3. 垂直间距 > 阈值 且 前一个元素不是标题 → 新段落
    4. 标题元素不触发新边界（标题与下方内容合并）
    """
    if not group:
        return True

    last = group[-1]

    # 跨页判断
    if elem.page != last.page:
        if (
            page_sizes
            and not elem.is_table
            and not last.is_table
            and _is_page_continuation(last, elem, page_sizes)
        ):
            return False
        return True

    # 垂直间距判断
    gap = _calculate_vertical_gap(last, elem)
    if gap > vertical_gap_threshold:
        # 前一个元素是标题 → 不拆分，标题吸收下方内容
        if is_heading_element(last):
            return False
        return True

    return False


def group_elements_by_paragraph(
    elements: list[ParsedElement],
    vertical_gap_threshold: float = DEFAULT_VERTICAL_GAP_THRESHOLD,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> list[list[ParsedElement]]:
    """
    将扁平 Element 列表按段落边界聚合为段落组。

    两阶段处理：
    1. 按段落边界分组（标题与内容合并）
    2. 超长分组拆分（不超过 max_chunk_size 字符）
    """
    if not elements:
        return []

    # 阶段 1：按段落边界分组
    paragraphs: list[list[ParsedElement]] = []
    current_group: list[ParsedElement] = []

    for elem in elements:
        if is_new_paragraph_boundary(elem, current_group, vertical_gap_threshold, page_sizes):
            if current_group:
                paragraphs.append(current_group)
            current_group = [elem]
        else:
            current_group.append(elem)

    # 最后一组
    if current_group:
        paragraphs.append(current_group)

    logger.info(
        "段落边界识别完成: %d 个元素 → %d 个段落组",
        len(elements),
        len(paragraphs),
    )

    # 阶段 2：超长分组拆分
    if max_chunk_size > 0:
        paragraphs = _split_oversized_groups(paragraphs, max_chunk_size)
        logger.info("超长拆分后: %d 个段落组", len(paragraphs))

    return paragraphs


def _split_oversized_groups(
    paragraphs: list[list[ParsedElement]],
    max_chunk_size: int,
) -> list[list[ParsedElement]]:
    """拆分超长的段落组"""
    result: list[list[ParsedElement]] = []
    for group in paragraphs:
        group_size = sum(len(e.content) for e in group)
        if group_size <= max_chunk_size or len(group) <= 1:
            result.append(group)
            continue
        sub_groups = _split_group_by_size(group, max_chunk_size)
        result.extend(sub_groups)
    return result


def _split_group_by_size(
    group: list[ParsedElement],
    max_chunk_size: int,
) -> list[list[ParsedElement]]:
    """按元素边界拆分单个段落组。

    确保标题不会孤立：如果子组以标题开头，至少包含一个非标题元素。
    """
    sub_groups: list[list[ParsedElement]] = []
    current: list[ParsedElement] = []
    current_size = 0

    for elem in group:
        elem_size = len(elem.content)

        # 单个元素超限 → 单独成组
        if elem_size > max_chunk_size and current:
            sub_groups.append(current)
            current = [elem]
            current_size = elem_size
            continue

        # 加入当前元素会超限 → 切分
        if current_size + elem_size > max_chunk_size and current:
            # 如果当前组只有标题一个元素，强制吸收下一个元素避免标题孤立
            if len(current) == 1 and is_heading_element(current[0]):
                current.append(elem)
                current_size += elem_size
                continue
            sub_groups.append(current)
            current = [elem]
            current_size = elem_size
            continue

        current.append(elem)
        current_size += elem_size

    if current:
        # 如果最后一个子组是孤立的标题，合并到前一个子组
        if len(current) == 1 and is_heading_element(current[0]) and sub_groups:
            sub_groups[-1].extend(current)
        else:
            sub_groups.append(current)

    return sub_groups


def _is_page_continuation(
    last: ParsedElement,
    elem: ParsedElement,
    page_sizes: dict[int, tuple[float, float]],
) -> bool:
    """判断跨页元素是否为连续段落（页底→页顶）。"""
    size_last = page_sizes.get(last.page)
    size_elem = page_sizes.get(elem.page)
    if not size_last or not size_elem:
        return False

    _, height_last = size_last
    _, height_elem = size_elem

    # 前一个元素在页底（y1 > 页面高度 × 0.85）
    if last.bbox[3] < height_last * 0.85:
        return False

    # 当前元素在页顶（y0 < 页面高度 × 0.15）
    if elem.bbox[1] > height_elem * 0.15:
        return False

    return True


def _calculate_vertical_gap(elem_a: ParsedElement, elem_b: ParsedElement) -> float:
    """计算两个元素之间的垂直间距"""
    a_bottom = elem_a.bbox[3]
    b_top = elem_b.bbox[1]
    gap = b_top - a_bottom
    return max(0, gap)


def detect_chunk_type(group: list[ParsedElement]) -> str:
    """检测段落组的类型"""
    has_text = any(not e.is_table for e in group)
    has_table = any(e.is_table for e in group)

    if has_text and has_table:
        return "mixed"
    if has_table:
        return "table"
    return "text"
