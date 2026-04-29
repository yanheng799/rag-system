"""段落边界识别模块：将扁平 Element 列表按语义段落边界聚合"""

from __future__ import annotations

import logging

from ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)

# 默认垂直间距阈值（像素），超过此值认为是新段落
DEFAULT_VERTICAL_GAP_THRESHOLD = 15.0
# 默认行高倍数阈值
DEFAULT_LINE_HEIGHT_MULTIPLIER = 1.5


def is_new_paragraph_boundary(
    elem: ParsedElement,
    group: list[ParsedElement],
    vertical_gap_threshold: float = DEFAULT_VERTICAL_GAP_THRESHOLD,
) -> bool:
    """
    判断当前元素是否为新段落边界。

    以下任一条件成立则认为是新段落：
    1. elem 类型为 "title"（标题级元素必然是新段落）
    2. elem 与 group 最后一个元素的垂直间距 > 阈值
    3. elem 在新的一页（跨页判断）
    4. 当前 group 为空
    """
    if not group:
        return True

    # 标题元素始终是新段落起点
    if elem.is_title:
        return True

    last = group[-1]

    # 跨页判断：不同页码视为新段落
    if elem.page != last.page:
        return True

    # 垂直间距判断
    gap = _calculate_vertical_gap(last, elem)
    if gap > vertical_gap_threshold:
        return True

    return False


def group_elements_by_paragraph(
    elements: list[ParsedElement],
    vertical_gap_threshold: float = DEFAULT_VERTICAL_GAP_THRESHOLD,
) -> list[list[ParsedElement]]:
    """
    将扁平 Element 列表按段落边界聚合为段落组。

    每个 paragraph group 可能包含文字和表格的混合内容。
    """
    if not elements:
        return []

    paragraphs: list[list[ParsedElement]] = []
    current_group: list[ParsedElement] = []

    for elem in elements:
        if is_new_paragraph_boundary(elem, current_group, vertical_gap_threshold):
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
    return paragraphs


def _calculate_vertical_gap(elem_a: ParsedElement, elem_b: ParsedElement) -> float:
    """计算两个元素之间的垂直间距"""
    # elem_a 的底部 y 坐标 - elem_b 的顶部 y 坐标
    a_bottom = elem_a.bbox[3]
    b_top = elem_b.bbox[1]

    # 如果 a 在 b 上方，gap 为正
    gap = b_top - a_bottom

    # 处理重叠情况（负值表示重叠，不算新段落）
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
