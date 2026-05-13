# RAG 问答系统

生产级 RAG（检索增强生成）系统，支持 PDF、Word、Excel 文档的上传、解析、检索与智能问答。

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI + Uvicorn |
| LLM | Qwen（DashScope API） |
| Embedding | text-embedding-v2（1024 维） |
| 向量数据库 | Milvus 2.5 |
| 关系数据库 | PostgreSQL 16 |
| 对象存储 | MinIO |
| 缓存 | Redis 7（Phase 4 使用） |
| PDF 解析 | pymupdf |
| Word 解析 | python-docx |
| Excel 解析 | openpyxl |

## 环境要求

- Python >= 3.11
- Docker & Docker Compose
- DashScope API Key（[申请地址](https://dashscope.console.aliyun.com/)）

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/rag-system.git
cd rag-system
```

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -e ".[dev]"
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入 DashScope API Key：

```
DASHSCOPE_API_KEY=sk-your-actual-key
```

其余配置保持默认即可用于本地开发。

### 4. 启动基础设施

```bash
docker-compose up -d
```

等待所有服务健康就绪（约 30 秒）：

```bash
docker-compose ps
```

确认 postgres、milvus、minio、redis 状态均为 `healthy`。

### 5. 初始化数据库

```bash
alembic upgrade head
```

### 6. 初始化 Milvus Collection

```bash
python scripts/init_milvus.py
```

### 7. 启动 API 服务

```bash
uvicorn src.main:app --reload
```

服务启动后访问：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/documents` | 上传文档（multipart/form-data） |
| POST | `/api/v1/query` | 问答查询，返回答案 + 来源 + 签名图片 URL |
| WebSocket | `/api/v1/query/ws` | 流式问答 |
| POST | `/api/v1/retrieve` | 检索接口，支持 vector/BM25/hybrid 策略 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/chunks` | 分块列表 |
| GET | `/api/v1/datasets` | 数据集列表 |

## 运行测试

```bash
# 运行全部测试
pytest

# 运行指定测试
pytest tests/unit/test_xxx.py -k "test_name"
```

## 代码格式检查

使用 [Ruff](https://docs.astral.sh/ruff/) 进行 lint 检查和代码格式化（已包含在 dev 依赖中）。

```bash
# 检查代码问题
ruff check src/ tests/

# 自动修复可修复的问题
ruff check src/ tests/ --fix

# 格式化代码
ruff format src/ tests/
```

## 项目结构

```
src/
├── main.py                # FastAPI 入口，手动 DI 组装
├── config/settings.py     # pydantic-settings 配置
├── models/                # 共享数据模型
├── api/                   # API 层
│   ├── routers/           # 路由（documents, query, retrieve, chunks, datasets）
│   ├── schemas/           # Pydantic 请求/响应模型
│   └── middleware/        # 错误处理中间件
├── ingestion/             # 数据摄入层
│   ├── parsers/           # 文档解析器（PDF, Word, Excel）+ 注册表
│   ├── chunkers/          # 段落分组 + 分块组装
│   ├── table_processor/   # 表格截图 + 语义描述
│   ├── embedder.py        # DashScope Embedding 封装
│   └── pipeline.py        # 摄入流程编排
├── storage/               # 存储层
│   ├── ports.py           # 抽象接口（StoragePort 模式）
│   ├── milvus_store.py    # Milvus 向量存储
│   ├── pg_store.py        # PostgreSQL 异步 ORM
│   ├── oss_store.py       # MinIO 对象存储
│   └── signed_url_service.py
├── retrieval/             # 检索层
│   ├── vector_search.py   # 向量检索
│   ├── bm25_search.py     # BM25 全文检索
│   └── hybrid_search.py   # 混合检索
└── orchestration/         # 编排层
    ├── orchestrator.py    # RAGOrchestrator
    ├── prompt_builder.py  # Prompt 构建
    └── llm_client.py      # DashScope Qwen 客户端
```

## 基础设施服务

| 服务 | 默认端口 | 说明 |
|------|---------|------|
| PostgreSQL | 5432 | 文档/分块元数据、查询日志 |
| Milvus | 19530 | 向量索引与检索 |
| MinIO | 9000 / 9001 | 原始文档 + 表格截图存储（9001 为管理控制台） |
| Redis | 6379 | Phase 4 启用 |

MinIO 管理控制台：http://localhost:9001（默认账号 `minio` / `miniosecret`）

## 常用命令

```bash
# 启动服务
uvicorn src.main:app --reload

# 数据库迁移
alembic upgrade head
alembic downgrade -1

# 初始化 Milvus
python scripts/init_milvus.py

# 启动/停止基础设施
docker-compose up -d
docker-compose down

# 运行测试
pytest
```

## 参考文档

- `docs/RAG系统设计文档.md` — 完整系统设计
- `docs/RAG系统开发任务清单.md` — 任务分解与接口定义
- `.env.example` — 环境变量模板
