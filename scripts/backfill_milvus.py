"""从 PG 补齐 Milvus 缺失的向量数据

用法: PYTHONPATH=. python scripts/backfill_milvus.py [--fix-bad-pages]
  默认: 检测缺失的 doc_id 并补齐
  --fix-bad-pages: 修复 pages 字段双重序列化的问题
"""

import asyncio
import json
import logging
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from src.config.settings import settings
from src.ingestion.embedder import Embedder
from src.storage.milvus_store import MilvusStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _parse_pages(raw) -> list[int]:
    """确保 pages 始终为 list[int]，兼容字符串/双重序列化"""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return json.loads(parsed)
    return []


async def fix_bad_pages(milvus: MilvusStore) -> None:
    """修复 pages 字段双重序列化的记录：删除后重新插入"""
    coll = milvus._collection
    # 找出 pages 值以引号开头的记录（双重序列化特征）
    results = coll.query(expr='', output_fields=['chunk_id', 'doc_id', 'pages', 'embedding', 'full_text', 'chunk_type', 'elements', 'image_urls', 'source', 'page', 'chunk_index', 'char_count', 'created_at', 'group_id', 'org_id'], limit=10000)
    bad = [r for r in results if isinstance(r.get('pages'), str) and r['pages'].startswith('"')]
    if not bad:
        logger.info("无异常 pages 数据")
        return
    logger.info("发现 %d 条 pages 异常记录", len(bad))

    # 按 doc_id 分组处理
    embedder = Embedder()
    doc_ids = sorted(set(r['doc_id'] for r in bad))
    for did in doc_ids:
        doc_bad = [r for r in bad if r['doc_id'] == did]
        chunk_ids = [r['chunk_id'] for r in doc_bad]
        logger.info("修复 doc_id=%s: %d 条异常记录", did, len(doc_bad))

        # 删除异常记录
        milvus.delete_by_chunk_ids(chunk_ids)

        # 重新插入（pages 修正为 list）
        records = []
        for r in doc_bad:
            records.append({
                'embedding': r['embedding'],
                'chunk_id': r['chunk_id'],
                'doc_id': r['doc_id'],
                'full_text': r['full_text'],
                'chunk_type': r['chunk_type'],
                'elements': json.loads(r['elements']) if isinstance(r['elements'], str) else r['elements'],
                'image_urls': json.loads(r['image_urls']) if isinstance(r['image_urls'], str) else r['image_urls'],
                'source': r['source'],
                'page': r['page'],
                'chunk_index': r['chunk_index'],
                'char_count': r['char_count'],
                'created_at': r['created_at'],
                'pages': _parse_pages(r['pages']),
                'group_id': r.get('group_id', ''),
                'org_id': r.get('org_id', ''),
            })
        milvus.insert(records)
        logger.info("doc_id=%s: 重新插入 %d 条记录", did, len(records))


async def backfill_missing(milvus: MilvusStore) -> None:
    """补齐 Milvus 中缺失的 doc_id"""
    existing = milvus._collection.query(expr="", output_fields=["doc_id"], limit=10000)
    milvus_doc_ids = set(r["doc_id"] for r in existing)
    logger.info("Milvus 已有 doc_id: %s", milvus_doc_ids)

    engine = create_async_engine(settings.postgres_dsn)
    pg_docs = {}
    async with AsyncSession(engine) as session:
        result = await session.execute(
            text("SELECT doc_id, filename, org_id FROM rag_documents WHERE status = 'done'")
        )
        for row in result.fetchall():
            pg_docs[row[0]] = {"filename": row[1], "org_id": row[2]}

    missing_doc_ids = set(pg_docs.keys()) - milvus_doc_ids
    if not missing_doc_ids:
        logger.info("无缺失数据，退出")
        await engine.dispose()
        return

    logger.info("需要补齐 %d 个文档: %s", len(missing_doc_ids), missing_doc_ids)

    embedder = Embedder()
    async with AsyncSession(engine) as session:
        for doc_id in sorted(missing_doc_ids):
            info = pg_docs[doc_id]
            org_id = info["org_id"] or ""
            filename = info["filename"]
            logger.info("处理 doc_id=%s, org_id=%s, filename=%s", doc_id, org_id, filename)

            result = await session.execute(
                text(
                    "SELECT chunk_id, doc_id, chunk_type, full_text, elements, image_urls, "
                    "page, chunk_index, char_count, group_id, created_at "
                    "FROM rag_chunks WHERE doc_id = :doc_id ORDER BY page, chunk_index"
                ),
                {"doc_id": doc_id},
            )
            rows = result.fetchall()
            if not rows:
                logger.warning("doc_id=%s 无 chunks，跳过", doc_id)
                continue

            non_empty = [r for r in rows if (r[3] or "").strip()]
            if not non_empty:
                logger.warning("doc_id=%s 所有 chunks 为空，跳过", doc_id)
                continue

            logger.info("doc_id=%s: %d 个非空 chunks", doc_id, len(non_empty))

            texts = [r[3] for r in non_empty]
            embeddings = []
            batch_size = 25
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_emb = await asyncio.to_thread(embedder.embed_for_index, batch)
                embeddings.extend(batch_emb)
                logger.info("  embedding 批次 %d/%d", i // batch_size + 1, (len(texts) + batch_size - 1) // batch_size)

            records = []
            for row, embedding in zip(non_empty, embeddings):
                chunk_id, doc_id_r, chunk_type, full_text, elements, image_urls, page, chunk_index, char_count, group_id, created_at = row
                records.append({
                    "embedding": embedding,
                    "chunk_id": chunk_id,
                    "doc_id": doc_id_r,
                    "full_text": full_text,
                    "chunk_type": chunk_type or "text",
                    "elements": elements if isinstance(elements, list) else json.loads(elements or "[]"),
                    "image_urls": image_urls if isinstance(image_urls, list) else json.loads(image_urls or "[]"),
                    "source": filename,
                    "page": page,
                    "chunk_index": chunk_index,
                    "char_count": char_count or len(full_text),
                    "created_at": created_at.isoformat() if created_at else "",
                    "pages": [page],
                    "group_id": group_id or "",
                    "org_id": org_id,
                })

            milvus.insert(records)
            logger.info("doc_id=%s: 已写入 %d 条向量记录", doc_id, len(records))

    await engine.dispose()
    logger.info("补齐完成")


async def main():
    milvus = MilvusStore()
    milvus.init_collection()

    if "--fix-bad-pages" in sys.argv:
        await fix_bad_pages(milvus)
    else:
        await backfill_missing(milvus)


if __name__ == "__main__":
    asyncio.run(main())
