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
