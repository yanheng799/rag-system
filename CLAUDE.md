# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Production-grade RAG (Retrieval-Augmented Generation) system. Handles PDF, Word (.docx), Excel (.xlsx) document parsing, chunking, embedding, retrieval, and intelligent Q&A.

All documentation and code comments are in Chinese.

## Architecture

Five-layer architecture, each layer with a single responsibility:

1. **Ingestion (`src/ingestion/`)** — Document parsing (PDF/Word/Excel), paragraph boundary detection, table screenshots + rule-based descriptions, MixedChunk assembly, embedding, sync pipeline
2. **Storage (`src/storage/`)** — Milvus (vector DB), PostgreSQL (document/chunk records), MinIO (raw docs + table images). Abstract interfaces via `StoragePort` in `ports.py`
3. **Retrieval (`src/retrieval/`)** — Vector search, BM25 full-text search, hybrid search with RRF fusion, chunk merge. Pipeline design — each node independently replaceable
4. **Orchestration (`src/orchestration/`)** — RAGOrchestrator chains retrieval → prompt building → LLM call → response. Streaming + timeout support
5. **API (`src/api/`)** — FastAPI REST + WebSocket. Manual DI via `app.state`

## Key Design Decisions

- **MixedChunk**: A single chunk can contain interleaved text and table elements. `full_text` is vectorized; `image_url` stores table screenshots but never enters the LLM prompt
- **Chunk ID format**: `{doc_id}_p{page}_c{chunk_index}`
- **StoragePort pattern**: Abstract base classes (`VectorStorePort`, `DocumentStorePort`, `ObjectStorePort`, `CachePort`) in `src/storage/ports.py` decouple business logic from storage implementations
- **Signed URLs**: All `image_url` in API responses are MinIO signed URLs (1-hour expiry) via `SignedUrlService`. Internal paths never exposed externally
- **Parser plugin registry**: `BaseParser` implementations register by file type; `ParserRegistry` dispatches by extension
- **Paragraph boundary detection**: Custom logic groups flat Element lists by coordinate proximity + semantic cues before chunking
- **Table description**: Rule-based extraction only (列名:值 format). Qwen-VL deferred to later phase
- **Incremental Milvus updates**: New documents added without rebuilding the entire vector index

## Commands

```bash
# Run the API server
uvicorn src.main:app --reload

# Database migrations
alembic upgrade head
alembic downgrade -1

# Run tests
pytest
pytest tests/test_specific.py -k "test_name"

# Start infrastructure services
docker-compose up -d

# Initialize Milvus collection
python scripts/init_milvus.py

# Lint check
ruff check src/ tests/

# Auto-fix lint issues
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/documents` | Upload document (multipart/form-data) |
| GET | `/api/v1/documents` | List documents |
| POST | `/api/v1/query` | Query (JSON), returns answer + sources + signed image URLs |
| WebSocket | `/api/v1/query/ws` | Streaming query |
| POST | `/api/v1/retrieve` | Retrieval — specify strategy (vector/BM25/hybrid) and weights |
| GET | `/api/v1/chunks` | List chunks |
| GET | `/api/v1/datasets` | List datasets |

## Directory Structure

```
src/
├── main.py                  # FastAPI entry, manual DI assembly
├── config/settings.py       # pydantic-settings, .env
├── models/                  # Shared data models (chunks.py, documents.py)
├── api/
│   ├── routers/             # documents, query, retrieve, chunks, datasets
│   ├── schemas/             # Pydantic request/response
│   └── middleware/          # Error handler
├── ingestion/
│   ├── parsers/             # PDF, Word, Excel parsers + registry
│   ├── chunkers/            # Paragraph grouper, layout detector, chunk assembler
│   ├── table_processor/     # Screenshot, rule-based describer
│   ├── embedder.py          # DashScope embedding
│   └── pipeline.py          # Ingestion orchestration
├── storage/
│   ├── ports.py             # Abstract interfaces
│   ├── milvus_store.py      # pymilvus vector store
│   ├── pg_store.py          # SQLAlchemy async ORM
│   ├── pg_models.py         # ORM models
│   ├── oss_store.py         # MinIO
│   └── signed_url_service.py
├── retrieval/
│   ├── vector_search.py     # Vector search
│   ├── bm25_search.py       # BM25 full-text
│   ├── hybrid_search.py     # Hybrid search
│   ├── rrf_fusion.py        # RRF fusion
│   └── chunk_merge.py       # Chunk merge
└── orchestration/
    ├── orchestrator.py      # RAGOrchestrator
    ├── prompt_builder.py    # Prompt construction
    └── llm_client.py        # DashScope Qwen client
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11 |
| Web | FastAPI + Uvicorn |
| LLM | Qwen (DashScope API) |
| Embedding | text-embedding-v2 (1024-dim) |
| Vector DB | Milvus (HNSW, COSINE) |
| Relational DB | PostgreSQL + SQLAlchemy 2.0 async + Alembic |
| Object Storage | MinIO |
| PDF | pymupdf |
| Word | python-docx |
| Excel | openpyxl |
| Config | pydantic-settings + `.env` |

## Reference Documents

- `docs/RAG系统设计文档.md` — System design (architecture, data flow, tech selection)
- `docs/RAG系统开发任务清单.md` — Task breakdown with interface definitions and SQL DDL

## Out of Scope

- Frontend UI / admin dashboard
- Mobile adaptation
- Multi-tenant isolation
- Document version management
- User registration/management
- Load balancing / horizontal scaling
- CI/CD pipeline
- Legacy formats (.doc, .xls) — require LibreOffice

## 注意

- 在实现过程中及时提交 **feature**，确保测试用例通过
- 确保逻辑完整，不可使用 **TODO**
