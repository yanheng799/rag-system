"""集成测试：段落分组 + Chunk 组装 + 描述生成"""

import os

import pytest

from src.ingestion.chunkers.chunk_assembler import ChunkBuilder
from src.ingestion.chunkers.paragraph_grouper import detect_chunk_type, group_elements_by_paragraph
from src.ingestion.parsers.pdf_parser import PDFParser
from src.ingestion.parsers.registry import ParserRegistry, init_parsers
from src.ingestion.parsers.word_parser import WordParser
from src.ingestion.table_processor.describer import TableDescriber

TEST_FILES_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class TestParagraphGroupingIntegration:
    """段落边界识别集成测试"""

    def test_group_pdf_elements(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        assert len(paragraphs) > 0
        # 每个段落至少 1 个元素
        for group, _gid in paragraphs:
            assert len(group) >= 1

    def test_group_word_elements(self):
        parser = WordParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "哈重项目管理实施规划.docx"))
        paragraphs = group_elements_by_paragraph(elements[:100])
        assert len(paragraphs) > 0

    def test_mixed_paragraphs_exist_in_pdf(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        types = {detect_chunk_type(g) for g, _ in paragraphs}
        # 至少应有 text 类型
        assert "text" in types


class TestChunkBuilderIntegration:
    """ChunkBuilder 集成测试（无截图服务）"""

    def test_build_text_chunk(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        # 取一个纯文字段落
        for group, _gid in paragraphs:
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
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        for group, _gid in paragraphs:
            if detect_chunk_type(group) == "mixed":
                has_table_elem = any(e.is_table for e in group)
                has_text_elem = any(not e.is_table and not e.is_image for e in group)
                if not has_table_elem or not has_text_elem:
                    continue
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
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        paragraphs = group_elements_by_paragraph(elements)
        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())

        for group, _gid in paragraphs:
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
        from src.ingestion.parsers.excel_parser import ExcelParser

        parser = ExcelParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "典型塔型吊装工况表.xlsx"))
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

    def test_table_screenshot_index_unique_across_chunks(self):
        """跨分块的表(含跨页续表)截图文件名应全局唯一，避免同页覆盖。

        复现场景：表A 主表在 page4、续页在 page5；表B 主表也在 page5、续页在 page6。
        若 table_index 都从 0 开始，表A 续页与表B 主表会落到同名 p5_t0 互相覆盖。
        pipeline 通过 table_index_offset 让各表 index 全局递增即可避免。
        """
        from src.ingestion.parsers.base import ParsedElement

        class _MockShot:
            def __init__(self):
                self.keys = []  # (page, table_index) 决定文件名

            def capture_pdf_table(self, *, org_id, pdf_path, page_num, bbox, doc_id, table_index, **kw):
                self.keys.append((page_num, table_index))
                return f"oss://mock/p{page_num}_t{table_index}.png"

        mock = _MockShot()
        builder = ChunkBuilder(screenshot=mock, describer=TableDescriber())

        table_a = ParsedElement(
            elem_type="table",
            content="| a |\n|---|\n| 1 |",
            page=4,
            bbox=(50, 400, 500, 800),
            raw={"_merged_pages": [{"page": 5, "bbox": (50, 56, 500, 175)}]},
        )
        table_b = ParsedElement(
            elem_type="table",
            content="| b |\n|---|\n| 2 |",
            page=5,
            bbox=(50, 226, 500, 800),
            raw={"_merged_pages": [{"page": 6, "bbox": (50, 56, 500, 337)}]},
        )

        # 模拟 pipeline：两个分块各含一张表，offset 递增
        builder.build(
            elements=[table_a],
            doc_id="d",
            source="s",
            page=4,
            chunk_index=0,
            pdf_path="x.pdf",
            table_index_offset=0,
        )
        builder.build(
            elements=[table_b],
            doc_id="d",
            source="s",
            page=5,
            chunk_index=0,
            pdf_path="x.pdf",
            table_index_offset=1,
        )

        # 文件名键 (page, index) 必须全部唯一
        assert len(mock.keys) == len(set(mock.keys)), f"截图文件名冲突: {mock.keys}"
        # 表A续页(p5,t0) 与 表B主表(p5,t1) 不再同名
        assert (5, 0) in mock.keys  # 表A 续页
        assert (5, 1) in mock.keys  # 表B 主表


class TestParserRegistryIntegration:
    """Parser 注册表集成测试"""

    def test_init_and_dispatch(self):
        init_parsers()
        pdf_parser = ParserRegistry.get("pdf")
        assert isinstance(pdf_parser, PDFParser)

    def test_parse_via_registry(self):
        init_parsers()
        parser = ParserRegistry.get_for_file("test.pdf")
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        assert len(elements) > 0


class TestDescriberIntegration:
    """表格描述器集成测试"""

    def test_describe_pdf_table(self):
        parser = PDFParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "杆塔明细表.pdf"))
        tables = [e for e in elements if e.elem_type == "table"]
        assert len(tables) > 0

        describer = TableDescriber()
        description = describer.describe(tables[0])
        assert len(description) > 0

    def test_describe_excel_table(self):
        from src.ingestion.parsers.excel_parser import ExcelParser

        parser = ExcelParser()
        elements = parser.parse(os.path.join(TEST_FILES_DIR, "典型塔型吊装工况表.xlsx"))
        assert len(elements) > 0

        describer = TableDescriber()
        description = describer.describe(elements[0])
        assert len(description) > 0
        assert "工作表" in description or "表头" in description
