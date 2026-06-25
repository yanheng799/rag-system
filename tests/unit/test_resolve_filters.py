"""resolve_filters 单元测试"""

import pytest

from src.api.routers._shared import resolve_filters


class FakePgStore:
    """模拟 PgStore 的过滤方法"""

    def __init__(
        self,
        dataset_to_docs: dict | None = None,
        name_to_docs: dict | None = None,
    ):
        self._dataset_to_docs = dataset_to_docs or {}
        self._name_to_docs = name_to_docs or {}

    async def get_doc_ids_by_dataset_ids(self, dataset_ids, org_id=None):
        result = []
        for ds_id in dataset_ids:
            result.extend(self._dataset_to_docs.get(ds_id, []))
        return result

    async def get_doc_ids_by_filenames(self, filenames, org_id=None):
        result = []
        for name in filenames:
            result.extend(self._name_to_docs.get(name, []))
        return result


@pytest.mark.asyncio
async def test_no_filters_returns_none():
    pg = FakePgStore()
    result = await resolve_filters(pg, None, None, None)
    assert result is None


@pytest.mark.asyncio
async def test_empty_filters_returns_none():
    pg = FakePgStore()
    result = await resolve_filters(pg, [], [], [])
    assert result is None


@pytest.mark.asyncio
async def test_dataset_ids_only():
    pg = FakePgStore(dataset_to_docs={"ds_001": ["doc_a", "doc_b"]})
    result = await resolve_filters(pg, ["ds_001"], None, None)
    assert result == {"doc_id": ["doc_a", "doc_b"]}


@pytest.mark.asyncio
async def test_doc_ids_only():
    pg = FakePgStore()
    result = await resolve_filters(pg, None, ["doc_x", "doc_y"], None)
    assert result == {"doc_id": ["doc_x", "doc_y"]}


@pytest.mark.asyncio
async def test_doc_names_only():
    pg = FakePgStore(name_to_docs={"report.pdf": ["doc_r"]})
    result = await resolve_filters(pg, None, None, ["report.pdf"])
    assert result == {"doc_id": ["doc_r"]}


@pytest.mark.asyncio
async def test_mixed_filters_merge_and_dedup():
    pg = FakePgStore(
        dataset_to_docs={"ds_001": ["doc_a", "doc_b"]},
        name_to_docs={"report.pdf": ["doc_a", "doc_c"]},
    )
    result = await resolve_filters(
        pg,
        ["ds_001"],
        ["doc_d"],
        ["report.pdf"],
    )
    assert set(result["doc_id"]) == {"doc_a", "doc_b", "doc_c", "doc_d"}


@pytest.mark.asyncio
async def test_dataset_ids_no_match_returns_empty_list():
    pg = FakePgStore(dataset_to_docs={})
    result = await resolve_filters(pg, ["ds_nonexist"], None, None)
    assert result is None


@pytest.mark.asyncio
async def test_doc_ids_sorted_output():
    pg = FakePgStore()
    result = await resolve_filters(pg, None, ["doc_z", "doc_a", "doc_m"], None)
    assert result["doc_id"] == ["doc_a", "doc_m", "doc_z"]
