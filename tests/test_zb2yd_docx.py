"""测试 ZB-2YD-40-16-640（800截面）落地双摇臂抱杆使用说明书.docx 的解析流程"""

import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingestion.parsers.word_parser import WordParser
from ingestion.chunkers.paragraph_grouper import (
    detect_chunk_type,
    group_elements_by_paragraph,
)
from ingestion.chunkers.chunk_assembler import ChunkBuilder
from ingestion.table_processor.describer import TableDescriber

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")

TEST_FILE = os.path.join(
    os.path.dirname(__file__), "..", "test-files",
    "ZB-2YD-40-16-640（800截面）落地双摇臂抱杆使用说明书.docx",
)


class TestZB2YDDocx:
    """ZB-2YD 800截面 抱杆使用说明书 docx 解析测试"""

    def test_01_parse_docx(self):
        """验证 docx 能成功解析出元素"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)

        type_counts = {}
        for e in elements:
            type_counts[e.elem_type] = type_counts.get(e.elem_type, 0) + 1

        print("\n=== 解析结果 ===")
        print(f"  总元素数: {len(elements)}")
        print(f"  元素类型: {dict(sorted(type_counts.items()))}")
        assert len(elements) > 0

    def test_02_title_detection(self):
        """验证标题检测"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        titles = [e for e in elements if e.elem_type == "title"]

        print("\n=== 标题 ===")
        for t in titles[:20]:
            print(f"  {t.content[:80]}")
        assert len(titles) > 0

    def test_03_table_content(self):
        """验证表格内容"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        tables = [e for e in elements if e.elem_type == "table"]

        print(f"\n=== 表格 ({len(tables)} 个) ===")
        for i, t in enumerate(tables[:3]):
            print(f"  表格[{i}] (前200字): {t.content[:200]}")
        assert len(tables) > 0

    def test_04_images(self):
        """验证图片提取"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        images = [e for e in elements if e.elem_type == "image"]

        print(f"\n=== 图片 ({len(images)} 张) ===")
        for im in images:
            print(f"  {im.content}")
        assert len(images) > 0, "docx 中应有图片"

    def test_05_paragraph_grouping(self):
        """验证段落分组"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        paragraphs = group_elements_by_paragraph(elements)

        type_counts = {}
        for g in paragraphs:
            ct = detect_chunk_type(g)
            type_counts[ct] = type_counts.get(ct, 0) + 1

        print(f"\n=== 段落分组 ===")
        print(f"  段落组数: {len(paragraphs)}")
        print(f"  类型分布: {dict(sorted(type_counts.items()))}")
        assert len(paragraphs) > 0

    def test_06_chunk_assembly(self):
        """验证 Chunk 组装"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        paragraphs = group_elements_by_paragraph(elements)

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd_800"
        chunks = []
        pcc = {}
        for pg in paragraphs:
            p = pg[0].page if pg else 1
            ci = pcc.get(p, 0)
            pcc[p] = ci + 1
            c = builder.build(
                elements=pg, doc_id=doc_id,
                source=os.path.basename(TEST_FILE),
                page=p, chunk_index=ci,
            )
            chunks.append(c)

        print(f"\n=== Chunk 组装 ===")
        print(f"  总 chunk: {len(chunks)}")

        ctc = {}
        for c in chunks:
            ctc[c.metadata.chunk_type] = ctc.get(c.metadata.chunk_type, 0) + 1
        print(f"  类型: {dict(sorted(ctc.items()))}")

        cc = [c.metadata.char_count for c in chunks]
        print(f"  字符数: min={min(cc)}, max={max(cc)}, avg={sum(cc)//len(cc)}")

        # 检查图片是否正确归入 chunk
        img_chunks = [c for c in chunks if any(e.type == "image" for e in c.elements)]
        print(f"  含图片的 chunk: {len(img_chunks)}")
        for c in img_chunks:
            img_names = [e.content for e in c.elements if e.type == "image"]
            other = [e.content[:40] for e in c.elements if e.type != "image"]
            print(f"    {c.metadata.chunk_id}: imgs={img_names}")
            print(f"      上下文: {other[:3]}")

        assert len(chunks) > 0

    def test_07_full_summary(self):
        """完整摘要"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE)
        paragraphs = group_elements_by_paragraph(elements)

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd_800"
        chunks = []
        pcc = {}
        for pg in paragraphs:
            p = pg[0].page if pg else 1
            ci = pcc.get(p, 0)
            pcc[p] = ci + 1
            c = builder.build(
                elements=pg, doc_id=doc_id,
                source=os.path.basename(TEST_FILE),
                page=p, chunk_index=ci,
            )
            chunks.append(c)

        print("\n" + "=" * 70)
        print("  DOCX 解析测试报告: ZB-2YD-40-16-640（800截面）抱杆使用说明书")
        print("=" * 70)

        tc = {}
        for e in elements:
            tc[e.elem_type] = tc.get(e.elem_type, 0) + 1
        print(f"  解析元素: {len(elements)}  类型: {dict(sorted(tc.items()))}")
        print(f"  段落组: {len(paragraphs)}")
        print(f"  MixedChunk: {len(chunks)}")

        ctc = {}
        for c in chunks:
            ctc[c.metadata.chunk_type] = ctc.get(c.metadata.chunk_type, 0) + 1
        print(f"  Chunk类型: {dict(sorted(ctc.items()))}")

        print("\n  --- Chunk 详情 ---")
        for i, chunk in enumerate(chunks):
            has_img = any(e.type == "image" for e in chunk.elements)
            flag = " [IMG]" if has_img else ""
            preview = chunk.full_text[:100].replace("\n", " ")
            print(f"  [{i:3d}] {chunk.metadata.chunk_id:30s} type={chunk.metadata.chunk_type:6s} chars={chunk.metadata.char_count:5d}{flag}")
            print(f"        {preview}")
