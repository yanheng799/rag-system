"""分块策略共享工具函数"""

from __future__ import annotations

from src.ingestion.chunkers.heading_patterns import is_heading_by_pattern, is_section_heading
from src.ingestion.parsers.base import ParsedElement


def is_heading_element(elem: ParsedElement) -> bool:
    """判断元素是否为标题（elem_type 或正则匹配）"""
    if elem.is_title:
        return True
    return is_heading_by_pattern(elem.content)


def split_oversized_groups(
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


def merge_small_chunks(
    groups: list[tuple[list[ParsedElement], str]],
    min_chunk_size: int = 50,
) -> list[tuple[list[ParsedElement], str]]:
    """合并过小的分块与相邻分块。

    - 非末尾小组 → 合并到下一个组
    - 末尾小组 → 合并到前一个组
    - 标题组（首元素为标题）合并后标题保持在组首
    """
    if min_chunk_size <= 0 or len(groups) <= 1:
        return groups

    result: list[tuple[list[ParsedElement], str]] = []

    for i, (group, gid) in enumerate(groups):
        group_size = sum(len(e.content) for e in group)

        if group_size < min_chunk_size:
            if i < len(groups) - 1:
                # 合并到下一个组
                groups[i + 1] = (group + groups[i + 1][0], groups[i + 1][1])
            elif result:
                # 末尾小组 → 合并到前一个组
                prev_elems, prev_gid = result.pop()
                result.append((prev_elems + group, prev_gid))
        else:
            result.append((group, gid))

    return result
