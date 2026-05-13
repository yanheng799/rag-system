"""标题正则匹配模块 — 中英文文档标题识别"""

from __future__ import annotations

import re

# 编译后的标题匹配正则（来自 section_patterns.md）
COMPILED_HEADING_PATTERNS: list[re.Pattern] = [
    # 中文章/节/篇/部分
    re.compile(r"^第[一二三四五六七八九十百千\d]+[章节篇部分]\s*.*"),
    # 中文条款
    re.compile(r"^第[一二三四五六七八九十百千\d]+[条款]\s*.*"),
    # 编号标题（如 "3.2 排序算法"、"3、施工要求"）
    re.compile(r"^\d+[\.\、]\s*\S+.*"),
    # 一级编号标题（如 "3 项目管理"）
    re.compile(r"^\d+\s+\S+.*"),
    # 子编号标题（如 "3.2.1 数据采集"）
    re.compile(r"^\d+\.\d+\s+\S+.*"),
    # 英文章节
    re.compile(r"(?i)^chapter\s+\d+[\.:]?\s*.*"),
    # 英文节
    re.compile(r"(?i)^section\s+\d+[\.:]?\s*.*"),
    # 英文部分
    re.compile(r"(?i)^part\s+[IVXLCDM\d]+[\.:]?\s*.*"),
]

# 标题文本最大长度（超长文本不可能是标题）
_MAX_HEADING_LENGTH = 100


def is_heading_by_pattern(text: str) -> bool:
    """通过正则判断文本是否为标题"""
    text = text.strip()
    if not text or len(text) > _MAX_HEADING_LENGTH:
        return False
    return any(pat.match(text) for pat in COMPILED_HEADING_PATTERNS)


def is_heading_combined(text: str, font_size: float, is_bold: bool) -> bool:
    """综合判断：样式（字号/加粗）OR 正则匹配，任一命中即为标题"""
    # 样式判断：字号 >= 14 或 加粗且字号 >= 12
    if font_size >= 14 or (is_bold and font_size >= 12):
        return True
    # 正则判断
    return is_heading_by_pattern(text)


# 章节标题正则 — 仅匹配真正的章节编号格式，排除正文列表项
_SECTION_HEADING_PATTERNS: list[re.Pattern] = [
    # 三级编号: 1.3.1, 2.2.1 等
    re.compile(r"^\d+\.\d+\.\d+\s+\S"),
    # 二级编号: 1.1, 2.3 等
    re.compile(r"^\d+\.\d+\s+\S"),
    # 中文章标题: 一、二、三、等
    re.compile(r"^[一二三四五六七八九十]+、\s*\S"),
    # 第X章/节/篇/部分
    re.compile(r"^第[一二三四五六七八九十百千\d]+[章节篇部分]\s"),
    # 英文章节
    re.compile(r"(?i)^chapter\s+\d+"),
    re.compile(r"(?i)^section\s+\d+"),
    re.compile(r"(?i)^part\s+[IVXLCDM\d]+"),
]

_MAX_SECTION_HEADING_LENGTH = 60


def is_section_heading(text: str) -> bool:
    """判断是否为章节标题（用于分片边界识别）。

    比 is_heading_by_pattern 更严格：只匹配带编号的章节标题格式，
    不匹配 "1、"、"3）" 等列表项，也不匹配纯样式上的加粗文本。
    """
    text = text.strip()
    if not text or len(text) > _MAX_SECTION_HEADING_LENGTH:
        return False
    return any(pat.match(text) for pat in _SECTION_HEADING_PATTERNS)
