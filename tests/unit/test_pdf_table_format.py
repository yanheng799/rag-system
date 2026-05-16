"""PDF 表格 Markdown 格式 + 目录过滤测试"""

from src.ingestion.parsers.base import ParsedElement


class TestTableMarkdownFormat:
    """表格 Markdown 格式 — 使用 PDFParser 和 TableDescriber"""

    def test_pdf_table_has_separator(self):
        """PDF 表格应包含 Markdown 分隔行 |---|"""
        from src.ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        tables = [e for e in elements if e.is_table]
        assert len(tables) > 0
        for t in tables:
            assert "---" in t.content, f"Table missing separator: {t.content[:60]}"

    def test_pdf_table_rows_start_with_pipe(self):
        """PDF 表格数据行应以 | 开头"""
        from src.ingestion.parsers.pdf_parser import PDFParser

        parser = PDFParser()
        elements = parser.parse("test-files/2.351-SA06911S-D0102 第6施工标段塔位明细表.pdf")
        tables = [e for e in elements if e.is_table]
        for t in tables[:5]:
            lines = t.content.strip().split("\n")
            for line in lines[:3]:
                assert line.startswith("|"), f"Not markdown: {line[:60]}"

    def test_describer_passes_markdown_through(self):
        """TableDescriber 应透传 Markdown 内容"""
        from src.ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        md = "| 姓名 | 年龄 |\n|---|---|\n| 张三 | 25 |"
        elem = ParsedElement(elem_type="table", content=md, page=0)
        assert describer.describe(elem) == md

    def test_describer_passes_excel_format(self):
        """TableDescriber 应透传 Excel 格式"""
        from src.ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        excel = "工作表: Sheet1\n表头: A | B\nA: 1; B: 2"
        elem = ParsedElement(elem_type="table", content=excel, page=0)
        assert describer.describe(elem) == excel

    def test_describer_empty_content(self):
        """TableDescriber 处理空内容"""
        from src.ingestion.table_processor.describer import TableDescriber

        describer = TableDescriber()
        elem = ParsedElement(elem_type="table", content="", page=0)
        assert describer.describe(elem) == ""


class TestTocFiltered:
    """目录内容过滤 — 使用 PDFParser"""

    def test_toc_content_filtered_in_parse(self):
        """解析后目录页内容应被过滤"""
        from src.ingestion.parsers.pdf_parser import PDFParser
        import re

        parser = PDFParser()
        elements = parser.parse("test-files/10.设计交底文件.pdf")
        toc_lines = [e for e in elements if not e.is_table and re.search(r"\.{50,}", e.content)]
        assert len(toc_lines) == 0, f"Found TOC content: {[e.content[:60] for e in toc_lines[:3]]}"
