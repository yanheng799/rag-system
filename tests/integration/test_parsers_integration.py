"""集成测试：使用真实文档验证解析器"""

import os
import pytest

from ingestion.parsers.pdf_parser import PDFParser
from ingestion.parsers.word_parser import WordParser
from ingestion.parsers.excel_parser import ExcelParser

TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "test-files")


def pdf_path():
    return os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf")


def word_path():
    return os.path.join(TEST_FILES_DIR, "1.哈重项目管理实施规划-1.docx")


def excel_path():
    return os.path.join(TEST_FILES_DIR, "附表2 典型塔型吊装工况表.xlsx")


class TestPDFParserIntegration:
    """PDF 解析器集成测试"""

    def test_parse_real_pdf(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        assert len(elements) > 0, "PDF 应解析出元素"

    def test_pdf_has_text_elements(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        text_elements = [e for e in elements if e.elem_type in ("text", "title")]
        assert len(text_elements) > 0, "PDF 应包含文字元素"

    def test_pdf_has_table_elements(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        table_elements = [e for e in elements if e.elem_type == "table"]
        assert len(table_elements) > 0, "PDF 应包含表格元素"

    def test_pdf_elements_have_page_numbers(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        pages = {e.page for e in elements}
        assert len(pages) >= 1, "元素应有页码信息"

    def test_pdf_table_has_content(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        tables = [e for e in elements if e.elem_type == "table"]
        for t in tables:
            assert len(t.content) > 0, "表格应有内容"

    def test_pdf_text_elements_have_bbox(self):
        parser = PDFParser()
        elements = parser.parse(pdf_path())
        text_elems = [e for e in elements if e.elem_type == "text"]
        for elem in text_elems[:10]:
            assert len(elem.bbox) == 4, "文字元素应有 bbox 坐标"

    def test_supported_type(self):
        parser = PDFParser()
        assert "pdf" in parser.supported_types()


class TestWordParserIntegration:
    """Word 解析器集成测试"""

    def test_parse_real_docx(self):
        parser = WordParser()
        elements = parser.parse(word_path())
        assert len(elements) > 0, "Word 应解析出元素"

    def test_docx_has_text_elements(self):
        parser = WordParser()
        elements = parser.parse(word_path())
        text_elements = [e for e in elements if e.elem_type == "text"]
        assert len(text_elements) > 0

    def test_docx_has_table_elements(self):
        parser = WordParser()
        elements = parser.parse(word_path())
        table_elements = [e for e in elements if e.elem_type == "table"]
        assert len(table_elements) > 0, "Word 应包含表格元素"

    def test_docx_elements_have_content(self):
        parser = WordParser()
        elements = parser.parse(word_path())
        for elem in elements[:20]:
            assert len(elem.content.strip()) > 0, "元素内容不应为空"

    def test_docx_preserves_order(self):
        parser = WordParser()
        elements = parser.parse(word_path())
        # 检查位置递增
        positions = [e.bbox[1] for e in elements]
        for i in range(1, min(10, len(positions))):
            assert positions[i] >= positions[i - 1], "元素应保持文档顺序"


class TestExcelParserIntegration:
    """Excel 解析器集成测试"""

    def test_parse_real_xlsx(self):
        parser = ExcelParser()
        elements = parser.parse(excel_path())
        assert len(elements) > 0, "Excel 应解析出元素"

    def test_xlsx_all_table_type(self):
        parser = ExcelParser()
        elements = parser.parse(excel_path())
        for elem in elements:
            assert elem.elem_type == "table", "Excel 元素应为 table 类型"

    def test_xlsx_content_has_headers(self):
        parser = ExcelParser()
        elements = parser.parse(excel_path())
        assert len(elements) > 0
        # 内容应包含"表头"关键字
        assert "表头" in elements[0].content

    def test_xlsx_page_is_sheet_index(self):
        parser = ExcelParser()
        elements = parser.parse(excel_path())
        pages = {e.page for e in elements}
        assert min(pages) >= 1, "Excel page 应为 sheet index（从 1 开始）"
