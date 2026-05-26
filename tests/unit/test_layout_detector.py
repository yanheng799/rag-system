"""排版检测测试 — layout_detector 模块"""

import fitz
import pytest

from src.ingestion.chunkers.layout_detector import (
    detect_header_footer_zones,
    detect_page_layout,
    detect_toc_pages,
    is_in_header_footer,
    reorder_elements_for_layout,
)
from src.ingestion.parsers.base import ParsedElement


class TestLayoutDetector:
    """排版检测 — 使用真实 PDF 文件"""

    def test_tower_detail_is_double(self):
        """塔位明细表应识别为双栏"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        for pn in [2, 3, 4]:
            assert detect_page_layout(doc[pn]) == "double", f"Page {pn} should be double"
        doc.close()

    def test_design_doc_is_single(self):
        """设计交底文件目录页应为单栏"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        for pn in [3, 4, 5, 6, 7]:
            assert detect_page_layout(doc[pn]) == "single", f"Page {pn} should be single"
        doc.close()

    def test_cover_page_is_single(self):
        """封面页（词数不足）应为单栏"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        assert detect_page_layout(doc[0]) == "single"
        doc.close()

    def test_reorder_double_column(self):
        """双栏元素应按左列→右列重排"""
        elements = [
            ParsedElement(elem_type="text", content="右1", page=0, bbox=(600, 100, 800, 110)),
            ParsedElement(elem_type="text", content="左1", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="text", content="右2", page=0, bbox=(600, 200, 800, 210)),
            ParsedElement(elem_type="text", content="左2", page=0, bbox=(100, 200, 300, 210)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        assert [e.content for e in result] == ["左1", "左2", "右1", "右2"]

    def test_reorder_single_column_unchanged(self):
        """单栏模式下不重排"""
        elements = [
            ParsedElement(elem_type="text", content="A", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="text", content="B", page=0, bbox=(100, 200, 300, 210)),
        ]
        result = reorder_elements_for_layout(elements, 595, "single")
        assert result == elements


class TestHeaderFooterDetection:
    """页眉页脚检测"""

    def test_tower_detail_has_header(self):
        """塔位明细表应检测到页眉"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) > 0
        assert any(z[0] < 50 for z in zones), f"No header zone found in {zones}"

    def test_tower_detail_has_footer(self):
        """塔位明细表应检测到页脚"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert any(z[0] > 700 for z in zones), f"No footer zone found in {zones}"

    def test_tower_detail_header_filtered(self):
        """解析后不应包含页眉内容"""
        from src.ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse("tests/data/塔位明细表.pdf")
        assert not any("千伏直流输电线路工程" in e.content for e in elements)

    def test_design_doc_no_false_positives(self):
        """设计交底文件不应误检页眉页脚"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        zones = detect_header_footer_zones(doc)
        doc.close()
        assert len(zones) == 0

    def test_is_in_header_footer(self):
        zones = [(28, 44, frozenset({"页眉文本"})), (762, 778, frozenset({"页脚文本"}))]
        assert is_in_header_footer((100, 28, 300, 44), zones, text="页眉文本") is True
        assert is_in_header_footer((100, 762, 300, 778), zones, text="页脚文本") is True
        assert is_in_header_footer((100, 100, 300, 120), zones, text="正文内容") is False
        # 文本不匹配 → 即使 y 在 zone 内也不应误杀
        assert is_in_header_footer((100, 28, 300, 44), zones, text="章节标题") is False


class TestFullWidthTable:
    """全宽表格在双栏重排中的处理"""

    def test_full_width_table_not_split(self):
        """全宽表格应保持完整，不被分入左/右列"""
        elements = [
            ParsedElement(elem_type="text", content="左1", page=0, bbox=(100, 100, 300, 110)),
            ParsedElement(elem_type="table", content="表格", page=0, bbox=(50, 120, 1140, 200)),
            ParsedElement(elem_type="text", content="右1", page=0, bbox=(600, 100, 800, 110)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        assert len(result) == 3
        table_idx = next(i for i, e in enumerate(result) if e.content == "表格")
        left_idx = next(i for i, e in enumerate(result) if e.content == "左1")
        right_idx = next(i for i, e in enumerate(result) if e.content == "右1")
        assert table_idx > left_idx
        assert table_idx > right_idx

    def test_narrow_table_goes_to_column(self):
        """窄表格应正常分入左/右列"""
        elements = [
            ParsedElement(elem_type="table", content="窄表", page=0, bbox=(100, 100, 400, 150)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        assert len(result) == 1

    def test_full_width_between_columns(self):
        """全宽元素在左右列元素之间按 y 排序"""
        elements = [
            ParsedElement(elem_type="text", content="左上", page=0, bbox=(100, 50, 300, 60)),
            ParsedElement(elem_type="text", content="右上", page=0, bbox=(600, 50, 800, 60)),
            ParsedElement(elem_type="table", content="全宽表", page=0, bbox=(50, 100, 1140, 200)),
            ParsedElement(elem_type="text", content="左下", page=0, bbox=(100, 250, 300, 260)),
            ParsedElement(elem_type="text", content="右下", page=0, bbox=(600, 250, 800, 260)),
        ]
        result = reorder_elements_for_layout(elements, 1191, "double")
        contents = [e.content for e in result]
        fw_idx = contents.index("全宽表")
        assert contents.index("左上") < fw_idx
        assert contents.index("右上") < fw_idx
        assert contents.index("左下") > fw_idx
        assert contents.index("右下") > fw_idx


class TestTocDetection:
    """目录页检测"""

    def test_toc_pages_in_project_plan(self):
        """设计交底文件目录检测不崩溃"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        assert isinstance(toc_pages, set)

    def test_no_toc_in_tower_detail(self):
        """塔位明细表不应检测到目录页"""
        doc = fitz.open("tests/data/塔位明细表.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        assert len(toc_pages) == 0

    def test_no_toc_in_design_doc(self):
        """设计交底文件正文页不应被误判为目录页"""
        doc = fitz.open("tests/data/设计交底文件.pdf")
        toc_pages = detect_toc_pages(doc)
        doc.close()
        for pn in range(3, 10):
            assert pn not in toc_pages, f"Page {pn} should not be detected as TOC"
