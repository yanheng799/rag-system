"""数据集管理路由"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas.datasets import (
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdateRequest,
)

router = APIRouter(prefix="/api/v1/datasets", tags=["数据集管理"])


@router.post("", response_model=DatasetResponse, status_code=201, summary="创建数据集")
async def create_dataset(request: Request, body: DatasetCreateRequest):
    pg_store = request.app.state.pg_store
    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"

    try:
        record = await pg_store.create_dataset(
            dataset_id=dataset_id,
            name=body.name,
            description=body.description,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="数据集名称已存在")

    doc_count = await pg_store.count_docs_by_dataset(dataset_id)
    return DatasetResponse(
        dataset_id=record.dataset_id,
        name=record.name,
        description=record.description,
        doc_count=doc_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=DatasetListResponse, summary="数据集列表")
async def list_datasets(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    pg_store = request.app.state.pg_store
    records, total = await pg_store.list_datasets(page=page, size=size)

    items = []
    for r in records:
        doc_count = await pg_store.count_docs_by_dataset(r.dataset_id)
        items.append(
            DatasetResponse(
                dataset_id=r.dataset_id,
                name=r.name,
                description=r.description,
                doc_count=doc_count,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return DatasetListResponse(total=total, page=page, size=size, items=items)


@router.get(
    "/{dataset_id}", response_model=DatasetResponse, summary="数据集详情"
)
async def get_dataset(request: Request, dataset_id: str):
    pg_store = request.app.state.pg_store
    record = await pg_store.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="数据集不存在")

    doc_count = await pg_store.count_docs_by_dataset(dataset_id)
    return DatasetResponse(
        dataset_id=record.dataset_id,
        name=record.name,
        description=record.description,
        doc_count=doc_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.patch(
    "/{dataset_id}", response_model=DatasetResponse, summary="更新数据集"
)
async def update_dataset(
    request: Request, dataset_id: str, body: DatasetUpdateRequest
):
    pg_store = request.app.state.pg_store
    existing = await pg_store.get_dataset(dataset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="数据集不存在")

    try:
        record = await pg_store.update_dataset(
            dataset_id=dataset_id,
            name=body.name,
            description=body.description,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="数据集名称已存在")

    doc_count = await pg_store.count_docs_by_dataset(dataset_id)
    return DatasetResponse(
        dataset_id=record.dataset_id,
        name=record.name,
        description=record.description,
        doc_count=doc_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/{dataset_id}", summary="删除数据集")
async def delete_dataset(
    request: Request,
    dataset_id: str,
    force: bool = Query(default=False),
):
    pg_store = request.app.state.pg_store
    milvus_store = request.app.state.milvus_store
    oss_store = request.app.state.oss_store

    existing = await pg_store.get_dataset(dataset_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="数据集不存在")

    doc_count = await pg_store.count_docs_by_dataset(dataset_id)
    if doc_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail=f"数据集下还有 {doc_count} 个文档，请先删除文档或使用 force=true",
        )

    # 级联删除：向量、OSS 文件、PG 记录
    if doc_count > 0:
        from sqlalchemy import select
        from src.storage.pg_models import DocumentORM

        async with pg_store.get_session() as session:
            result = await session.execute(
                select(DocumentORM.doc_id, DocumentORM.raw_file_url).where(
                    DocumentORM.dataset_id == dataset_id
                )
            )
            docs = result.all()

        for doc_id, raw_file_url in docs:
            milvus_store.delete_by_doc_id(doc_id)
            if raw_file_url:
                try:
                    oss_store.delete(raw_file_url)
                except Exception:
                    pass

    await pg_store.delete_dataset(dataset_id)

    return {"message": "删除成功", "dataset_id": dataset_id}
