"""分块管理 API 逻辑测试 — 通过真实函数和 Schema 验证"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.api.routers.chunks import (
    EMBEDDING_MAX_CHARS,
    _cleanup_oss_images,
    _detect_chunk_type,
    _dissolve_orphan_groups,
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
    """合并校验：选定范围内无遗漏"""

    def test_no_gap_passes(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=2),
        ]
        _validate_merge_no_gap(["c0", "c1"], all_chunks, 1, 0, 1, 1)

    def test_gap_raises_400(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=2),
        ]
        with pytest.raises(HTTPException) as exc:
            _validate_merge_no_gap(["c0", "c2"], all_chunks, 1, 0, 1, 2)
        assert exc.value.status_code == 400
        assert "未选中" in exc.value.detail
        assert "c1" in exc.value.detail

    def test_outside_range_ignored(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=1, chunk_index=2),
        ]
        _validate_merge_no_gap(["c0", "c1"], all_chunks, 1, 0, 1, 1)

    def test_cross_page_gap(self):
        all_chunks = [
            _FakeChunk("c0", page=1, chunk_index=0),
            _FakeChunk("c1", page=1, chunk_index=1),
            _FakeChunk("c2", page=2, chunk_index=0),
        ]
        with pytest.raises(HTTPException) as exc:
            _validate_merge_no_gap(["c0", "c2"], all_chunks, 1, 0, 2, 0)
        assert "c1" in exc.value.detail


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
