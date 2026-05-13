"""Parser 注册表测试"""

import pytest

from src.ingestion.parsers.base import UnsupportedFileTypeError
from src.ingestion.parsers.excel_parser import ExcelParser
from src.ingestion.parsers.pdf_parser import PDFParser
from src.ingestion.parsers.registry import ParserRegistry, init_parsers
from src.ingestion.parsers.word_parser import WordParser


class TestParserRegistry:
    def setup_method(self):
        # 每次测试前清空注册表
        ParserRegistry._parsers.clear()
        init_parsers()

    def test_supported_types(self):
        types = ParserRegistry.supported_types()
        assert "pdf" in types
        assert "docx" in types
        assert "xlsx" in types

    def test_get_pdf_parser(self):
        parser = ParserRegistry.get("pdf")
        assert isinstance(parser, PDFParser)

    def test_get_word_parser(self):
        parser = ParserRegistry.get("docx")
        assert isinstance(parser, WordParser)

    def test_get_excel_parser(self):
        parser = ParserRegistry.get("xlsx")
        assert isinstance(parser, ExcelParser)

    def test_unsupported_type(self):
        with pytest.raises(UnsupportedFileTypeError):
            ParserRegistry.get("html")

    def test_get_for_file(self):
        parser = ParserRegistry.get_for_file("test.pdf")
        assert isinstance(parser, PDFParser)

    def test_dot_prefix(self):
        parser = ParserRegistry.get(".pdf")
        assert isinstance(parser, PDFParser)
