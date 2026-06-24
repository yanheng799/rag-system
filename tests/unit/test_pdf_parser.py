"""PDF 解析器单元测试 — pdf_parser 模块"""

from src.ingestion.parsers.pdf_parser import PDFParser


def _text_block(bbox: tuple, size: float, text: str) -> dict:
    """构造 pymupdf dict 风格的文本块"""
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"bbox": bbox, "spans": [{"text": text, "size": size, "font": ""}]}],
    }


class TestDetectBodyFontSize:
    """正文基准字号统计"""

    def test_excludes_table_text(self):
        """表格单元格的小字号不应污染正文基准字号。

        表格常用比正文更小的字号，若纳入统计，表格字符多会让正文基准偏小，
        真正的正文反而被按"字号偏大"误判为标题。
        """
        parser = PDFParser()
        table_block = _text_block((50, 100, 500, 300), size=10.4, text="表" * 80)
        body_block = _text_block((50, 400, 500, 480), size=14.1, text="正" * 25)

        # 不排除表格 → 基准被表格小字号(10.4)主导
        with_table = parser._detect_body_font_size([table_block, body_block], 842, None, None)
        assert with_table == 10.4

        # 排除表格区域 → 基准回归正文(14.1)
        excluded = parser._detect_body_font_size([table_block, body_block], 842, None, [(50, 100, 500, 300)])
        assert excluded == 14.1

    def test_no_table_bboxes_unchanged(self):
        """无表格时行为不变"""
        parser = PDFParser()
        body_block = _text_block((50, 400, 500, 480), size=12.0, text="正文" * 10)
        assert parser._detect_body_font_size([body_block], 842, None, None) == 12.0
        assert parser._detect_body_font_size([body_block], 842, None, []) == 12.0
