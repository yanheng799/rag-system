"""测试 ZB-2YD docx 文档解析与分块"""

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

TEST_FILE_640 = os.path.join(
    os.path.dirname(__file__), "..", "test-files",
    "ZB-2YD-40-16-640（800截面）落地双摇臂抱杆使用说明书.docx",
)

TEST_FILE_800 = os.path.join(
    os.path.dirname(__file__), "..", "test-files",
    "ZB-2YD-50-18-800（800截面）落地双摇臂抱杆使用说明书.docx",
)


class TestZB2YDDocx:
    """ZB-2YD 800截面 抱杆使用说明书 docx 解析测试"""

    def test_01_parse_docx(self):
        """验证 docx 能成功解析出元素"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_640)

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
        elements = parser.parse(TEST_FILE_640)
        titles = [e for e in elements if e.elem_type == "title"]

        print("\n=== 标题 ===")
        for t in titles[:20]:
            print(f"  {t.content[:80]}")
        assert len(titles) > 0

    def test_03_table_content(self):
        """验证表格内容"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_640)
        tables = [e for e in elements if e.elem_type == "table"]

        print(f"\n=== 表格 ({len(tables)} 个) ===")
        for i, t in enumerate(tables[:3]):
            print(f"  表格[{i}] (前200字): {t.content[:200]}")
        assert len(tables) > 0

    def test_04_images(self):
        """验证图片提取"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_640)
        images = [e for e in elements if e.elem_type == "image"]

        print(f"\n=== 图片 ({len(images)} 张) ===")
        for im in images:
            print(f"  {im.content}")
        assert len(images) > 0, "docx 中应有图片"

    def test_05_paragraph_grouping(self):
        """验证段落分组"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_640)
        paragraphs = group_elements_by_paragraph(elements)

        type_counts = {}
        for g, _ in paragraphs:
            ct = detect_chunk_type(g)
            type_counts[ct] = type_counts.get(ct, 0) + 1

        print(f"\n=== 段落分组 ===")
        print(f"  段落组数: {len(paragraphs)}")
        print(f"  类型分布: {dict(sorted(type_counts.items()))}")
        assert len(paragraphs) > 0

    def test_06_chunk_assembly(self):
        """验证 Chunk 组装"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_640)
        paragraphs = group_elements_by_paragraph(elements)

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd_800"
        chunks = []
        pcc = {}
        for pg, _ in paragraphs:
            p = pg[0].page if pg else 1
            ci = pcc.get(p, 0)
            pcc[p] = ci + 1
            c = builder.build(
                elements=pg, doc_id=doc_id,
                source=os.path.basename(TEST_FILE_640),
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
        elements = parser.parse(TEST_FILE_640)
        paragraphs = group_elements_by_paragraph(elements)

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_zb2yd_800"
        chunks = []
        pcc = {}
        for pg, _ in paragraphs:
            p = pg[0].page if pg else 1
            ci = pcc.get(p, 0)
            pcc[p] = ci + 1
            c = builder.build(
                elements=pg, doc_id=doc_id,
                source=os.path.basename(TEST_FILE_640),
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


class TestZB2YD800Docx:
    """ZB-2YD 50-18-800 抱杆使用说明书 docx 解析测试"""

    def test_01_no_toc_elements(self):
        """验证 TOC 条目被过滤"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_800)
        # 该文档有约 47 条 TOC 条目（toc 1/toc 2 样式），应全部被过滤
        # 过滤后不应出现 "1\t1" 之类的目录页码条目
        toc_like = [
            e for e in elements
            if "\t" in e.content and any(c.isdigit() for c in e.content.split("\t")[-1])
        ]
        assert len(toc_like) == 0, f"应无 TOC 残留，但发现 {len(toc_like)} 条"

    def test_02_tables_preserved(self):
        """验证表格未丢失"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_800)
        tables = [e for e in elements if e.is_table]
        assert len(tables) >= 20, f"表格数量过少: {len(tables)}"

    def test_03_images_preserved(self):
        """验证图片未丢失"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_800)
        images = [e for e in elements if e.is_image]
        assert len(images) >= 30, f"图片数量过少: {len(images)}"

    def test_04_titles_trigger_boundary(self):
        """验证标题触发段落边界（无编号标题也能触发）"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_800)
        paragraphs = group_elements_by_paragraph(elements)

        # 每个标题元素应该开始新的段落组（或被孤立标题合并到下一个组）
        # 验证段落组数量应显著大于无标题分割时
        assert len(paragraphs) >= 80, f"段落组过少: {len(paragraphs)}，标题未触发边界"

    def test_05_chunk_quality(self):
        """验证 chunk 质量：表格/图片与所属 section 绑定"""
        parser = WordParser()
        elements = parser.parse(TEST_FILE_800)
        paragraphs = group_elements_by_paragraph(elements)

        builder = ChunkBuilder(screenshot=None, describer=TableDescriber())
        doc_id = "test_800"
        chunks = []
        pcc = {}
        for pg, _ in paragraphs:
            p = pg[0].page if pg else 1
            ci = pcc.get(p, 0)
            pcc[p] = ci + 1
            c = builder.build(
                elements=pg, doc_id=doc_id,
                source=os.path.basename(TEST_FILE_800),
                page=p, chunk_index=ci,
            )
            chunks.append(c)

        # 所有表格都在 chunk 中
        chunk_tables = sum(1 for c in chunks for e in c.elements if e.type == "table")
        chunk_images = sum(1 for c in chunks for e in c.elements if e.type == "image")
        parsed_tables = sum(1 for e in elements if e.is_table)
        parsed_images = sum(1 for e in elements if e.is_image)

        print(f"\n=== 800 文档 Chunk 质量 ===")
        print(f"  Chunks: {len(chunks)}")
        print(f"  Tables: {chunk_tables}/{parsed_tables}  Images: {chunk_images}/{parsed_images}")

        assert chunk_tables == parsed_tables, f"表格丢失: {chunk_tables}/{parsed_tables}"
        assert chunk_images == parsed_images, f"图片丢失: {chunk_images}/{parsed_images}"

        # 含表格/图片的 chunk 应较多
        rich_chunks = sum(
            1 for c in chunks
            if any(e.type in ("table", "image") for e in c.elements)
        )
        assert rich_chunks >= 30, f"含表格/图片的 chunk 过少: {rich_chunks}"
