"""分块管理 API 逻辑测试 — 通过真实函数和 Schema 验证"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.api.routers.chunks import (
    CHUNK_PREVIEW_LIMIT,
    EMBEDDING_MAX_CHARS,
    _cleanup_oss_images,
    _detect_chunk_type,
    _dissolve_orphan_groups,
    _preview_text,
    _validate_char_limit,
    _validate_merge_no_gap,
    _validate_merge_same_doc,
    _validate_split_at,
)


# ---- 轻量 Fake 对象 ----


class _FakeChunk:
    __slots__ = ("chunk_id", "doc_id", "page", "chunk_index", "group_id")

    def __init__(self, chunk_id, doc_id="", page=1, chunk_index=0, group_id=""):
        self.chunk_id = chunk_id
        self.doc_id = doc_id
        self.page = page
        self.chunk_index = chunk_index
        self.group_id = group_id


class _FakePgStore:
    def __init__(self, chunks=None):
        self._chunks = chunks or []
        self.cleared_group_ids: list[list[str]] = []

    async def get_chunks_by_ids(self, ids):
        return [c for c in self._chunks if c.chunk_id in ids]

    async def clear_group_id(self, gids):
        self.cleared_group_ids.append(gids)


class _FakeMilvusStore:
    def __init__(self, siblings=None):
        self._siblings = siblings or []

    def fetch_by_group_ids(self, gids):
        return self._siblings


class _FakeOssStore:
    def __init__(self, fail_on=None):
        self.deleted: list[str] = []
        self._fail_on = fail_on or set()

    def delete(self, url):
        if url in self._fail_on:
            raise RuntimeError(f"delete failed: {url}")
        self.deleted.append(url)


# ---- _detect_chunk_type ----


class TestDetectChunkType:
    """根据 elements 列表推断 chunk_type"""

    def test_single_text(self):
        assert _detect_chunk_type([{"type": "text", "content": "hello"}]) == "text"

    def test_single_table(self):
        assert _detect_chunk_type([{"type": "table", "content": "| a | b |"}]) == "table"

    def test_single_image(self):
        assert _detect_chunk_type([{"type": "image", "content": "图片", "image_url": "x.png"}]) == "image"

    def test_mixed(self):
        elements = [
            {"type": "text", "content": "hello"},
            {"type": "table", "content": "| a | b |"},
        ]
        assert _detect_chunk_type(elements) == "mixed"

    def test_empty_returns_text(self):
        assert _detect_chunk_type([]) == "text"


# ---- _validate_merge_same_doc ----


class TestValidateMergeSameDoc:
    """合并校验：同一文档检查"""

    def test_same_doc_returns_doc_id(self):
        chunks = [_FakeChunk("c1", "doc_a"), _FakeChunk("c2", "doc_a")]
        assert _validate_merge_same_doc(chunks) == "doc_a"

    def test_different_doc_raises_400(self):
        chunks = [_FakeChunk("c1", "doc_a"), _FakeChunk("c2", "doc_b")]
        with pytest.raises(HTTPException) as exc:
            _validate_merge_same_doc(chunks)
        assert exc.value.status_code == 400
        assert "同一文档" in exc.value.detail


# ---- _validate_merge_no_gap ----


class TestValidateMergeNoGap:
    """合并校验：选中的分块在文档分块序列中连续，中间无遗漏"""

    def test_contiguous_passes(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=2),
        ]
        _validate_merge_no_gap(["c0", "c1"], all_chunks)

    def test_gap_in_sorted_order_raises_400(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=2),
        ]
        with pytest.raises(HTTPException) as exc:
            _validate_merge_no_gap(["c0", "c2"], all_chunks)
        assert exc.value.status_code == 400
        assert "未选中" in exc.value.detail
        assert "c1" in exc.value.detail

    def test_non_adjacent_outside_range_ok(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=5),
        ]
        # c0 和 c1 相邻，c2 在排序中隔开但不影响
        _validate_merge_no_gap(["c0", "c1"], all_chunks)

    def test_cross_page_gap(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=2, chunk_index=0),
        ]
        with pytest.raises(HTTPException) as exc:
            _validate_merge_no_gap(["c0", "c2"], all_chunks)
        assert "c1" in exc.value.detail

    def test_non_sequential_indices_after_merge(self):
        """合并后 chunk_index 可能不连续（如 0, 1, 5, 6），但仍可按排序顺序检查"""
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c5", page=1, chunk_index=5),
            _FakeChunk("c6", page=1, chunk_index=6),
        ]
        # c1 和 c5 在排序中相邻，应允许合并
        _validate_merge_no_gap(["c1", "c5"], all_chunks)


# ---- _validate_char_limit ----


class TestValidateCharLimit:
    """合并校验：embedding 字数限制"""

    def test_within_limit_passes(self):
        _validate_char_limit(EMBEDDING_MAX_CHARS)

    def test_exactly_at_limit_passes(self):
        _validate_char_limit(EMBEDDING_MAX_CHARS)

    def test_over_limit_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_char_limit(EMBEDDING_MAX_CHARS + 1)
        assert exc.value.status_code == 400
        assert "embedding 限制" in exc.value.detail

    def test_zero_passes(self):
        _validate_char_limit(0)


# ---- _validate_split_at ----


class TestValidateSplitAt:
    """拆分校验：split_at 边界"""

    def test_valid_passes(self):
        _validate_split_at(1, 3)

    def test_split_at_middle(self):
        _validate_split_at(2, 5)

    def test_equals_len_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_split_at(2, 2)
        assert exc.value.status_code == 400
        assert "超出元素范围" in exc.value.detail

    def test_exceeds_len_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            _validate_split_at(5, 3)
        assert exc.value.status_code == 400

    def test_single_element_rejects_split_at_1(self):
        with pytest.raises(HTTPException) as exc:
            _validate_split_at(1, 1)
        assert exc.value.status_code == 400


# ---- Schema 验证 ----


class TestMergeRequestSchema:
    """MergeRequest Pydantic 校验"""

    def test_min_two_chunk_ids(self):
        from src.api.schemas.chunks import MergeRequest

        with pytest.raises(ValidationError):
            MergeRequest(chunk_ids=["only_one"])

    def test_valid_request(self):
        from src.api.schemas.chunks import MergeRequest

        req = MergeRequest(chunk_ids=["c1", "c2"])
        assert req.chunk_ids == ["c1", "c2"]


class TestSplitRequestSchema:
    """SplitRequest Pydantic 校验"""

    def test_split_at_zero_rejected(self):
        from src.api.schemas.chunks import SplitRequest

        with pytest.raises(ValidationError):
            SplitRequest(split_at=0)

    def test_split_at_negative_rejected(self):
        from src.api.schemas.chunks import SplitRequest

        with pytest.raises(ValidationError):
            SplitRequest(split_at=-1)

    def test_default_link_group_is_false(self):
        from src.api.schemas.chunks import SplitRequest

        req = SplitRequest(split_at=1)
        assert req.link_group is False

    def test_explicit_link_group_true(self):
        from src.api.schemas.chunks import SplitRequest

        req = SplitRequest(split_at=1, link_group=True)
        assert req.link_group is True


# ---- _dissolve_orphan_groups ----


class TestDissolveOrphanGroups:
    """孤儿组解散逻辑"""

    @pytest.mark.asyncio
    async def test_orphan_group_cleaned(self):
        pg = _FakePgStore(chunks=[_FakeChunk("c1", group_id="g1")])
        milvus = _FakeMilvusStore(siblings=[{"chunk_id": "c1"}])

        await _dissolve_orphan_groups(pg, milvus, None, ["c1"])

        assert ["g1"] in pg.cleared_group_ids

    @pytest.mark.asyncio
    async def test_surviving_members_not_cleaned(self):
        pg = _FakePgStore(chunks=[_FakeChunk("c1", group_id="g1")])
        milvus = _FakeMilvusStore(siblings=[{"chunk_id": "c1"}, {"chunk_id": "c2"}])

        await _dissolve_orphan_groups(pg, milvus, None, ["c1"])

        assert pg.cleared_group_ids == []

    @pytest.mark.asyncio
    async def test_no_group_id_early_return(self):
        pg = _FakePgStore(chunks=[_FakeChunk("c1", group_id="")])
        milvus = _FakeMilvusStore()

        await _dissolve_orphan_groups(pg, milvus, None, ["c1"])

        assert pg.cleared_group_ids == []


# ---- _cleanup_oss_images ----


class TestCleanupOssImages:
    """OSS 图片清理"""

    @pytest.mark.asyncio
    async def test_deletes_all_urls(self):
        oss = _FakeOssStore()
        await _cleanup_oss_images(oss, ["img1.png", "img2.png"])
        assert oss.deleted == ["img1.png", "img2.png"]

    @pytest.mark.asyncio
    async def test_continues_on_failure(self):
        oss = _FakeOssStore(fail_on={"img2.png"})
        await _cleanup_oss_images(oss, ["img1.png", "img2.png", "img3.png"])
        assert oss.deleted == ["img1.png", "img3.png"]

    @pytest.mark.asyncio
    async def test_empty_urls_no_op(self):
        oss = _FakeOssStore()
        await _cleanup_oss_images(oss, [])
        assert oss.deleted == []


# ---- _preview_text ----


class TestPreviewText:
    """列表预览截断：头尾保留，确保末尾注释可见"""

    def test_short_text_not_truncated(self):
        assert _preview_text("短文本") == "短文本"

    def test_exact_limit_not_truncated(self):
        text = "a" * CHUNK_PREVIEW_LIMIT
        assert _preview_text(text) == text

    def test_long_text_keeps_head_and_tail(self):
        text = "头" * 300 + "尾" * 300
        preview = _preview_text(text)
        assert len(preview) <= CHUNK_PREVIEW_LIMIT
        assert preview.startswith("头")
        assert preview.endswith("尾")
        assert "..." in preview

    def test_table_chunk_tail_note_visible(self):
        """回归：表格 chunk 末尾的'注：…'不能被列表预览截掉。

        full_text = 表标题 + 多行表格 markdown（长） + 末尾注释。
        从头截断 200 字符会把末尾注释截掉；头尾保留后注释应可见。
        """
        header = "表6-2 地线参数\n"
        # 构造一段足够长的表格 markdown，把注释推到 200 字符之外
        rows = "\n".join(f"| 项目{i} | 数据{i} |" for i in range(40))
        note = "注：参数参照物资招标技术规范书，具体参数以中标结果为准。"
        full_text = header + rows + "\n" + note

        assert len(full_text) > CHUNK_PREVIEW_LIMIT  # 确实超长
        assert note not in full_text[:CHUNK_PREVIEW_LIMIT]  # 从头截断会丢注释

        preview = _preview_text(full_text)
        assert note in preview  # 头尾保留后注释可见
        assert "表6-2" in preview  # 头部表标题仍保留
