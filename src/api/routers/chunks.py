"""分块管理路由：查看、合并、拆分、删除、关联"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.chunks import (
    ChunkDetail,
    ChunkListItem,
    ChunkListResponse,
    EditChunkRequest,
    EditChunkResponse,
    LinkRequest,
    LinkResponse,
    MergeRequest,
    MergeResponse,
    SplitChunkInfo,
    SplitRequest,
    SplitResponse,
    UnlinkRequest,
    UnlinkResponse,
)

router = APIRouter(prefix="/api/v1", tags=["分块管理"])

EMBEDDING_MAX_CHARS = 2048


def _detect_chunk_type(elements: list[dict]) -> str:
    """根据 elements 列表推断 chunk_type"""
    types = {e.get("type", "text") for e in elements}
    if len(types) > 1:
        return "mixed"
    return types.pop() if types else "text"


def _validate_merge_same_doc(chunks: list) -> str:
    """校验所有 chunk 属于同一文档，返回 doc_id"""
    doc_ids = {c.doc_id for c in chunks}
    if len(doc_ids) != 1:
        raise HTTPException(status_code=400, detail="只能合并同一文档的分块")
    return doc_ids.pop()


def _validate_merge_no_gap(
    body_chunk_ids: list[str],
    all_chunks: list,
) -> None:
    """校验选中的分块在文档分块序列中连续，中间无遗漏 chunk"""
    selected_ids = set(body_chunk_ids)
    sorted_all = sorted(all_chunks, key=lambda c: (c.page, c.chunk_index))

    # 找到选中分块在排序列表中的位置
    selected_positions = []
    for i, c in enumerate(sorted_all):
        if c.chunk_id in selected_ids:
            selected_positions.append(i)

    if not selected_positions:
        return

    first = selected_positions[0]
    last = selected_positions[-1]
    if len(selected_positions) != last - first + 1:
        for i in range(first, last + 1):
            if sorted_all[i].chunk_id not in selected_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"选定范围内存在未选中的分块: {sorted_all[i].chunk_id}，请先合并或移除",
                )


def _validate_char_limit(char_count: int) -> None:
    """校验文本长度不超过 embedding 限制"""
    if char_count > EMBEDDING_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"合并后文本长度 {char_count} 超过 embedding 限制 {EMBEDDING_MAX_CHARS} 字符",
        )


def _validate_split_at(split_at: int, num_elements: int) -> None:
    """校验 split_at 在合法范围内"""
    if split_at >= num_elements:
        raise HTTPException(
            status_code=400,
            detail=f"split_at={split_at} 超出元素范围 (共 {num_elements} 个元素)",
        )


async def _dissolve_orphan_groups(pg_store, milvus_store, embedder, deleted_chunk_ids: list[str]) -> None:
    """合并/删除后，若被删除的 chunk 所在组已无其他成员，则清理 PG 残留"""
    chunks = await pg_store.get_chunks_by_ids(deleted_chunk_ids)
    affected_group_ids = list({c.group_id for c in chunks if c.group_id})
    if not affected_group_ids:
        return

    for gid in affected_group_ids:
        siblings = milvus_store.fetch_by_group_ids([gid])
        surviving = [s for s in siblings if s["chunk_id"] not in deleted_chunk_ids]
        if surviving:
            continue
        # 组内已无成员，清理 PG 中残留的空组
        await pg_store.clear_group_id([gid])


async def _update_milvus_group_id(milvus_store, embedder, chunk_ids: list[str], new_group_id: str) -> None:
    """更新 Milvus 中指定 chunk 的 group_id（delete + re-insert）"""
    import json

    if milvus_store._collection is None:
        milvus_store.init_collection()
    collection = milvus_store._collection

    values = ", ".join(f'"{cid}"' for cid in chunk_ids)
    expr = f"chunk_id in [{values}]"
    results = collection.query(
        expr=expr,
        output_fields=[
            "chunk_id",
            "doc_id",
            "full_text",
            "chunk_type",
            "elements",
            "image_urls",
            "source",
            "page",
            "chunk_index",
            "char_count",
            "created_at",
            "pages",
            "group_id",
        ],
    )

    if not results:
        return

    texts = [r.get("full_text", "") for r in results]
    embeddings = embedder.embed(texts)

    milvus_store.delete_by_chunk_ids(chunk_ids)

    for r, emb in zip(results, embeddings, strict=False):
        # Milvus query 返回 JSON 字符串字段，需反序列化为 list 再传给 insert
        if isinstance(r.get("elements"), str):
            r["elements"] = json.loads(r["elements"])
        if isinstance(r.get("image_urls"), str):
            r["image_urls"] = json.loads(r["image_urls"])
        if isinstance(r.get("pages"), str):
            r["pages"] = json.loads(r["pages"])
        r["embedding"] = emb
        r["group_id"] = new_group_id
        milvus_store.insert([r])


async def _cleanup_oss_images(oss_store, image_urls: list[str]) -> None:
    """清理 OSS 图片文件，忽略失败"""
    for url in image_urls:
        with contextlib.suppress(Exception):
            oss_store.delete(url)


# ---- 列出文档分块 ----


@router.get(
    "/documents/{doc_id}/chunks",
    response_model=ChunkListResponse,
    summary="列出文档分块",
)
async def list_chunks(
    request: Request,
    doc_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """分页查询文档下的分块列表，按 page + chunk_index 排序"""
    pg_store = request.app.state.pg_store

    doc = await pg_store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    records, total = await pg_store.list_chunks_by_doc(doc_id, page=page, size=size)

    items = [
        ChunkListItem(
            chunk_id=r.chunk_id,
            doc_id=r.doc_id,
            chunk_type=r.chunk_type,
            page=r.page,
            chunk_index=r.chunk_index,
            char_count=r.char_count,
            full_text=r.full_text[:200],
            element_count=len(r.elements) if isinstance(r.elements, list) else 0,
            group_id=r.group_id,
            created_at=r.created_at,
        )
        for r in records
    ]

    return ChunkListResponse(total=total, page=page, size=size, items=items)


# ---- 查看分块详情 ----


@router.get(
    "/chunks/{chunk_id}",
    response_model=ChunkDetail,
    summary="查看分块详情",
)
async def get_chunk_detail(request: Request, chunk_id: str):
    """返回分块的完整 elements、full_text、image_urls"""
    pg_store = request.app.state.pg_store

    chunk = await pg_store.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="分块不存在")

    elements = chunk.elements if isinstance(chunk.elements, list) else []
    for elem in elements:
        if elem.get("image_url"):
            elem["image_url"] = f"/api/v1/images/{elem['image_url']}"

    raw_urls = chunk.image_urls if isinstance(chunk.image_urls, list) else []
    image_urls = [f"/api/v1/images/{url}" for url in raw_urls]

    return ChunkDetail(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        chunk_type=chunk.chunk_type,
        page=chunk.page,
        chunk_index=chunk.chunk_index,
        char_count=chunk.char_count,
        full_text=chunk.full_text,
        elements=elements,
        image_urls=image_urls,
        group_id=chunk.group_id,
        created_at=chunk.created_at,
    )


# ---- 编辑分块内容 ----


@router.put(
    "/chunks/{chunk_id}",
    response_model=EditChunkResponse,
    summary="编辑分块内容",
)
async def edit_chunk(request: Request, chunk_id: str, body: EditChunkRequest):
    """编辑分块文本内容，同步更新 PG + Milvus 向量和 BM25 索引"""
    import json

    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    chunk = await pg_store.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="分块不存在")

    new_text = body.full_text.strip()
    if not new_text:
        raise HTTPException(status_code=400, detail="文本内容不能为空")

    new_char_count = len(new_text)

    # 重新 embedding
    embedding = embedder.embed_single(new_text)

    # Milvus: delete + re-insert（保留其他字段，更新 full_text/embedding/char_count）
    if milvus_store._collection is None:
        milvus_store.init_collection()
    collection = milvus_store._collection

    results = collection.query(
        expr=f'chunk_id == "{chunk_id}"',
        output_fields=[
            "chunk_id", "doc_id", "chunk_type", "elements", "image_urls",
            "source", "page", "chunk_index", "created_at", "pages", "group_id",
        ],
    )

    milvus_store.delete_by_chunk_ids([chunk_id])

    if results:
        r = results[0]
        for field in ("elements", "image_urls", "pages"):
            if isinstance(r.get(field), str):
                r[field] = json.loads(r[field])
        r["full_text"] = new_text
        r["embedding"] = embedding
        r["char_count"] = new_char_count
        milvus_store.insert([r])

    # PG: 更新 full_text 和 char_count
    await pg_store.update_chunk_full_text(chunk_id, new_text, new_char_count)

    return EditChunkResponse(
        chunk_id=chunk_id,
        full_text=new_text,
        char_count=new_char_count,
    )


# ---- 删除单个分块 ----


@router.delete("/chunks/{chunk_id}", summary="删除单个分块")
async def delete_chunk(request: Request, chunk_id: str):
    """删除单个分块，同步清理 PG + Milvus + OSS 图片"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder
    oss_store = request.app.state.oss_store

    chunk = await pg_store.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="分块不存在")

    image_urls = chunk.image_urls if isinstance(chunk.image_urls, list) else []

    # 解散孤儿组（必须在删除前查询 group_id）
    await _dissolve_orphan_groups(pg_store, milvus_store, embedder, [chunk_id])

    milvus_store.delete_by_chunk_ids([chunk_id])
    await pg_store.delete_chunks_by_ids([chunk_id])

    # 清理 OSS 图片
    await _cleanup_oss_images(oss_store, image_urls)

    return {"message": "删除成功", "chunk_id": chunk_id}


# ---- 合并分块 ----


@router.post("/chunks/merge", response_model=MergeResponse, summary="合并分块")
async def merge_chunks(request: Request, body: MergeRequest):
    """将多个相邻分块合并为一个"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    # 1. 查询所有待合并 chunk
    chunks = await pg_store.get_chunks_by_ids(body.chunk_ids)
    if len(chunks) != len(body.chunk_ids):
        found_ids = {c.chunk_id for c in chunks}
        missing = [cid for cid in body.chunk_ids if cid not in found_ids]
        raise HTTPException(status_code=404, detail=f"分块不存在: {missing}")

    # 2. 校验：同一文档
    doc_id = _validate_merge_same_doc(chunks)

    # 3. 校验：选定范围内无遗漏 chunk
    sorted_chunks = sorted(chunks, key=lambda c: (c.page, c.chunk_index))

    all_in_range, _ = await pg_store.list_chunks_by_doc(doc_id, page=1, size=10000)
    _validate_merge_no_gap(body.chunk_ids, all_in_range)

    # 4. 合并数据
    merged_elements = []
    merged_image_urls = []
    for c in sorted_chunks:
        elems = c.elements if isinstance(c.elements, list) else []
        merged_elements.extend(elems)
        imgs = c.image_urls if isinstance(c.image_urls, list) else []
        merged_image_urls.extend(imgs)

    merged_full_text = "\n".join(e.get("content", "") for e in merged_elements)
    merged_char_count = len(merged_full_text)

    # 5. 校验：字数不超过 embedding 限制
    _validate_char_limit(merged_char_count)

    merged_page = sorted_chunks[0].page
    merged_chunk_index = sorted_chunks[0].chunk_index
    new_chunk_id = f"{doc_id}_m_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc = await pg_store.get_document(doc_id)
    source = doc.filename if doc else ""

    embedding = embedder.embed_single(merged_full_text)

    # 解散孤儿组（必须在删除前查询 group_id）
    await _dissolve_orphan_groups(pg_store, milvus_store, embedder, body.chunk_ids)

    milvus_store.delete_by_chunk_ids(body.chunk_ids)
    await pg_store.delete_chunks_by_ids(body.chunk_ids)

    pages = sorted({c.page for c in sorted_chunks})
    chunk_type = _detect_chunk_type(merged_elements)

    milvus_record = {
        "embedding": embedding,
        "chunk_id": new_chunk_id,
        "doc_id": doc_id,
        "full_text": merged_full_text,
        "chunk_type": chunk_type,
        "elements": merged_elements,
        "image_urls": merged_image_urls,
        "source": source,
        "page": merged_page,
        "chunk_index": merged_chunk_index,
        "char_count": merged_char_count,
        "created_at": now,
        "pages": pages,
        "group_id": "",
    }
    milvus_store.insert([milvus_record])

    from src.models.documents import ChunkRecord

    await pg_store.save_chunk(
        ChunkRecord(
            chunk_id=new_chunk_id,
            doc_id=doc_id,
            chunk_type=chunk_type,
            full_text=merged_full_text,
            elements=merged_elements,
            image_urls=merged_image_urls,
            page=merged_page,
            chunk_index=merged_chunk_index,
            char_count=merged_char_count,
            group_id="",
        )
    )

    return MergeResponse(
        merged_chunk_id=new_chunk_id,
        deleted_chunk_ids=body.chunk_ids,
        char_count=merged_char_count,
    )


# ---- 拆分分块 ----


@router.post(
    "/chunks/{chunk_id}/split",
    response_model=SplitResponse,
    summary="拆分分块",
)
async def split_chunk(request: Request, chunk_id: str, body: SplitRequest):
    """将一个分块按元素索引拆分为两个"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    chunk = await pg_store.get_chunk(chunk_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail="分块不存在")

    elements = chunk.elements if isinstance(chunk.elements, list) else []

    _validate_split_at(body.split_at, len(elements))

    elems_a = elements[: body.split_at]
    elems_b = elements[body.split_at :]

    full_text_a = "\n".join(e.get("content", "") for e in elems_a)
    full_text_b = "\n".join(e.get("content", "") for e in elems_b)

    doc_id = chunk.doc_id
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    chunk_a_id = f"{doc_id}_m_{uuid.uuid4().hex[:8]}"
    chunk_b_id = f"{doc_id}_m_{uuid.uuid4().hex[:8]}"

    shared_group_id = ""
    if body.link_group:
        shared_group_id = f"{doc_id}_g{uuid.uuid4().hex[:8]}"

    image_urls_a = [e.get("image_url") for e in elems_a if e.get("image_url")]
    image_urls_b = [e.get("image_url") for e in elems_b if e.get("image_url")]
    char_count_a = len(full_text_a)
    char_count_b = len(full_text_b)
    chunk_type_a = _detect_chunk_type(elems_a)
    chunk_type_b = _detect_chunk_type(elems_b)

    doc = await pg_store.get_document(doc_id)
    source = doc.filename if doc else ""

    embeddings = embedder.embed([full_text_a, full_text_b])

    milvus_store.delete_by_chunk_ids([chunk_id])
    await pg_store.delete_chunks_by_ids([chunk_id])

    from src.models.documents import ChunkRecord

    milvus_records = []
    pg_records = []

    for cid, elems, ft, ccount, imgs, ctype, emb, cidx in [
        (chunk_a_id, elems_a, full_text_a, char_count_a, image_urls_a, chunk_type_a, embeddings[0], chunk.chunk_index),
        (
            chunk_b_id,
            elems_b,
            full_text_b,
            char_count_b,
            image_urls_b,
            chunk_type_b,
            embeddings[1],
            chunk.chunk_index + 1,
        ),
    ]:
        milvus_records.append(
            {
                "embedding": emb,
                "chunk_id": cid,
                "doc_id": doc_id,
                "full_text": ft,
                "chunk_type": ctype,
                "elements": elems,
                "image_urls": imgs,
                "source": source,
                "page": chunk.page,
                "chunk_index": cidx,
                "char_count": ccount,
                "created_at": now,
                "pages": [chunk.page],
                "group_id": shared_group_id,
            }
        )
        pg_records.append(
            ChunkRecord(
                chunk_id=cid,
                doc_id=doc_id,
                chunk_type=ctype,
                full_text=ft,
                elements=elems,
                image_urls=imgs,
                page=chunk.page,
                chunk_index=cidx,
                char_count=ccount,
                group_id=shared_group_id,
            )
        )

    milvus_store.insert(milvus_records)
    await pg_store.save_chunks_batch(pg_records)

    return SplitResponse(
        chunk_a=SplitChunkInfo(
            chunk_id=chunk_a_id,
            char_count=char_count_a,
            element_count=len(elems_a),
        ),
        chunk_b=SplitChunkInfo(
            chunk_id=chunk_b_id,
            char_count=char_count_b,
            element_count=len(elems_b),
        ),
        deleted_chunk_id=chunk_id,
    )


# ---- 关联分块 ----


@router.post("/chunks/link", response_model=LinkResponse, summary="关联分块")
async def link_chunks(request: Request, body: LinkRequest):
    """将多个分块关联到同一 group_id"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    chunks = await pg_store.get_chunks_by_ids(body.chunk_ids)
    if len(chunks) != len(body.chunk_ids):
        found_ids = {c.chunk_id for c in chunks}
        missing = [cid for cid in body.chunk_ids if cid not in found_ids]
        raise HTTPException(status_code=404, detail=f"分块不存在: {missing}")

    doc_ids = {c.doc_id for c in chunks}
    if len(doc_ids) != 1:
        raise HTTPException(status_code=400, detail="只能关联同一文档的分块")

    doc_id = doc_ids.pop()
    new_group_id = f"{doc_id}_g{uuid.uuid4().hex[:8]}"

    # 如果某些 chunk 已有 group_id，先解散旧组
    old_group_ids = {c.group_id for c in chunks if c.group_id}
    if old_group_ids:
        # 解散旧组中不在本次关联列表里的兄弟
        all_old_group_chunks = []
        for gid in old_group_ids:
            siblings = milvus_store.fetch_by_group_ids([gid])
            all_old_group_chunks.extend(siblings)
        linked_set = set(body.chunk_ids)
        orphan_ids = []
        for s in all_old_group_chunks:
            if s["chunk_id"] not in linked_set:
                orphan_ids.append(s["chunk_id"])

        if orphan_ids:
            # PG 清空孤儿 group_id
            await pg_store.clear_group_ids_by_ids(orphan_ids)
            # Milvus 重新插入
            await _update_milvus_group_id(milvus_store, embedder, orphan_ids, "")

    # PG: 更新 group_id
    await pg_store.update_chunks_group_id(body.chunk_ids, new_group_id)

    # Milvus: 更新 group_id
    await _update_milvus_group_id(milvus_store, embedder, body.chunk_ids, new_group_id)

    return LinkResponse(group_id=new_group_id, chunk_ids=body.chunk_ids)


# ---- 取消关联 ----


@router.post("/chunks/unlink", response_model=UnlinkResponse, summary="取消分块关联")
async def unlink_chunks(request: Request, body: UnlinkRequest):
    """取消分块的 group_id 关联"""
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    embedder = request.app.state.embedder

    chunks = await pg_store.get_chunks_by_ids(body.chunk_ids)
    if len(chunks) != len(body.chunk_ids):
        found_ids = {c.chunk_id for c in chunks}
        missing = [cid for cid in body.chunk_ids if cid not in found_ids]
        raise HTTPException(status_code=404, detail=f"分块不存在: {missing}")

    # 过滤出有 group_id 的 chunk
    to_unlink = [c for c in chunks if c.group_id]
    if not to_unlink:
        return UnlinkResponse(unlinked_count=0)

    unlink_ids = [c.chunk_id for c in to_unlink]

    # PG: 清空 group_id
    await pg_store.clear_group_ids_by_ids(unlink_ids)

    # Milvus: 更新 group_id
    await _update_milvus_group_id(milvus_store, embedder, unlink_ids, "")

    return UnlinkResponse(unlinked_count=len(unlink_ids))
