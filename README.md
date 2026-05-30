# RAG 问答系统

生产级 RAG（检索增强生成）系统，支持 PDF、Word、Excel、TXT、Markdown、CSV 文档的上传、解析、检索与智能问答。

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| 语言 | Python 3.11 |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | Vue 3 + Ant Design Vue + TypeScript |
| LLM | Qwen（DashScope API） |
| Embedding | text-embedding-v2（1024 维），[模型仓库](https://github.com/yanheng799/rag-embedding) |
| 向量数据库 | Milvus 2.6 |
| 关系数据库 | PostgreSQL 16 |
| 对象存储 | MinIO |
| PDF 解析 | pymupdf |
| Word 解析 | python-docx |
| Excel 解析 | openpyxl |

## 环境要求

- Python >= 3.11, Node >= 20
- Docker & Docker Compose
- DashScope API Key（[申请地址](https://dashscope.console.aliyun.com/)）

## 快速开始

### 方式一：Docker 部署（推荐）

**启动全部服务（app + 基础设施）：**

```bash
# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

docker compose -f docker/docker-compose.full.yml up -d
```

**仅启动应用（依赖宿主机已有的基础设施）：**

```bash
docker compose -f docker/docker-compose.app.yml up -d
```

启动后访问：

- 前端页面：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 方式二：本地开发

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/rag-system.git
cd rag-system

# 2. 创建虚拟环境并安装依赖
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install -e ".[dev]"

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY

# 4. 启动基础设施
docker compose -f docker/docker-compose.full.yml up -d postgres milvus minio

# 5. 初始化数据库
alembic upgrade head

# 6. 启动后端
uvicorn src.main:app --reload

# 7. 启动前端（另一个终端）
cd web
npm install
npm run dev
```

## Docker 文件说明

```
docker/
├── Dockerfile                # 多阶段构建（Node 前端 + Python 后端）
├── entrypoint.sh             # 容器入口（alembic 迁移 + uvicorn 启动）
├── docker-compose.app.yml    # 仅启动应用容器（连宿主机已有服务）
└── docker-compose.full.yml   # 启动全部服务（app + pg + milvus + minio）
```

| 命令 | 说明 |
|------|------|
| `docker compose -f docker/docker-compose.app.yml up -d` | 仅启动 app，连宿主机已有的 pg/milvus/minio |
| `docker compose -f docker/docker-compose.full.yml up -d` | 启动全部服务 |
| `docker compose -f docker/docker-compose.app.yml build` | 重新构建镜像 |

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/documents` | 上传文档（multipart/form-data） |
| POST | `/api/v1/query` | 问答查询，返回答案 + 来源 + 图片 URL |
| WebSocket | `/api/v1/query/ws` | 流式问答 |
| POST | `/api/v1/retrieve` | 检索接口，支持 vector/BM25/hybrid 策略 |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/chunks` | 分块列表 |
| GET | `/api/v1/datasets` | 数据集列表 |
| GET | `/api/v1/images/{path}` | 图片代理 |

## 项目结构

```
src/
├── main.py                # FastAPI 入口，手动 DI 组装
├── config/settings.py     # pydantic-settings 配置
├── models/                # 共享数据模型
├── api/                   # API 层
│   ├── routers/           # 路由（documents, query, retrieve, chunks, datasets, images）
│   ├── schemas/           # Pydantic 请求/响应模型
│   └── middleware/        # 错误处理中间件
├── ingestion/             # 数据摄入层
│   ├── parsers/           # 文档解析器（PDF, Word, Excel, TXT, MD, CSV）+ 注册表
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
│   ├── hybrid_search.py   # 混合检索 + RRF 融合
│   └── chunk_merge.py     # 分块合并
└── orchestration/         # 编排层
    ├── orchestrator.py    # RAGOrchestrator
    ├── prompt_builder.py  # Prompt 构建
    └── llm_client.py      # DashScope Qwen 客户端

web/                        # Vue 3 前端
├── src/views/              # 页面（知识库、文档查看、问答、检索、分块管理）
├── src/api/                # API 调用层
└── src/stores/             # Pinia 状态管理
```

## 基础设施服务

| 服务 | 默认端口 | 说明 |
|------|---------|------|
| PostgreSQL | 5432 | 文档/分块元数据、查询日志 |
| Milvus | 19530 | 向量索引与检索 |
| MinIO | 9000 / 9001 | 原始文档 + 表格截图存储（9001 为管理控制台） |

MinIO 管理控制台：http://localhost:9001（默认账号 `minioadmin` / `minioadmin`）

## 常用命令

```bash
# 启动后端
uvicorn src.main:app --reload

# 启动前端
cd web && npm run dev

# 数据库迁移
alembic upgrade head
alembic downgrade -1

# 运行测试
pytest

# 代码检查
ruff check src/ tests/
ruff format src/ tests/
```

## 参考文档

- `docs/RAG系统设计文档.md` — 完整系统设计
- `docs/RAG系统开发任务清单.md` — 任务分解与接口定义
- `.env.example` — 环境变量模板
