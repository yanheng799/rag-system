"""测试 ZB-2YD-40-12-480 落地双摇臂抱杆使用说明书.pdf 的解析流程"""

import logging
import os
import sys

import pytest

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.parsers.pdf_parser import PDFParser
from ingestion.chunkers.paragraph_grouper import (
    detect_chunk_type,
    group_elements_by_paragraph,
)
from ingestion.chunkers.chunk_assembler import ChunkBuilder
from ingestion.table_processor.describer import TableDescriber
from config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TEST_FILE = os.path.join(
    os.path.dirname(__file__), "..", "test-files",
    "ZB-2YD-40-12-480（700截面）落地双摇臂抱杆使用说明书.pdf",
)


class TestZB2YDPdf:
    """ZB-2YD 抱杆使用说明书 PDF 解析测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        assert os.path.exists(TEST_FILE), f"测试文件不存在: {TEST_FILE}"

    # ──── 第一步：PDF 解析 ────

    def test_01_parse_pdf(self):
        """验证 PDF 能成功解析出元素"""
        parser = PDFParser(extract_images=True)
        elements = parser.parse(TEST_FILE)
        self.__class__.elements = elements

        logger.info("=== 解析结果 ===")
        logger.info("总元素数: %d", len(elements))

        # 按类型统计
        type_counts = {}
        for e in elements:
            type_counts[e.elem_type] = type_counts.get(e.elem_type, 0) + 1
        for t, c in sorted(type_counts.items()):
            logger.info("  %s: %d", t, c)

        # 按页码统计
        page_counts = {}
        for e in elements:
            page_counts[e.page] = page_counts.get(e.page, 0) + 1
        logger.info("页码分布: %s", dict(sorted(page_counts.items())))

        assert len(elements) > 0, "PDF 应解析出元素"

    # ──── 第二步：元素内容检查 ────

    def test_02_element_types(self):
        """验证解析出的元素类型分布"""
        parser = PDFParser(extract_images=True)
        elements = parser.parse(TEST_FILE)

        type_counts = {}
        for e in elements:
            type_counts[e.elem_type] = type_counts.get(e.elem_type, 0) + 1

        logger.info("元素类型分布: %s", type_counts)
        assert "text" in type_counts, "应有文本元素"

    def test_03_table_content(self):
        """验证表格元素有内容"""
        parser = PDFParser()
        elements = parser.parse(TEST_FILE)
        tables = [e for e in elements if e.elem_type == "table"]

        logger.info("表格数量: %d", len(tables))
        for i, t in enumerate(tables[:5]):
            logger.info("表格[%d] (页%d): %s", i, t.page, t.content[:200])

        assert len(tables) > 0, "应有表格元素"
        for t in tables:
            assert len(t.content.strip()) > 0, "表格内容不应为空"

    def test_04_title_detection(self):
        """验证标题检测"""
        parser = PDFParser()
        elements = parser.parse(TEST_FILE)
        titles = [e for e in elements if e.elem_type == "title"]

        logger.info("标题数量: %d", len(titles))
        for t in titles[:10]:
            logger.info("  标题(页%d): %s", t.page, t.content[:80])

        assert len(titles) > 0, "应检测到标题"

    # ──── 第三步：段落边界识别 ────

    def test_05_paragraph_grouping(self):
        """验证段落边界识别"""
        parser = PDFParser()
        elements = parser.parse(TEST_FILE)

        # 获取 page_sizes（供跨页判断使用）
        import fitz
        pdf_doc = fitz.open(TEST_FILE)
        page_sizes = {pn: (pdf_doc[pn].rect.width, pdf_doc[pn].rect.height) for pn in range(len(pdf_doc))}
        pdf_doc.close()

        paragraphs = group_elements_by_paragraph(
            elements,
            vertical_gap_threshold=settings.chunk_vertical_gap,
            max_chunk_size=settings.chunk_max_size,
            page_sizes=page_sizes,
        )

        logger.info("=== 段落分组 ===")
        logger.info("段落组数: %d", len(paragraphs))

        # 按类型统计
        type_counts = {}
        for g in paragraphs:
            ct = detect_chunk_type(g)
            type_counts[ct] = type_counts.get(ct, 0) + 1
        for t, c in sorted(type_counts.items()):
            logger.info("  %s: %d", t, c)

        assert len(paragraphs) > 0, "应有段落组"

    # ──── 第四步：Chunk 组装 ────

    def test_06_chunk_assembly(self):
        """验证 MixedChunk 组装"""
        parser = PDFParser()
        elements = parser.parse(TEST_FILE)

        import fitz
        pdf_doc = fitz.open(TEST_FILE)
        page_sizes = {pn: (pdf_doc[pn].rect.width, pdf_doc[pn].rect.height) for pn in range(len(pdf_doc))}
        pdf_doc.close()

        paragraphs = group_elements_by_paragraph(
            elements,
            vertical_gap_threshold=settings.chunk_vertical_gap,
            max_chunk_size=settings.chunk_max_size,
            page_sizes=page_sizes,
        )

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd"
        chunks = []

        page_chunk_counters: dict[int, int] = {}
        for para_group in paragraphs:
            page = para_group[0].page if para_group else 0
            chunk_index = page_chunk_counters.get(page, 0)
            page_chunk_counters[page] = chunk_index + 1

            chunk = builder.build(
                elements=para_group,
                doc_id=doc_id,
                source=os.path.basename(TEST_FILE),
                page=page,
                chunk_index=chunk_index,
                pdf_path=TEST_FILE,
            )
            chunks.append(chunk)

        logger.info("=== MixedChunk 组装 ===")
        logger.info("总 chunk 数: %d", len(chunks))

        # 按类型统计
        type_counts = {}
        for c in chunks:
            type_counts[c.metadata.chunk_type] = type_counts.get(c.metadata.chunk_type, 0) + 1
        for t, c in sorted(type_counts.items()):
            logger.info("  %s: %d", t, c)

        # 字符数分布
        char_counts = [c.metadata.char_count for c in chunks]
        if char_counts:
            logger.info(
                "字符数: min=%d, max=%d, avg=%.0f",
                min(char_counts), max(char_counts), sum(char_counts) / len(char_counts),
            )

        # 输出部分 chunk 内容预览
        for i, chunk in enumerate(chunks[:10]):
            logger.info(
                "Chunk[%d] %s (%d字): %s",
                i, chunk.metadata.chunk_id, chunk.metadata.char_count,
                chunk.full_text[:120].replace("\n", " "),
            )

        assert len(chunks) > 0, "应生成 chunk"

        # 所有 chunk 都应有文本
        non_empty = [c for c in chunks if c.full_text.strip()]
        logger.info("非空 chunk: %d / %d", len(non_empty), len(chunks))

    # ──── 第五步：输出完整摘要 ────

    def test_07_full_summary(self, capsys=None):
        """输出完整的解析摘要报告"""
        parser = PDFParser()
        elements = parser.parse(TEST_FILE)

        import fitz
        pdf_doc = fitz.open(TEST_FILE)
        total_pages = len(pdf_doc)
        page_sizes = {pn: (pdf_doc[pn].rect.width, pdf_doc[pn].rect.height) for pn in range(len(pdf_doc))}
        pdf_doc.close()

        paragraphs = group_elements_by_paragraph(
            elements,
            vertical_gap_threshold=settings.chunk_vertical_gap,
            max_chunk_size=settings.chunk_max_size,
            page_sizes=page_sizes,
        )

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd"
        chunks = []
        page_chunk_counters: dict[int, int] = {}
        for para_group in paragraphs:
            page = para_group[0].page if para_group else 0
            chunk_index = page_chunk_counters.get(page, 0)
            page_chunk_counters[page] = chunk_index + 1
            chunk = builder.build(
                elements=para_group, doc_id=doc_id,
                source=os.path.basename(TEST_FILE),
                page=page, chunk_index=chunk_index,
            )
            chunks.append(chunk)

        # 摘要
        print("\n" + "=" * 60)
        print(f"  PDF 解析测试报告: ZB-2YD-40-12-480 抱杆使用说明书")
        print("=" * 60)
        print(f"  文件: {os.path.basename(TEST_FILE)}")
        print(f"  总页数: {total_pages}")
        print(f"  解析元素: {len(elements)}")

        type_counts = {}
        for e in elements:
            type_counts[e.elem_type] = type_counts.get(e.elem_type, 0) + 1
        print(f"  元素类型: {dict(sorted(type_counts.items()))}")

        print(f"  段落组: {len(paragraphs)}")
        print(f"  MixedChunk: {len(chunks)}")

        chunk_type_counts = {}
        for c in chunks:
            chunk_type_counts[c.metadata.chunk_type] = chunk_type_counts.get(c.metadata.chunk_type, 0) + 1
        print(f"  Chunk 类型: {dict(sorted(chunk_type_counts.items()))}")

        char_counts = [c.metadata.char_count for c in chunks]
        if char_counts:
            print(f"  字符数: min={min(char_counts)}, max={max(char_counts)}, avg={sum(char_counts) // len(char_counts)}")

        non_empty = [c for c in chunks if c.full_text.strip()]
        print(f"  非空 chunk: {len(non_empty)} / {len(chunks)}")

        # 输出所有 chunk 摘要
        print("\n  --- Chunk 详情 ---")
        for i, chunk in enumerate(chunks):
            img_count = len(chunk.image_urls)
            print(f"  [{i:3d}] {chunk.metadata.chunk_id:40s} type={chunk.metadata.chunk_type:6s} chars={chunk.metadata.char_count:5d} imgs={img_count}")
            # 输出前 150 字
            preview = chunk.full_text[:150].replace("\n", "\\n")
            print(f"        {preview}")

        print("\n" + "=" * 60)
