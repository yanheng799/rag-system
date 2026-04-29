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
