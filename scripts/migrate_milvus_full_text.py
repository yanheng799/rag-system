"""Milvus Collection 迁移脚本：将 full_text 的 max_length 从 32768 扩大到 65535

流程：
1. 从旧 collection 查询全部数据
2. 创建临时 collection（新 schema，full_text max_length=65535）
3. 批量写入数据
4. 创建索引
5. 删除旧 collection
6. 将临时 collection 重命名为原名
"""

import logging
import sys
import time

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, Function, FunctionType, connections, utility

from src.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

OLD_COLLECTION = settings.milvus_collection
TEMP_COLLECTION = f"{OLD_COLLECTION}_tmp_{int(time.time())}"

BATCH_SIZE = 500

OUTPUT_FIELDS = [
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
    "embedding",
]


def build_new_schema() -> CollectionSchema:
    fields = [
        FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=settings.embedding_dimension),
        FieldSchema("chunk_id", DataType.VARCHAR, max_length=128),
        FieldSchema("doc_id", DataType.VARCHAR, max_length=64),
        FieldSchema("full_text", DataType.VARCHAR, max_length=65535, enable_analyzer=True),
        FieldSchema("chunk_type", DataType.VARCHAR, max_length=16),
        FieldSchema("elements", DataType.VARCHAR, max_length=65535),
        FieldSchema("image_urls", DataType.VARCHAR, max_length=2048),
        FieldSchema("source", DataType.VARCHAR, max_length=512),
        FieldSchema("page", DataType.INT32),
        FieldSchema("chunk_index", DataType.INT32),
        FieldSchema("char_count", DataType.INT32),
        FieldSchema("created_at", DataType.VARCHAR, max_length=32),
        FieldSchema("pages", DataType.VARCHAR, max_length=256),
        FieldSchema("group_id", DataType.VARCHAR, max_length=128),
        FieldSchema("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR),
    ]
    bm25_function = Function(
        name="text_bm25_emb",
        input_field_names=["full_text"],
        output_field_names=["sparse_embedding"],
        function_type=FunctionType.BM25,
    )
    return CollectionSchema(
        fields=fields,
        functions=[bm25_function],
        description="RAG 分块向量索引（含 BM25 全文检索）",
    )


def create_indexes(collection: Collection) -> None:
    hnsw_params = {
        "metric_type": settings.milvus_metric_type,
        "index_type": settings.milvus_index_type,
        "params": {
            "M": settings.milvus_hnsw_m,
            "efConstruction": settings.milvus_hnsw_ef_construction,
        },
    }
    collection.create_index(field_name="embedding", index_params=hnsw_params)

    sparse_params = {
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "BM25",
        "params": {
            "inverted_index_algo": "DAAT_MAXSCORE",
            "bm25_k1": settings.bm25_k1,
            "bm25_b": settings.bm25_b,
        },
    }
    collection.create_index(field_name="sparse_embedding", index_params=sparse_params)
    logger.info("索引创建完成")


def migrate():
    connections.connect(alias="default", host=settings.milvus_host, port=str(settings.milvus_port))

    if not utility.has_collection(OLD_COLLECTION):
        logger.error("旧 Collection '%s' 不存在，无需迁移", OLD_COLLECTION)
        sys.exit(1)

    old_col = Collection(OLD_COLLECTION)
    old_col.load()

    total = old_col.num_entities
    logger.info("旧 Collection '%s' 共 %d 条记录，开始迁移", OLD_COLLECTION, total)

    if total == 0:
        logger.info("旧 Collection 无数据，直接删除并重建")
        utility.drop_collection(OLD_COLLECTION)
        schema = build_new_schema()
        new_col = Collection(name=OLD_COLLECTION, schema=schema)
        create_indexes(new_col)
        new_col.load()
        logger.info("重建完成")
        return

    # 1. 创建临时 collection（清理上次失败的临时 collection）
    if utility.has_collection(TEMP_COLLECTION):
        logger.info("清理上次失败的临时 Collection '%s'", TEMP_COLLECTION)
        utility.drop_collection(TEMP_COLLECTION)
    schema = build_new_schema()
    temp_col = Collection(name=TEMP_COLLECTION, schema=schema)
    logger.info("临时 Collection '%s' 创建完成", TEMP_COLLECTION)

    # 2. 分批查询旧数据并写入新 collection
    # 使用 query 迭代，按 id 分页
    migrated = 0
    offset_id = 0

    while True:
        rows = old_col.query(
            expr=f"id > {offset_id}",
            output_fields=OUTPUT_FIELDS,
            limit=BATCH_SIZE,
            sort_by_primary_key=True,
        )
        if not rows:
            break

        data = []
        for row in rows:
            data.append({
                "embedding": row["embedding"],
                "chunk_id": row["chunk_id"],
                "doc_id": row["doc_id"],
                "full_text": row["full_text"],
                "chunk_type": row["chunk_type"],
                "elements": row["elements"],
                "image_urls": row["image_urls"],
                "source": row["source"],
                "page": row["page"],
                "chunk_index": row["chunk_index"],
                "char_count": row["char_count"],
                "created_at": row["created_at"],
                "pages": row["pages"],
                "group_id": row["group_id"],
            })
            offset_id = row["id"]

        temp_col.insert(data)
        migrated += len(data)
        logger.info("已迁移 %d / %d 条", migrated, total)

        if len(rows) < BATCH_SIZE:
            break

    temp_col.flush()
    logger.info("数据写入完成，共 %d 条", migrated)

    # 3. 创建索引并加载
    create_indexes(temp_col)
    temp_col.load()
    logger.info("临时 Collection 索引创建并加载完成")

    # 4. 删除旧 collection，重命名临时 collection
    logger.info("删除旧 Collection '%s' ...", OLD_COLLECTION)
    utility.drop_collection(OLD_COLLECTION)

    logger.info("重命名 '%s' → '%s'", TEMP_COLLECTION, OLD_COLLECTION)
    utility.rename_collection(TEMP_COLLECTION, OLD_COLLECTION)

    logger.info("迁移完成！共迁移 %d 条记录，full_text max_length 已扩大到 65535", migrated)


if __name__ == "__main__":
    migrate()
