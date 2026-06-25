"""跨检索/问答路由共享的工具：过滤条件解析 + 文档文件名映射。

此前 resolve_filters 定义在 query.py、被 retrieve.py 反向 import（坏味道）；
现统一收纳于此，供两个路由复用。build_doc_filename_map 同样是两端检索后都要做的
doc_id → 真实 filename 富化，一并集中。
"""

from __future__ import annotations

from src.models.chunks import RetrievedChunk


async def resolve_filters(
    pg_store,
    dataset_ids,
    doc_ids,
    doc_names,
    org_id: str | None = None,
) -> dict | None:
    """将 dataset_ids / doc_ids / doc_names 解析为 Milvus 过滤条件，按 org_id 限定范围"""
    sets: list[set[str]] = []

    if dataset_ids:
        ids = await pg_store.get_doc_ids_by_dataset_ids(dataset_ids, org_id=org_id)
        sets.append(set(ids))

    if doc_ids:
        sets.append(set(doc_ids))

    if doc_names:
        ids = await pg_store.get_doc_ids_by_filenames(doc_names, org_id=org_id)
        sets.append(set(ids))

    if not sets:
        return None

    result = sets[0]
    for s in sets[1:]:
        result &= s

    if not result:
        return None
    return {"doc_id": sorted(result)}


async def build_doc_filename_map(
    doc_store,
    chunks: list[RetrievedChunk],
) -> dict[str, str]:
    """批量查询 chunks 涉及文档的真实 filename，返回 doc_id -> filename 映射。"""
    unique_doc_ids = list({c.metadata.doc_id for c in chunks})
    mapping: dict[str, str] = {}
    for did in unique_doc_ids:
        doc = await doc_store.get_document(did)
        if doc:
            mapping[did] = doc.filename
    return mapping
