"""跨检索/问答路由共享的工具：过滤条件解析。

此前 resolve_filters 定义在 query.py、被 retrieve.py 反向 import（坏味道）；
现统一收纳于此，供两个路由复用。doc_id → filename 的富化由检索层的
retrieval_service.build_doc_filename_map 提供（编排层也要用，不能放 API 层）。
"""

from __future__ import annotations


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
