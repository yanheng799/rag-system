"""Milvus org_id 字段迁移脚本

策略：
1. 新建带 org_id 字段的 collection（{coll_name}_v2）
2. 读取旧 collection 全量数据
3. 逐批写入新 collection（org_id 从 PG 文档表查询，查不到填空）
4. 验证数据量一致
5. 删除旧 collection，重命名新 collection
"""

from __future__ import annotations

import logging
import sys
import time

from pymilvus import Collection, connections, utility

from src.config.settings import settings
from src.storage.milvus_store import FULL_TEXT_MAX_LENGTH, MilvusStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 100


def _get_org_id_map() -> dict[str, str]:
    """从 PG 查询所有文档的 doc_id → org_id 映射"""
    try:
        import asyncio
        from src.storage.pg_store import PgStore

        async def _query():
            pg = PgStore()
            async with pg._session_factory() as session:
                from sqlalchemy import select
                from src.storage.pg_models import DocumentORM

                result = await session.execute(
                    select(DocumentORM.doc_id, DocumentORM.org_id)
                )
                return {row[0]: row[1] or "" for row in result.all()}

        return asyncio.run(_query())
    except Exception as e:
        logger.warning("PG 查询失败，所有迁移数据的 org_id 将为空: %s", e)
        return {}


def main():
    old_coll_name = settings.milvus_collection
    new_coll_name = f"{old_coll_name}_v2"

    # 1. 连接
    connections.connect(host=settings.milvus_host, port=str(settings.milvus_port))
    logger.info("Milvus 连接成功: %s:%s", settings.milvus_host, settings.milvus_port)

    if not utility.has_collection(old_coll_name):
        logger.info("Collection '%s' 不存在，直接创建新 collection", old_coll_name)
        store = MilvusStore()
        store.init_collection()
        logger.info("新 collection '%s' 创建完成", old_coll_name)
        return

    # 2. 创建新 collection
    if utility.has_collection(new_coll_name):
        logger.error("新 collection '%s' 已存在，请先删除或重命名", new_coll_name)
        sys.exit(1)

    store = MilvusStore(collection_name=new_coll_name)
    store.init_collection()

    # 3. 读取旧 collection 全量数据
    old_coll = Collection(old_coll_name)
    old_coll.load()
    total = old_coll.num_entities
    logger.info("旧 collection '%s' 共 %d 条记录", old_coll_name, total)

    if total == 0:
        logger.info("旧 collection 为空，直接切换")
        utility.drop_collection(old_coll_name)
        utility.rename_collection(new_coll_name, old_coll_name)
        logger.info("迁移完成（空 collection）")
        return

    # 4. 获取 org_id 映射
    org_id_map = _get_org_id_map()
    logger.info("从 PG 获取 %d 条 doc_id→org_id 映射", len(org_id_map))

    # 5. 按游标逐批迁移
    migrated = 0
    expr = "id >= 0"
    new_coll = Collection(new_coll_name)
    new_coll.load()

    while migrated < total:
        results = old_coll.query(
            expr=expr,
            output_fields=[
                "embedding", "chunk_id", "doc_id", "full_text", "chunk_type",
                "elements", "image_urls", "source", "page", "chunk_index",
                "char_count", "created_at", "pages", "group_id",
            ],
            limit=BATCH_SIZE,
        )
        if not results:
            break

        insert_data = []
        for hit in results:
            doc_id = hit.get("doc_id", "")
            org_id = org_id_map.get(doc_id, "")
            text = hit.get("full_text", "")
            if len(text) > FULL_TEXT_MAX_LENGTH:
                text = text[:FULL_TEXT_MAX_LENGTH]
            insert_data.append({
                "embedding": hit.get("embedding"),
                "chunk_id": hit.get("chunk_id"),
                "doc_id": doc_id,
                "full_text": text,
                "chunk_type": hit.get("chunk_type", ""),
                "elements": hit.get("elements", "[]"),
                "image_urls": hit.get("image_urls", "[]"),
                "source": hit.get("source", ""),
                "page": hit.get("page", 0),
                "chunk_index": hit.get("chunk_index", 0),
                "char_count": hit.get("char_count", 0),
                "created_at": hit.get("created_at", ""),
                "pages": hit.get("pages", "[]"),
                "group_id": hit.get("group_id", ""),
                "org_id": org_id,
            })

        new_coll.insert(insert_data)
        new_coll.flush()

        last_id = results[-1].get("id", 0)
        expr = f"id > {last_id}"
        migrated += len(results)
        logger.info("已迁移 %d/%d", migrated, total)

    # 6. 验证数据量
    new_total = new_coll.num_entities
    logger.info("旧 collection: %d, 新 collection: %d", total, new_total)
    if new_total != total:
        logger.error("数据量不一致!")
        sys.exit(1)

    # 7. 切换：删除旧 collection，重命名新 collection
    logger.info("删除旧 collection '%s'...", old_coll_name)
    utility.drop_collection(old_coll_name)
    logger.info("重命名 '%s' → '%s'", new_coll_name, old_coll_name)
    utility.rename_collection(new_coll_name, old_coll_name)

    logger.info("Milvus org_id 迁移完成!")
    logger.info("⚠️  请重启服务以使用新的 collection schema")


if __name__ == "__main__":
    main()
