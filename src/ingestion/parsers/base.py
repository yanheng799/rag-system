"""文档解析器基类和解析元素定义"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedElement:
    """解析后的文档元素"""

    elem_type: str  # "text" | "table" | "title" | "list_item" | "image"
    content: str  # 文字内容或图片占位文本
    page: int  # 页码（Excel 使用 sheet index）
    bbox: tuple = (0, 0, 0, 0)  # (x0, y0, x1, y1) 坐标
    style: dict = field(default_factory=dict)  # 字体、缩进等样式信息
    raw: Any = None  # 原始对象（备用）

    @property
    def is_table(self) -> bool:
        return self.elem_type == "table"

    @property
    def is_title(self) -> bool:
        return self.elem_type == "title"

    @property
    def is_image(self) -> bool:
        return self.elem_type == "image"


class BaseParser(ABC):
    """文档解析器基类"""

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedElement]:
        """解析文档，返回扁平 Element 列表"""

    @abstractmethod
    def supported_types(self) -> list[str]:
        """返回支持的文件扩展名列表"""


class UnsupportedFileTypeError(Exception):
    """不支持的文件类型"""

    def __init__(self, file_type: str):
        super().__init__(f"不支持的文件类型: {file_type}")
        self.file_type = file_type


class ParseError(Exception):
    """文档解析失败"""

    def __init__(self, file_path: str, detail: str = ""):
        super().__init__(f"文档解析失败: {file_path} - {detail}")
        self.file_path = file_path
        self.detail = detail


def format_rows(headers: list[str], rows: list[list[str]], sheet_name: str = "") -> str:
    """将行列数据格式化为自然语言描述（共享函数）。

    Args:
        headers: 列名列表
        rows: 数据行列表，每行为字符串列表
        sheet_name: 可选的工作表名称前缀

    Returns:
        格式化后的文本，格式如 "工作表: X\\n表头: A | B\\n列A: val1; 列B: val2"
    """
    lines: list[str] = []
    if sheet_name:
        lines.append(f"工作表: {sheet_name}")
    lines.append(f"表头: {' | '.join(headers)}")

    for row in rows:
        parts = []
        for idx, (header, value) in enumerate(zip(headers, row, strict=False)):
            if value.strip():
                col_name = header.strip() if header.strip() else f"列{idx + 1}"
                parts.append(f"{col_name}: {value.strip()}")
        if parts:
            lines.append("; ".join(parts))

    return "\n".join(lines)


def read_text_file(file_path: str) -> str:
    """读取文本文件，自动探测编码。

    级联尝试: utf-8-sig → utf-8 → gbk → latin-1
    utf-8-sig 自动剥离 BOM，gbk 覆盖中文 Windows 常见编码。
    """
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(file_path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, ValueError):
            continue
    raise ParseError(file_path, "无法识别文件编码")
