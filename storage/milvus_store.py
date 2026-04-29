"""Milvus 向量数据库存储实现"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections
from pymilvus import utility

from config.settings import settings
from storage.ports import VectorStorePort

logger = logging.getLogger(__name__)


class MilvusStore(VectorStorePort):
    """Milvus 向量存储实现"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection_name: Optional[str] = None,
    ):
        self._host = host or settings.milvus_host
        self._port = port or settings.milvus_port
        self._collection_name = collection_name or settings.milvus_collection
        self._collection: Optional[Collection] = None

    def _connect(self) -> None:
        """建立 Milvus 连接"""
        connections.connect(
            alias="default",
            host=self._host,
            port=str(self._port),
        )

    def _get_schema(self) -> CollectionSchema:
        """定义 Collection Schema"""
        fields = [
            FieldSchema(
                "id", DataType.INT64, is_primary=True, auto_id=True
            ),
            FieldSchema(
                "embedding", DataType.FLOAT_VECTOR, dim=settings.embedding_dimension
            ),
            FieldSchema("chunk_id", DataType.VARCHAR, max_length=128),
            FieldSchema("doc_id", DataType.VARCHAR, max_length=64),
            FieldSchema("full_text", DataType.VARCHAR, max_length=8192),
            FieldSchema("chunk_type", DataType.VARCHAR, max_length=16),
            FieldSchema("elements", DataType.VARCHAR, max_length=16384),
            FieldSchema("image_urls", DataType.VARCHAR, max_length=2048),
            FieldSchema("source", DataType.VARCHAR, max_length=512),
            FieldSchema("page", DataType.INT32),
            FieldSchema("chunk_index", DataType.INT32),
            FieldSchema("char_count", DataType.INT32),
            FieldSchema("created_at", DataType.VARCHAR, max_length=32),
        ]
        return CollectionSchema(fields=fields, description="RAG 分块向量索引")

    def init_collection(self) -> None:
        """初始化 Collection"""
        self._connect()
        if utility.has_collection(self._collection_name):
            logger.info("Milvus Collection '%s' 已存在", self._collection_name)
            self._collection = Collection(self._collection_name)
        else:
            schema = self._get_schema()
            self._collection = Collection(
                name=self._collection_name, schema=schema
            )
            # 创建 HNSW 索引
            index_params = {
                "metric_type": settings.milvus_metric_type,
                "index_type": settings.milvus_index_type,
                "params": {
                    "M": settings.milvus_hnsw_m,
                    "efConstruction": settings.milvus_hnsw_ef_construction,
                },
            }
            self._collection.create_index(
                field_name="embedding", index_params=index_params
            )
            logger.info(
                "Milvus Collection '%s' 创建成功，索引类型: %s",
                self._collection_name,
                settings.milvus_index_type,
            )
        self._collection.load()

    def insert(self, records: list[dict]) -> list[int]:
        """批量插入向量记录"""
        if self._collection is None:
            self.init_collection()

        data = [
            {
                "embedding": r["embedding"],
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "full_text": r["full_text"],
                "chunk_type": r["chunk_type"],
                "elements": json.dumps(r["elements"], ensure_ascii=False),
                "image_urls": json.dumps(r.get("image_urls", []), ensure_ascii=False),
                "source": r["source"],
                "page": r["page"],
                "chunk_index": r["chunk_index"],
                "char_count": r["char_count"],
                "created_at": r["created_at"],
            }
            for r in records
        ]
        result = self._collection.insert(data)
        self._collection.flush()
        logger.info("Milvus 插入 %d 条记录", len(data))
        return result.primary_keys

    def search(
        self,
        embedding: list[float],
        top_k: int = 50,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """向量检索"""
        if self._collection is None:
            self.init_collection()

        search_params = {"metric_type": "COSINE", "params": {"ef": 128}}
        expr = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if isinstance(value, list):
                    values_str = ", ".join(f'"{v}"' for v in value)
                    conditions.append(f"{key} in [{values_str}]")
                else:
                    conditions.append(f'{key} == "{value}"')
            expr = " and ".join(conditions)

        results = self._collection.search(
            data=[embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            expr=expr,
            output_fields=[
                "chunk_id", "doc_id", "full_text", "chunk_type",
                "elements", "image_urls", "source", "page",
                "chunk_index", "char_count", "created_at",
            ],
        )

        hits = []
        for hit in results[0]:
            record = {
                "id": hit.id,
                "score": hit.score,
                "chunk_id": hit.entity.get("chunk_id"),
                "doc_id": hit.entity.get("doc_id"),
                "full_text": hit.entity.get("full_text"),
                "chunk_type": hit.entity.get("chunk_type"),
                "elements": json.loads(hit.entity.get("elements", "[]")),
                "image_urls": json.loads(hit.entity.get("image_urls", "[]")),
                "source": hit.entity.get("source"),
                "page": hit.entity.get("page"),
                "chunk_index": hit.entity.get("chunk_index"),
                "char_count": hit.entity.get("char_count"),
                "created_at": hit.entity.get("created_at"),
            }
            hits.append(record)
        return hits

    def delete_by_doc_id(self, doc_id: str) -> None:
        """按文档 ID 删除所有向量记录"""
        if self._collection is None:
            self.init_collection()
        self._collection.delete(f'doc_id == "{doc_id}"')
        logger.info("Milvus 删除 doc_id=%s 的所有记录", doc_id)
