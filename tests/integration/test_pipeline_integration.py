"""集成测试：段落分组 + Chunk 组装 + 描述生成"""

import os
import pytest

from ingestion.parsers.pdf_parser import PDFParser
from ingestion.parsers.word_parser import WordParser
from ingestion.parsers.registry import init_parsers, ParserRegistry
from ingestion.chunkers.paragraph_grouper import group_elements_by_paragraph, detect_chunk_type
from ingestion.chunkers.chunk_assembler import ChunkBuilder
from ingestion.table_processor.describer import TableDescriber

TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "test-files")


class TestParagraphGroupingIntegration:
    """段落边界识别集成测试"""

    def test_group_pdf_elements(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        assert len(paragraphs) > 0
        # 每个段落至少 1 个元素
        for group, gid in paragraphs:
            assert len(group) >= 1

    def test_group_word_elements(self):
        parser = WordParser()
        elements = parser.parse(
            os.path.join(TEST_FILES_DIR, "1.哈重项目管理实施规划-1.docx")
        )
        paragraphs = group_elements_by_paragraph(elements[:100])
        assert len(paragraphs) > 0

    def test_mixed_paragraphs_exist_in_pdf(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        types = {detect_chunk_type(g) for g, _ in paragraphs}
        # 至少应有 text 类型
        assert "text" in types


class TestChunkBuilderIntegration:
    """ChunkBuilder 集成测试（无截图服务）"""

    def test_build_text_chunk(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        # 取一个纯文字段落
        for group, gid in paragraphs:
            if detect_chunk_type(group) == "text":
                chunk = builder.build(
                    elements=group,
                    doc_id="test_doc",
                    source="test.pdf",
                    page=group[0].page,
                    chunk_index=0,
                )
                assert chunk.metadata.chunk_id == f"test_doc_p{group[0].page}_c0"
                assert chunk.metadata.chunk_type == "text"
                assert len(chunk.full_text) > 0
                assert len(chunk.elements) > 0
                return

        pytest.skip("PDF 中没有纯文字段落")

    def test_build_mixed_chunk(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        for group, gid in paragraphs:
            if detect_chunk_type(group) == "mixed":
                chunk = builder.build(
                    elements=group,
                    doc_id="test_doc",
                    source="test.pdf",
                    page=group[0].page,
                    chunk_index=0,
                )
                assert chunk.metadata.chunk_type == "mixed"
                assert any(e.type == "table" for e in chunk.elements)
                assert any(e.type == "text" for e in chunk.elements)
                return

    def test_build_table_chunk(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        for group, gid in paragraphs:
            if detect_chunk_type(group) == "table":
                chunk = builder.build(
                    elements=group,
                    doc_id="test_doc",
                    source="test.pdf",
                    page=group[0].page,
                    chunk_index=0,
                )
                assert chunk.metadata.chunk_type == "table"
                assert all(e.type == "table" for e in chunk.elements)
                return

    def test_build_excel_chunks(self):
        from ingestion.parsers.excel_parser import ExcelParser

        parser = ExcelParser()
        elements = parser.parse(
            os.path.join(TEST_FILES_DIR, "附表2 典型塔型吊装工况表.xlsx")
        )
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        assert len(paragraphs) > 0
        chunk = builder.build(
            elements=paragraphs[0][0],
            doc_id="test_excel",
            source="test.xlsx",
            page=paragraphs[0][0][0].page,
            chunk_index=0,
        )
        assert len(chunk.full_text) > 0
        assert chunk.metadata.chunk_type == "table"


class TestParserRegistryIntegration:
    """Parser 注册表集成测试"""

    def test_init_and_dispatch(self):
        init_parsers()
        pdf_parser = ParserRegistry.get("pdf")
        assert isinstance(pdf_parser, PDFParser)

    def test_parse_via_registry(self):
        init_parsers()
        parser = ParserRegistry.get_for_file("test.pdf")
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        assert len(elements) > 0


class TestDescriberIntegration:
    """表格描述器集成测试"""

    def test_describe_pdf_table(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "2.杆塔明细表.pdf"))
        tables = [e for e in elements if e.elem_type == "table"]
        assert len(tables) > 0

        describer = TableDescriber()
        description = describer.describe(tables[0])
        assert len(description) > 0

    def test_describe_excel_table(self):
        from ingestion.parsers.excel_parser import ExcelParser

        parser = ExcelParser()
        elements = parser.parse(
            os.path.join(TEST_FILES_DIR, "附表2 典型塔型吊装工况表.xlsx")
        )
        assert len(elements) > 0

        describer = TableDescriber()
        description = describer.describe(elements[0])
        assert len(description) > 0
        assert "工作表" in description or "表头" in description
