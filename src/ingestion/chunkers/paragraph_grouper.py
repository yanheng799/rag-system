"""段落边界识别模块：将扁平 Element 列表按语义段落边界聚合"""

from __future__ import annotations

import logging
from collections import Counter

from src.ingestion.chunkers.heading_patterns import is_heading_by_pattern, is_section_heading
from src.ingestion.parsers.base import ParsedElement

logger = logging.getLogger(__name__)

# 默认垂直间距阈值（像素），超过此值认为是新段落
DEFAULT_VERTICAL_GAP_THRESHOLD = 15.0
# 默认最大分块字符数
DEFAULT_MAX_CHUNK_SIZE = 1024
# 首行缩进检测阈值（像素），超过此值认为是缩进
DEFAULT_INDENT_THRESHOLD = 10.0
# 段末右边界阈值（像素），行尾距右边界超过此值视为段末短行
DEFAULT_RIGHT_MARGIN_THRESHOLD = 30.0
# ParagraphGrouper fallback: 标题级别阈值，heading_level <= 此值时视为段落边界
DEFAULT_HEADING_LEVEL_THRESHOLD = 3


def is_heading_element(elem: ParsedElement) -> bool:
    """判断元素是否为标题（elem_type 或正则匹配）"""
    if elem.is_title:
        return True
    return is_heading_by_pattern(elem.content)


def _is_zero_bbox_elements(elements: list[ParsedElement]) -> bool:
    """检测所有元素是否为零 bbox（TXT/Markdown/CSV 场景）。"""
    return all(e.bbox == (0, 0, 0, 0) for e in elements) if elements else False


def is_new_paragraph_boundary_fallback(
    elem: ParsedElement,
    group: list[ParsedElement],
    heading_level_threshold: int = DEFAULT_HEADING_LEVEL_THRESHOLD,
) -> bool:
    """零 bbox 元素的段落边界判断（fallback 模式）。

    边界信号：
    1. 空 group → 新段落
    2. 标题元素 + heading_level ≤ 阈值 → 新段落
    3. paragraph_break 标记 → 新段落

    注意：不检查 elem_type 变化。Markdown 中标题间的文字、列表、代码块
    天然属于同一章节，类型交替不应触发拆分。
    """
    if not group:
        return True

    # 标题元素：heading_level ≤ 阈值时为新段落
    if elem.is_title:
        level = elem.style.get("heading_level", 1)
        if level <= heading_level_threshold:
            return True

    # paragraph_break 标记
    if elem.style.get("paragraph_break"):
        return True

    return False


def is_new_paragraph_boundary(
    elem: ParsedElement,
    group: list[ParsedElement],
    vertical_gap_threshold: float = DEFAULT_VERTICAL_GAP_THRESHOLD,
    page_sizes: dict[int, tuple[float, float]] | None = None,
    body_margins: dict[int, list[tuple[float, float]]] | None = None,
    indent_threshold: float = DEFAULT_INDENT_THRESHOLD,
    right_margin_threshold: float = DEFAULT_RIGHT_MARGIN_THRESHOLD,
) -> bool:
    """
    判断当前元素是否为新段落边界。

    规则：
    1. 当前 group 为空 → 新段落
    2. 标题元素始终触发新边界（按标题分片）
    3. 跨页 → 如果是页底→页顶的连续文本则不拆分，否则新段落
    4. 垂直间距 > 阈值 且 前一个元素不是标题 → 新段落
    5. 首行缩进检测：当前元素 x0 显著右偏于正文左边距 → 新段落
    6. 段末短行检测：前一个元素 x1 显著小于正文右边界 → 新段落
    """
    if not group:
        return True

    # 章节标题始终开始新段落（标题吸收下方内容，但不合并到上一个段落）
    # 同时检查：严格正则匹配 或 文档样式标记为标题且内容匹配编号模式
    if is_section_heading(elem.content):
        return True
    if elem.is_title and is_heading_by_pattern(elem.content):
        return True
    # 文档样式标记为标题 → 始终触发新边界（处理无编号标题）
    if elem.is_title:
        return True

    last = group[-1]

    # 跨页判断
    if elem.page != last.page:
        # 当前 group 以章节标题开头 → 放宽续接条件，标题内容应保持完整
        first = group[0]
        if (
            is_section_heading(first.content)
            and page_sizes
            and not elem.is_table
            and elem.bbox[1] < page_sizes.get(elem.page, (0, 9999))[1] * 0.40
        ):
            return False
        # 常规跨页续接
        return not (
            page_sizes and not elem.is_table and not last.is_table and _is_page_continuation(last, elem, page_sizes)
        )

    # 垂直间距判断
    gap = _calculate_vertical_gap(last, elem)
    if gap > vertical_gap_threshold:
        # 前一个元素是标题 → 不拆分，标题吸收下方内容
        return not is_heading_element(last)

    # 首行缩进 + 段末短行检测（需要正文边距信息且均为文本元素）
    if body_margins and not elem.is_table and not last.is_table and not is_heading_element(elem):
        column_margins = body_margins.get(elem.page)
        if column_margins is not None:
            margins = _find_column_margin(column_margins, elem)
            if margins is not None:
                body_left, body_right = margins
                # 规则 5：首行缩进 — 当前元素 x0 显著右偏于正文左边距
                if elem.bbox[0] > body_left + indent_threshold and abs(last.bbox[0] - body_left) < indent_threshold:
                    return True
                # 规则 6：段末短行 — 前一个元素 x1 显著小于正文右边界
                if last.bbox[2] < body_right - right_margin_threshold:
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

    # 检测零 bbox 元素（TXT/Markdown/CSV），使用 fallback 模式
    use_fallback = _is_zero_bbox_elements(elements)

    if use_fallback:
        return _group_by_fallback(elements, max_chunk_size, doc_id)

    # 自适应行距检测：如果典型行距大于配置阈值，自动提高阈值
    effective_gap_threshold = vertical_gap_threshold
    dominant_gap = _detect_dominant_line_spacing(elements)
    if dominant_gap and dominant_gap > vertical_gap_threshold:
        effective_gap_threshold = dominant_gap + 2.0
        logger.info("自适应行距: 典型行距=%.1fpx, 有效阈值=%.1fpx", dominant_gap, effective_gap_threshold)

    # 首行缩进检测：统计每页正文左边距
    body_margins = _detect_page_body_margins(elements)

    # 阶段 1：按段落边界分组
    paragraphs: list[list[ParsedElement]] = []
    current_group: list[ParsedElement] = []

    for elem in elements:
        if is_new_paragraph_boundary(elem, current_group, effective_gap_threshold, page_sizes, body_margins):
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


def _group_by_fallback(
    elements: list[ParsedElement],
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    doc_id: str = "",
) -> list[tuple[list[ParsedElement], str]]:
    """零 bbox 元素的 fallback 分组逻辑。

    使用 elem_type 变化、paragraph_break 标记、heading_level 阈值判断边界。
    """
    paragraphs: list[list[ParsedElement]] = []
    current_group: list[ParsedElement] = []

    for elem in elements:
        if is_new_paragraph_boundary_fallback(elem, current_group):
            if current_group:
                paragraphs.append(current_group)
            current_group = [elem]
        else:
            current_group.append(elem)

    if current_group:
        paragraphs.append(current_group)

    logger.info(
        "Fallback 段落边界识别: %d 个元素 → %d 个段落组",
        len(elements),
        len(paragraphs),
    )

    # 孤立标题合并
    paragraphs = _merge_heading_only_groups(paragraphs)

    # 超长分组拆分
    if max_chunk_size > 0:
        result = _split_oversized_groups(paragraphs, max_chunk_size, doc_id)
        logger.info("Fallback 超长拆分后: %d 个段落组", len(result))
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
            has_content = any(not is_section_heading(e.content) and not e.is_image for e in group if e.content.strip())
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


def _detect_dominant_line_spacing(elements: list[ParsedElement]) -> float | None:
    """检测文档中同页相邻文本元素之间的典型垂直间距（众数）。"""
    gap_counter: Counter[float] = Counter()
    for i in range(1, len(elements)):
        prev, curr = elements[i - 1], elements[i]
        if prev.page != curr.page:
            continue
        if prev.is_table or curr.is_table or prev.is_image or curr.is_image:
            continue
        gap = curr.bbox[1] - prev.bbox[3]
        if gap > 0:
            rounded = round(gap * 2) / 2
            gap_counter[rounded] += 1

    if not gap_counter:
        return None
    return gap_counter.most_common(1)[0][0]


def _detect_page_body_margins(elements: list[ParsedElement]) -> dict[int, list[tuple[float, float]]]:
    """检测每页正文文本的左右边距（按文本长度加权的 x0/x1 众数）。

    支持双栏排版：自动检测 x0 聚类，分栏计算各自的边距。
    返回 {page: [(left, right), ...]}，单栏页面为单元素列表。
    """
    page_elements: dict[int, list[ParsedElement]] = {}
    for e in elements:
        if not e.is_table and not e.is_image and e.elem_type != "title":
            page_elements.setdefault(e.page, []).append(e)

    margins: dict[int, list[tuple[float, float]]] = {}
    for page, elems in page_elements.items():
        if not elems:
            continue

        # 按 x0 聚类检测分栏
        columns = _cluster_by_x0(elems)

        if len(columns) <= 1:
            margins[page] = [_compute_column_margin(elems)]
        else:
            margins[page] = [_compute_column_margin(col) for col in columns]

    return margins


def _find_column_margin(
    column_margins: list[tuple[float, float]], elem: ParsedElement
) -> tuple[float, float] | None:
    """从多栏边距列表中找到元素所属栏的边距。"""
    if not column_margins:
        return None
    if len(column_margins) == 1:
        return column_margins[0]
    best = min(column_margins, key=lambda m: abs(elem.bbox[0] - m[0]))
    return best


def _cluster_by_x0(elems: list[ParsedElement], gap: float = 100.0) -> list[list[ParsedElement]]:
    """按 x0 聚类元素，检测双栏排版。gap 为栏间最小间距阈值。"""
    if not elems:
        return [[]]

    # 用 x0 的分箱来检测聚类：将 x0 四舍五入到 20px 精度
    bucket_elems: dict[int, list[ParsedElement]] = {}
    for e in elems:
        key = round(e.bbox[0] / 20) * 20
        bucket_elems.setdefault(key, []).append(e)

    sorted_keys = sorted(bucket_elems.keys())

    # 按间距切分
    clusters: list[list[int]] = []
    current = [sorted_keys[0]]
    for i in range(1, len(sorted_keys)):
        if sorted_keys[i] - current[-1] > gap:
            clusters.append(current)
            current = [sorted_keys[i]]
        else:
            current.append(sorted_keys[i])
    clusters.append(current)

    # 将小簇（< 3 个元素）合并到最近的簇
    if len(clusters) > 2:
        merged: list[list[int]] = []
        small_clusters: list[tuple[int, list[int]]] = []  # (center_x, keys)
        big_clusters: list[tuple[int, list[int]]] = []
        for c in clusters:
            center = sum(c) / len(c)
            total_elems = sum(len(bucket_elems[k]) for k in c)
            if total_elems < 3:
                small_clusters.append((center, c))
            else:
                big_clusters.append((center, c))

        if big_clusters:
            for center, c in small_clusters:
                nearest = min(big_clusters, key=lambda bc: abs(bc[0] - center))
                nearest[1].extend(c)
            merged = [c for _, c in big_clusters]
            # 重新按 center 排序
            merged.sort(key=lambda c: sum(c) / len(c))
            clusters = merged

    # 映射回元素
    return [[e for k in cluster for e in bucket_elems[k]] for cluster in clusters]


def _compute_column_margin(elems: list[ParsedElement]) -> tuple[float, float]:
    """计算一组元素的正文左右边距。"""
    x0_counter: Counter[float] = Counter()
    x1_counter: Counter[float] = Counter()
    for e in elems:
        weight = max(len(e.content), 1)
        x0_counter[round(e.bbox[0])] += weight
        x1_counter[round(e.bbox[2])] += weight
    body_left = x0_counter.most_common(1)[0][0]
    body_right = x1_counter.most_common(1)[0][0]
    return (body_left, body_right)


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
    return not elem.bbox[1] > height_elem * 0.15


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
