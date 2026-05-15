"""分块策略测试：FixedSizeChunker、HeadingChunker、PageChunker、ParagraphChunker、ChunkerRegistry"""

from src.ingestion.chunkers.registry import ChunkerRegistry, init_chunkers
from src.ingestion.chunkers.strategies.fixed_size_chunker import (
    FixedSizeChunker,
    _get_overlap_elements,
)
from src.ingestion.chunkers.strategies.heading_chunker import HeadingChunker
from src.ingestion.chunkers.strategies.page_chunker import PageChunker
from src.ingestion.chunkers.strategies.paragraph_chunker import ParagraphChunker
from src.ingestion.parsers.base import ParsedElement


def _elem(content: str, page: int = 1, elem_type: str = "text") -> ParsedElement:
    return ParsedElement(elem_type=elem_type, content=content, page=page)


class TestFixedSizeChunker:
    """固定大小分块：按字符数滑窗切割"""

    def setup_method(self):
        self.chunker = FixedSizeChunker()
        self.page_sizes = {1: (612, 792)}

    def test_empty_input(self):
        result = self.chunker.chunk([], self.page_sizes, "doc1")

        assert result == []

    def test_single_element_under_limit(self):
        result = self.chunker.chunk(
            [_elem("hello")], self.page_sizes, "doc1", max_chunk_size=100
        )

        assert len(result) == 1
        assert len(result[0][0]) == 1

    def test_overflow_creates_groups_with_ids(self):
        elems = [_elem("a" * 60), _elem("b" * 60), _elem("c" * 60)]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=100)

        assert len(result) >= 2
        groups_with_ids = [(e, g) for e, g in result if g != ""]
        assert len(groups_with_ids) > 0

    def test_all_elements_fit_in_one_chunk(self):
        elems = [_elem("short"), _elem("text")]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=1000)

        assert len(result) == 1

    def test_max_chunk_size_zero_returns_single_group(self):
        elems = [_elem("a" * 200), _elem("b" * 200)]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=0)

        assert len(result) == 1
        assert result[0][1] == ""

    def test_group_id_format(self):
        elems = [_elem("a" * 60), _elem("b" * 60)]

        result = self.chunker.chunk(elems, self.page_sizes, "mydoc", max_chunk_size=80)

        for _, gid in result:
            if gid:
                assert gid.startswith("mydoc_g")

    def test_tail_merge_small_last_chunk(self):
        elems = [_elem("a" * 60), _elem("b" * 60), _elem("c")]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=100, min_chunk_size=10
        )

        all_elems = [e for group, _ in result for e in group]
        assert len(all_elems) == 3

    def test_overlap_includes_elements_from_previous_group(self):
        elems = [_elem("aaa"), _elem("bbb"), _elem("ccc"), _elem("ddd")]

        result = self.chunker.chunk(
            elems,
            self.page_sizes,
            "doc1",
            max_chunk_size=6,
            overlap=3,
        )

        if len(result) >= 2:
            first_ids = {id(e) for e in result[0][0]}
            second_ids = {id(e) for e in result[1][0]}
            assert first_ids & second_ids, "重叠组应共享部分元素"

    def test_single_oversized_element_own_group(self):
        elems = [_elem("a" * 200), _elem("b" * 80)]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=100, min_chunk_size=0
        )

        assert len(result) == 2
        assert len(result[0][0]) == 1
        assert result[0][0][0].content == "a" * 200


class TestGetOverlapElements:
    """overlap 回溯逻辑"""

    def test_returns_trailing_elements(self):
        elems = [_elem("aaa"), _elem("bbb"), _elem("ccc")]

        overlap = _get_overlap_elements(elems, overlap_chars=5)

        assert len(overlap) >= 1
        assert overlap[-1].content == "ccc"

    def test_zero_overlap_returns_empty(self):
        result = _get_overlap_elements([_elem("aaa")], overlap_chars=0)

        assert result == []

    def test_full_group_as_overlap(self):
        elems = [_elem("aa")]

        overlap = _get_overlap_elements(elems, overlap_chars=100)

        assert overlap == elems


class TestHeadingChunker:
    """标题分块：按标题边界拆分"""

    def setup_method(self):
        self.chunker = HeadingChunker()
        self.page_sizes = {1: (612, 792)}

    def test_empty_input(self):
        assert self.chunker.chunk([], self.page_sizes, "doc1") == []

    def test_splits_at_title_boundary(self):
        preamble = "前言内容前言内容前言内容前言内容前言内容前言内容"
        intro = "简介内容简介内容简介内容简介内容简介内容简介内容"
        elems = [
            _elem(preamble),
            _elem("第1章 简介", elem_type="title"),
            _elem(intro),
        ]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=0, min_chunk_size=0
        )

        assert len(result) == 2
        assert preamble in result[0][0][0].content
        assert "第1章 简介" in result[1][0][0].content

    def test_splits_at_heading_pattern(self):
        elems = [
            _elem("1.1 背景介绍"),
            _elem("背景内容"),
            _elem("1.2 研究方法"),
            _elem("方法内容"),
        ]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=0, min_chunk_size=0)

        assert len(result) >= 2

    def test_no_headings_returns_single_group(self):
        elems = [_elem("纯文本段落一"), _elem("纯文本段落二")]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=0)

        assert len(result) == 1

    def test_oversized_heading_group_split(self):
        elems = [
            _elem("第1章", elem_type="title"),
            _elem("a" * 60),
            _elem("b" * 60),
        ]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=100, min_chunk_size=0
        )

        assert len(result) >= 2
        groups_with_ids = [g for _, g in result if g]
        assert len(groups_with_ids) > 0


class TestPageChunker:
    """逐页分块：按页码聚合"""

    def setup_method(self):
        self.chunker = PageChunker()
        self.page_sizes = {1: (612, 792), 2: (612, 792)}

    def test_empty_input(self):
        assert self.chunker.chunk([], self.page_sizes, "doc1") == []

    def test_groups_by_page(self):
        elems = [
            _elem("p1 text a, " * 10, page=1),
            _elem("p1 text b, " * 10, page=1),
            _elem("p2 text, " * 10, page=2),
        ]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=0, min_chunk_size=0
        )

        assert len(result) == 2
        assert all(e.page == 1 for e in result[0][0])
        assert all(e.page == 2 for e in result[1][0])

    def test_single_page(self):
        elems = [_elem("a", page=1), _elem("b", page=1)]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1", max_chunk_size=0)

        assert len(result) == 1

    def test_oversized_page_split(self):
        elems = [
            _elem("a" * 60, page=1),
            _elem("b" * 60, page=1),
        ]

        result = self.chunker.chunk(
            elems, self.page_sizes, "doc1", max_chunk_size=80, min_chunk_size=0
        )

        assert len(result) >= 2


class TestParagraphChunker:
    """段落分块：委托给 group_elements_by_paragraph"""

    def setup_method(self):
        self.chunker = ParagraphChunker()
        self.page_sizes = {1: (612, 792)}

    def test_empty_input(self):
        result = self.chunker.chunk([], self.page_sizes, "doc1")

        assert result == []

    def test_returns_chunked_groups(self):
        elems = [
            _elem("第一段文本内容"),
            _elem("第二段文本内容"),
        ]

        result = self.chunker.chunk(elems, self.page_sizes, "doc1")

        assert len(result) >= 1
        all_elems = [e for group, _ in result for e in group]
        assert len(all_elems) == 2


class TestChunkerRegistry:
    """分块策略注册表"""

    def setup_method(self):
        ChunkerRegistry._chunkers.clear()

    def test_register_and_get(self):
        chunker = FixedSizeChunker()
        ChunkerRegistry.register("test", chunker)

        assert ChunkerRegistry.get("test") is chunker

    def test_get_unknown_raises(self):
        try:
            ChunkerRegistry.get("nonexistent")
            assert False, "应抛出 ValueError"
        except ValueError as e:
            assert "nonexistent" in str(e)

    def test_available_strategies(self):
        ChunkerRegistry.register("a", FixedSizeChunker())
        ChunkerRegistry.register("b", PageChunker())

        strategies = ChunkerRegistry.available_strategies()

        assert "a" in strategies
        assert "b" in strategies

    def test_init_chunkers_registers_all(self):
        init_chunkers()

        strategies = ChunkerRegistry.available_strategies()

        assert "paragraph" in strategies
        assert "heading" in strategies
        assert "fixed_size" in strategies
        assert "page" in strategies
        assert len(strategies) == 4

    def test_init_chunkers_returns_correct_types(self):
        init_chunkers()

        assert isinstance(ChunkerRegistry.get("paragraph"), ParagraphChunker)
        assert isinstance(ChunkerRegistry.get("heading"), HeadingChunker)
        assert isinstance(ChunkerRegistry.get("fixed_size"), FixedSizeChunker)
        assert isinstance(ChunkerRegistry.get("page"), PageChunker)

