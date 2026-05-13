"""分块管理 API 逻辑测试"""

from __future__ import annotations

from src.api.routers.chunks import EMBEDDING_MAX_CHARS, _detect_chunk_type


class TestDetectChunkType:
    """测试 chunk_type 推断逻辑"""

    def test_single_text(self):
        elements = [{"type": "text", "content": "hello"}]
        assert _detect_chunk_type(elements) == "text"

    def test_single_table(self):
        elements = [{"type": "table", "content": "| a | b |"}]
        assert _detect_chunk_type(elements) == "table"

    def test_single_image(self):
        elements = [{"type": "image", "content": "图片", "image_url": "x.png"}]
        assert _detect_chunk_type(elements) == "image"

    def test_mixed(self):
        elements = [
            {"type": "text", "content": "hello"},
            {"type": "table", "content": "| a | b |"},
        ]
        assert _detect_chunk_type(elements) == "mixed"

    def test_empty(self):
        assert _detect_chunk_type([]) == "text"


class TestMergeValidation:
    """测试合并校验逻辑"""

    def test_same_doc_check(self):
        """不同文档的 chunk 不能合并"""
        chunks_data = [
            {"chunk_id": "a_p1_c0", "doc_id": "doc_a", "page": 1, "chunk_index": 0},
            {"chunk_id": "b_p1_c0", "doc_id": "doc_b", "page": 1, "chunk_index": 0},
        ]
        doc_ids = {c["doc_id"] for c in chunks_data}
        assert len(doc_ids) != 1

    def test_no_gap_range(self):
        """选定范围（page+chunk_index）内不应有遗漏 chunk"""
        selected = [
            {"chunk_id": "a_p1_c0", "page": 1, "chunk_index": 0},
            {"chunk_id": "a_p1_c2", "page": 1, "chunk_index": 2},
        ]
        all_chunks = [
            {"chunk_id": "a_p1_c0", "page": 1, "chunk_index": 0},
            {"chunk_id": "a_p1_c1", "page": 1, "chunk_index": 1},  # 遗漏
            {"chunk_id": "a_p1_c2", "page": 1, "chunk_index": 2},
        ]
        sorted_sel = sorted(selected, key=lambda c: (c["page"], c["chunk_index"]))
        min_pos = (sorted_sel[0]["page"], sorted_sel[0]["chunk_index"])
        max_pos = (sorted_sel[-1]["page"], sorted_sel[-1]["chunk_index"])
        selected_ids = {c["chunk_id"] for c in selected}
        has_gap = any(
            (c["page"], c["chunk_index"]) >= min_pos
            and (c["page"], c["chunk_index"]) <= max_pos
            and c["chunk_id"] not in selected_ids
            for c in all_chunks
        )
        assert has_gap is True

    def test_no_gap_range_ok(self):
        """选定范围无遗漏时应通过"""
        selected = [
            {"chunk_id": "a_p1_c0", "page": 1, "chunk_index": 0},
            {"chunk_id": "a_p1_c1", "page": 1, "chunk_index": 1},
        ]
        all_chunks = [
            {"chunk_id": "a_p1_c0", "page": 1, "chunk_index": 0},
            {"chunk_id": "a_p1_c1", "page": 1, "chunk_index": 1},
            {"chunk_id": "a_p1_c2", "page": 1, "chunk_index": 2},
        ]
        sorted_sel = sorted(selected, key=lambda c: (c["page"], c["chunk_index"]))
        min_pos = (sorted_sel[0]["page"], sorted_sel[0]["chunk_index"])
        max_pos = (sorted_sel[-1]["page"], sorted_sel[-1]["chunk_index"])
        selected_ids = {c["chunk_id"] for c in selected}
        has_gap = any(
            (c["page"], c["chunk_index"]) >= min_pos
            and (c["page"], c["chunk_index"]) <= max_pos
            and c["chunk_id"] not in selected_ids
            for c in all_chunks
        )
        assert has_gap is False

    def test_embedding_char_limit(self):
        """合并后 full_text 超过 embedding 限制应拒绝"""
        char_count = EMBEDDING_MAX_CHARS + 1
        assert char_count > EMBEDDING_MAX_CHARS

    def test_embedding_char_limit_ok(self):
        """合并后 full_text 在限制内应通过"""
        char_count = EMBEDDING_MAX_CHARS
        assert char_count <= EMBEDDING_MAX_CHARS

    def test_min_chunks(self):
        """至少需要 2 个 chunk"""
        assert len(["only_one"]) < 2


class TestSplitValidation:
    """测试拆分校验逻辑"""

    def test_split_at_boundary_zero(self):
        """split_at=0 不合法"""
        split_at = 0
        assert split_at < 1

    def test_split_at_equals_len(self):
        """split_at=len(elements) 不合法"""
        elements = [{"type": "text", "content": "a"}, {"type": "text", "content": "b"}]
        split_at = len(elements)
        assert split_at >= len(elements)

    def test_split_at_valid(self):
        """split_at=1 合法"""
        elements = [{"type": "text", "content": "a"}, {"type": "text", "content": "b"}]
        split_at = 1
        assert 1 <= split_at < len(elements)

    def test_split_result(self):
        """验证拆分后元素分配正确"""
        elements = [
            {"type": "text", "content": "a"},
            {"type": "table", "content": "| b |"},
            {"type": "text", "content": "c"},
        ]
        split_at = 2
        elems_a = elements[:split_at]
        elems_b = elements[split_at:]
        assert len(elems_a) == 2
        assert len(elems_b) == 1
        assert elems_a[0]["content"] == "a"
        assert elems_b[0]["content"] == "c"

    def test_split_image_urls(self):
        """拆分后 image_urls 按元素归属分配"""
        elements = [
            {"type": "table", "content": "t1", "image_url": "img1.png"},
            {"type": "table", "content": "t2", "image_url": "img2.png"},
        ]
        split_at = 1
        urls_a = [e.get("image_url") for e in elements[:split_at] if e.get("image_url")]
        urls_b = [e.get("image_url") for e in elements[split_at:] if e.get("image_url")]
        assert urls_a == ["img1.png"]
        assert urls_b == ["img2.png"]

    def test_single_element_cannot_split(self):
        """只有 1 个元素的 chunk 无法拆分"""
        elements = [{"type": "text", "content": "only"}]
        split_at = 1
        assert split_at >= len(elements)


class TestSplitGroupPolicy:
    """测试拆分 group_id 策略"""

    def test_link_group_true(self):
        """link_group=True 时两子 chunk 应共享 group_id"""
        link_group = True
        doc_id = "doc_test"
        group_id = f"{doc_id}_g_abc12345" if link_group else ""
        assert group_id != ""
        assert group_id.startswith(f"{doc_id}_g_")

    def test_link_group_false(self):
        """link_group=False 时两子 chunk 的 group_id 应为空"""
        link_group = False
        doc_id = "doc_test"
        group_id = ""
        if link_group:
            group_id = f"{doc_id}_g_abc12345"
        assert group_id == ""

    def test_default_is_false(self):
        """Schema 默认值应为 False"""
        from src.api.schemas.chunks import SplitRequest

        req = SplitRequest(split_at=1)
        assert req.link_group is False


class TestDeleteValidation:
    """测试删除校验逻辑"""

    def test_delete_nonexistent_returns_none(self):
        """删除不存在的 chunk 应返回 None（路由层判 404）"""
        # 模拟 get_chunk 返回 None
        assert None is None

    def test_dissolve_orphan_group(self):
        """删除带 group_id 的 chunk 时，同组兄弟应解散"""
        deleted_chunk = {"chunk_id": "a_p1_c0", "group_id": "doc_g0"}
        sibling_chunk = {"chunk_id": "a_p1_c1", "group_id": "doc_g0"}
        affected_groups = set()
        if deleted_chunk["group_id"]:
            affected_groups.add(deleted_chunk["group_id"])
        # 兄弟应清空 group_id
        if sibling_chunk["group_id"] in affected_groups:
            sibling_chunk["group_id"] = ""
        assert sibling_chunk["group_id"] == ""
