"""段落边界识别模块：将扁平 Element 列表按语义段落边界聚合"""

from __future__ import annotations

import logging

from ingestion.chunkers.heading_patterns import is_heading_by_pattern, is_heading_combined, is_section_heading
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
    2. 标题元素始终触发新边界（按标题分片）
    3. 跨页 → 如果是页底→页顶的连续文本则不拆分，否则新段落
    4. 垂直间距 > 阈值 且 前一个元素不是标题 → 新段落
    """
    if not group:
        return True

    # 章节标题始终开始新段落（标题吸收下方内容，但不合并到上一个段落）
    # 同时检查：严格正则匹配 或 文档样式标记为标题且内容匹配编号模式
    if is_section_heading(elem.content):
        return True
    if elem.is_title and is_heading_by_pattern(elem.content):
        return True

    last = group[-1]

    # 跨页判断
    if elem.page != last.page:
        # 当前 group 以章节标题开头 → 放宽续接条件，标题内容应保持完整
        first = group[0]
        if is_section_heading(first.content):
            if (
                page_sizes
                and not elem.is_table
                and elem.bbox[1] < page_sizes.get(elem.page, (0, 9999))[1] * 0.40
            ):
                return False
        # 常规跨页续接
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
    doc_id: str = "",
) -> list[tuple[list[ParsedElement], str]]:
    """
    将扁平 Element 列表按段落边界聚合为段落组。

    两阶段处理：
    1. 按段落边界分组（标题与内容合并）
    2. 超长分组拆分（不超过 max_chunk_size 字符）

    返回 list[tuple[elements, group_id]]：
    - 未拆分的段落 group_id 为空串
    - 被拆分的段落所有子组共享同一 group_id
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

    # 阶段 1.5：孤立标题合并到下一个 group
    paragraphs = _merge_heading_only_groups(paragraphs)

    # 阶段 2：超长分组拆分
    if max_chunk_size > 0:
        result = _split_oversized_groups(paragraphs, max_chunk_size, doc_id)
        logger.info("超长拆分后: %d 个段落组", len(result))
        return result

    return [(p, "") for p in paragraphs]


def _merge_heading_only_groups(
    paragraphs: list[list[ParsedElement]],
) -> list[list[ParsedElement]]:
    """将只含标题（无实质内容）的 group 合并到下一个 group。"""
    if len(paragraphs) <= 1:
        return paragraphs

    merged: list[list[ParsedElement]] = []
    i = 0
    while i < len(paragraphs):
        group = paragraphs[i]
        total_chars = sum(len(e.content) for e in group)

        # 孤立标题：总字符少，且只有标题+图片元素
        if total_chars < 40 and i + 1 < len(paragraphs):
            has_content = any(
                not is_section_heading(e.content) and not e.is_image
                for e in group
                if e.content.strip()
            )
            if not has_content:
                # 合并到下一个 group
                paragraphs[i + 1] = group + paragraphs[i + 1]
                i += 1
                continue

        merged.append(group)
        i += 1

    return merged


def _split_oversized_groups(
    paragraphs: list[list[ParsedElement]],
    max_chunk_size: int,
    doc_id: str = "",
) -> list[tuple[list[ParsedElement], str]]:
    """拆分超长的段落组，被拆分的组共享同一个 group_id"""
    result: list[tuple[list[ParsedElement], str]] = []
    group_counter = 0
    for group in paragraphs:
        group_size = sum(len(e.content) for e in group)
        if group_size <= max_chunk_size or len(group) <= 1:
            result.append((group, ""))
            continue
        gid = f"{doc_id}_g{group_counter}" if doc_id else f"g{group_counter}"
        sub_groups = _split_group_by_size(group, max_chunk_size)
        for sg in sub_groups:
            result.append((sg, gid))
        group_counter += 1
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
            # 表格标题保护：末尾短文本 + 紧跟表格 → 标题随表格进入新分组
            if elem.is_table and len(current) >= 1:
                last_cur = current[-1]
                if len(last_cur.content) < 30 and not is_heading_element(last_cur):
                    caption = current.pop()
                    current_size -= len(caption.content)
                    sub_groups.append(current)
                    current = [caption, elem]
                    current_size = len(caption.content) + elem_size
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
    has_table = any(e.is_table for e in group)
    has_image = any(e.is_image for e in group)
    has_text = any(not e.is_table and not e.is_image for e in group)

    if (has_text and has_table) or (has_text and has_image) or (has_table and has_image):
        return "mixed"
    if has_table:
        return "table"
    if has_image:
        return "image"
    return "text"
