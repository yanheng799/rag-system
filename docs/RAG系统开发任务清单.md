# RAG 系统开发任务清单

> 基于《RAG 系统整体设计文档 v1.7》拆解
> 版本：v1.4 | 状态：Phase 2 开发中

---

## 任务说明

- 每个任务包含：任务编号、所属模块、详细描述、涉及表/字段/接口/代码结构
- 任务按 Phase 顺序排列，Phase 内任务存在依赖关系时已标注
- 前置任务完成后方可开始后续任务

---

## Phase 1 技术决策记录

以下决策已在开发前确认，影响 Phase 1 任务的具体实现：

| # | 决策点 | 结论 | 备注 |
|---|--------|------|------|
| 1 | Embedding 方案 | DashScope text-embedding-v3 (1024维) | 替代 BGE-M3 本地部署，v3 支持自定义维度 |
| 2 | LLM 调用 | DashScope 云端 API (Qwen) | 替代 vLLM 本地部署 |
| 3 | Qwen-VL 视觉模型 | Phase 1 跳过 | 所有表格走规则描述路径 |
| 4 | 异步任务队列 | Phase 1 同步摄入 | Celery 推迟到 Phase 4 |
| 5 | 向量数据库 | Milvus (pymilvus 同步客户端) | 已本地部署 |
| 6 | Redis 缓存 | Phase 1 不使用 | 查询/Embedding 缓存推迟到 Phase 4 |
| 7 | 数据库访问层 | SQLAlchemy 2.0 async ORM + Alembic | |
| 8 | PDF 解析 | pymupdf (fitz) | 替代 Unstructured |
| 9 | Word 解析 | python-docx | 替代 Unstructured |
| 10 | Excel 解析 | openpyxl（Phase 1 新增） | 新增 ExcelParser 任务 |
| 11 | 旧格式 (.doc/.xls) | Phase 1 不支持 | 需要 LibreOffice，推迟到后续 Phase |
| 12 | 依赖注入 | app.state 手动组装 | |
| 13 | 测试策略 | 单元测试(mock) + 真实文档集成测试 | 集成测试使用 test-files/ 中真实电力工程文档 |
| 14 | Python 版本 | 3.11 | |

### Phase 1 推迟的任务

以下原 Phase 1 任务因技术决策调整，推迟到后续 Phase：

- **TASK-015b（摄入重试/死信队列）** → Phase 4（依赖 Celery）
- **TASK-050（vLLM 部署）** → 取消（使用 DashScope 云端 API）
- **TASK-023（WebSocket 流式接口）** → Phase 2（优先级 P1，非主链路必需）

### Phase 1 开发顺序（按 Batch 分批提交）

```
Batch 1: 工程骨架
  TASK-001 (目录结构 + requirements + docker-compose)
  TASK-006 (共享数据模型)
  TASK-038 (统一配置 settings.py)

Batch 2: 存储层
  TASK-002 (PostgreSQL DDL + Alembic)
  TASK-003 (Milvus Collection 初始化)
  TASK-004 (MinIO 对象存储)
  TASK-005 (StoragePort 接口抽象)

Batch 3: 摄入层
  TASK-007 (PDF Parser - pymupdf)
  TASK-008 (Word Parser - python-docx)
  TASK-008d (Excel Parser - openpyxl)  ← 新增
  TASK-009 (Parser 注册表)
  TASK-010 (段落边界识别)
  TASK-011 (表格截图)
  TASK-012 (表格语义描述 - 仅规则路径)
  TASK-013 (MixedChunk 组装)
  TASK-051 (文档图片提取)  ← 新增
  TASK-014 (Embedder - DashScope text-embedding-v3)
  TASK-015 (摄入 Pipeline - 同步版)

Batch 4: 检索 + 编排
  TASK-016 (LLM 客户端 - DashScope)
  TASK-017 (Prompt 构建器)
  TASK-018 (向量检索)
  TASK-019 (编排主流程)

Batch 5: API 层
  TASK-020 (文档上传接口)
  TASK-021 (文档状态查询)
  TASK-022 (问答接口)
  TASK-023b (调试检索接口)
```

## Phase 1：主链路跑通

> 目标：文档可上传、可解析、可问答的最小可用版本

---

### TASK-001｜基础工程初始化

**模块**：工程基础
**优先级**：P0
**描述**：搭建项目骨架，建立分层目录结构，配置依赖管理。

**目录结构**：
```
rag-system/
├── ingestion/          # 数据摄入层
│   ├── parsers/        # 文档解析器（插件注册表）
│   ├── chunkers/       # 分块引擎
│   ├── embedder.py     # Embedding 封装
│   └── pipeline.py     # 摄入主流程
├── storage/            # 存储层
│   ├── ports.py        # StoragePort 接口定义
│   ├── milvus_store.py
│   ├── pg_store.py
│   ├── oss_store.py
│   └── redis_cache.py
├── retrieval/          # 检索层
│   ├── pipeline.py     # 检索流水线
│   ├── query_rewriter.py
│   ├── hybrid_search.py
│   ├── reranker.py
│   └── context_compressor.py
├── orchestration/      # 编排层
│   ├── orchestrator.py
│   ├── prompt_builder.py
│   └── llm_client.py
├── api/                # 用户交互层
│   ├── routers/
│   ├── schemas/        # Pydantic 请求/响应模型
│   └── main.py
├── models/             # 共享数据结构
│   └── chunks.py       # ContentElement / ChunkMetadata / MixedChunk
├── config/
│   └── settings.py     # 统一配置管理（支持环境变量覆盖）
├── tests/
└── docker-compose.yml
```

**交付物**：
- 项目可运行（`uvicorn api.main:app`）
- `docker-compose.yml` 包含 PostgreSQL、Milvus、Redis、MinIO 服务
- 依赖文件 `requirements.txt` / `pyproject.toml`

---

### TASK-002｜数据库初始化 & Migration

**模块**：存储层 - PostgreSQL
**优先级**：P0
**前置**：TASK-001
**描述**：创建所有 PostgreSQL 表结构，配置索引。

**DDL 详细定义**：

```sql
-- 文档管理表
CREATE TABLE documents (
    doc_id        VARCHAR(64)  PRIMARY KEY,
    filename      VARCHAR(512) NOT NULL,
    raw_file_url  VARCHAR(1024) NOT NULL,        -- OSS 存储路径（内部路径，非签名URL）
    file_size     BIGINT,
    file_type     VARCHAR(16),                   -- pdf | docx | html | md
    status        VARCHAR(16)  NOT NULL DEFAULT 'pending',
                                                 -- pending | processing | done | failed
    error_msg     TEXT,                          -- 失败时记录错误信息
    created_by    VARCHAR(64),
    uploaded_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_status    ON documents(status);
CREATE INDEX idx_documents_created_by ON documents(created_by);
CREATE INDEX idx_documents_uploaded_at ON documents(uploaded_at DESC);

-- 分块记录表
CREATE TABLE chunks (
    chunk_id      VARCHAR(128) PRIMARY KEY,      -- 格式：{doc_id}_p{page}_c{index}
    doc_id        VARCHAR(64)  NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_type    VARCHAR(16)  NOT NULL,          -- text | table | mixed
    full_text     TEXT         NOT NULL,
    elements      JSONB        NOT NULL,          -- ContentElement 有序列表
    image_urls    JSONB        NOT NULL DEFAULT '[]',
    page          INT          NOT NULL,
    chunk_index   INT          NOT NULL,
    char_count    INT          NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_doc_id    ON chunks(doc_id);
CREATE INDEX idx_chunks_page      ON chunks(doc_id, page);
CREATE INDEX idx_chunks_type      ON chunks(chunk_type);

-- 查询日志表（监控用）
CREATE TABLE query_logs (
    log_id            VARCHAR(64)  PRIMARY KEY,
    question          TEXT         NOT NULL,
    answer            TEXT,
    retrieved_chunks  JSONB,                     -- 召回的 chunk_id 列表
    retrieval_ms      INT,                        -- 检索耗时（毫秒）
    llm_ms            INT,                        -- LLM 耗时（毫秒）
    total_ms          INT,
    token_count       INT,
    cache_hit         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by        VARCHAR(64),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_query_logs_created_at ON query_logs(created_at DESC);
CREATE INDEX idx_query_logs_created_by ON query_logs(created_by);
```

**交付物**：
- Alembic migration 文件，可通过 `alembic upgrade head` 一键建表
- 回滚脚本 `alembic downgrade -1`

---

### TASK-003｜Milvus Collection 初始化

**模块**：存储层 - Milvus
**优先级**：P0
**前置**：TASK-001
**描述**：创建 Milvus Collection，定义 Schema 和索引。

**Schema 定义**：

```python
# storage/milvus_store.py

COLLECTION_NAME = "rag_chunks"

fields = [
    FieldSchema("id",           DataType.INT64,        is_primary=True, auto_id=True),
    FieldSchema("embedding",    DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema("chunk_id",     DataType.VARCHAR,      max_length=128),
    FieldSchema("doc_id",       DataType.VARCHAR,      max_length=64),
    FieldSchema("full_text",    DataType.VARCHAR,      max_length=8192),
    FieldSchema("chunk_type",   DataType.VARCHAR,      max_length=16),
    FieldSchema("elements",     DataType.VARCHAR,      max_length=16384),  # JSON
    FieldSchema("image_urls",   DataType.VARCHAR,      max_length=2048),   # JSON array
    FieldSchema("source",       DataType.VARCHAR,      max_length=512),
    FieldSchema("page",         DataType.INT32),
    FieldSchema("chunk_index",  DataType.INT32),
    FieldSchema("char_count",   DataType.INT32),
    FieldSchema("created_at",   DataType.VARCHAR,      max_length=32),
]

# 索引配置
index_params = {
    "metric_type": "COSINE",
    "index_type":  "HNSW",
    "params": {"M": 16, "efConstruction": 200}
}
```

**接口方法**：

```python
class MilvusStore:
    def init_collection(self) -> None
    def insert(self, chunks: list[MilvusRecord]) -> list[int]
    def search(self, embedding: list[float], top_k: int, filters: dict) -> list[SearchResult]
    def delete_by_doc_id(self, doc_id: str) -> None
    def get_by_chunk_ids(self, chunk_ids: list[str]) -> list[MilvusRecord]
```

**交付物**：
- `storage/milvus_store.py` 实现上述接口
- 初始化脚本 `scripts/init_milvus.py`

---

### TASK-004｜MinIO 对象存储初始化

**模块**：存储层 - 对象存储
**优先级**：P0
**前置**：TASK-001
**描述**：初始化 MinIO Bucket，封装上传/下载/签名 URL 接口。

**目录规范**：
```
Bucket: rag-storage
├── raw-docs/{doc_id}/{filename}          # 原始文档
└── table-images/{doc_id}_p{page}_t{n}.png  # 表格截图
```

**接口方法**：

```python
class OSSStore:
    def upload_raw_doc(self, doc_id: str, filename: str, data: bytes) -> str
        # 返回内部路径：raw-docs/{doc_id}/{filename}

    def upload_table_image(self, doc_id: str, page: int, table_index: int, image: bytes) -> str
        # 返回内部路径：table-images/{doc_id}_p{page}_t{table_index}.png

    def sign_url(self, path: str, expire_seconds: int = 3600) -> str
        # 返回带签名的临时访问 URL

    def download(self, path: str) -> bytes
        # 下载原始文件内容

    def delete(self, path: str) -> None
```

**交付物**：`storage/oss_store.py`

---

### TASK-005｜StoragePort 接口抽象

**模块**：存储层 - 接口定义
**优先级**：P0
**前置**：TASK-002、TASK-003、TASK-004
**描述**：定义统一的 StoragePort 抽象接口，隔离业务逻辑与具体存储实现。

```python
# storage/ports.py

from abc import ABC, abstractmethod

class VectorStorePort(ABC):
    @abstractmethod
    def insert(self, chunks: list[MilvusRecord]) -> None: ...
    @abstractmethod
    def search(self, embedding: list[float], top_k: int, filters: dict) -> list[SearchResult]: ...
    @abstractmethod
    def delete_by_doc_id(self, doc_id: str) -> None: ...

class DocumentStorePort(ABC):
    @abstractmethod
    def save_document(self, doc: DocumentRecord) -> None: ...
    @abstractmethod
    def update_status(self, doc_id: str, status: str, error_msg: str = None) -> None: ...
    @abstractmethod
    def get_document(self, doc_id: str) -> DocumentRecord: ...
    @abstractmethod
    def list_documents(self, page: int, size: int) -> tuple[list[DocumentRecord], int]: ...
    @abstractmethod
    def save_chunk(self, chunk: ChunkRecord) -> None: ...
    @abstractmethod
    def delete_chunks_by_doc(self, doc_id: str) -> None: ...

class ObjectStorePort(ABC):
    @abstractmethod
    def upload_raw_doc(self, doc_id: str, filename: str, data: bytes) -> str: ...
    @abstractmethod
    def upload_table_image(self, doc_id: str, page: int, table_index: int, img: bytes) -> str: ...
    @abstractmethod
    def sign_url(self, path: str, expire_seconds: int) -> str: ...
    @abstractmethod
    def download(self, path: str) -> bytes: ...

class CachePort(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None: ...
    @abstractmethod
    def set(self, key: str, value: str, ttl: int) -> None: ...
    @abstractmethod
    def delete(self, key: str) -> None: ...
```

**交付物**：`storage/ports.py` + 各存储实现类注册到依赖注入容器

---

### TASK-006｜共享数据模型定义

**模块**：models
**优先级**：P0
**前置**：TASK-001
**描述**：定义贯穿所有层的核心数据结构。

```python
# models/chunks.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ContentElement:
    type:      str              # "text" | "table"
    content:   str              # 文字原文或表格语义描述
    image_url: Optional[str]    # 仅 table 有值，内部 OSS 路径（非签名URL）

@dataclass
class ChunkMetadata:
    chunk_id:    str
    chunk_type:  str            # "text" | "table" | "mixed"
    source:      str            # 原始文件名
    page:        int
    chunk_index: int
    char_count:  int
    created_at:  str            # ISO 8601
    doc_id:      str

@dataclass
class MixedChunk:
    metadata:   ChunkMetadata
    elements:   list[ContentElement]
    full_text:  str
    image_urls: list[str]       # 内部路径列表，快速索引

@dataclass
class RetrievedChunk:
    metadata:   ChunkMetadata
    elements:   list[ContentElement]  # image_url 已替换为签名 URL
    full_text:  str
    image_urls: list[str]
    score:      float
```

**交付物**：`models/chunks.py`、`models/documents.py`

---

### TASK-007｜文档解析器 - PDF Parser

**模块**：摄入层 - 解析器
**优先级**：P0
**前置**：TASK-006
**描述**：基于 pymupdf (fitz) 实现 PDF 解析器，输出扁平 Element 列表。

**接口定义**：

```python
# ingestion/parsers/base.py
class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedElement]: ...
    @abstractmethod
    def supported_types(self) -> list[str]: ...

@dataclass
class ParsedElement:
    elem_type:  str         # "text" | "table" | "title" | "list_item"
    content:    str         # 文字内容
    page:       int
    bbox:       tuple       # (x0, y0, x1, y1) 坐标
    style:      dict        # 字体、缩进等样式信息
    raw:        Any         # 原始对象（备用）

# ingestion/parsers/pdf_parser.py
class PDFParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedElement]: ...
    def supported_types(self) -> list[str]:
        return ["pdf"]
```

**关键逻辑**：
- 使用 `pymupdf` (fitz) 解析 PDF
- 提取文字块及 bbox 坐标（用于后续表格截图裁剪和段落边界识别）
- pymupdf 的 `page.find_tables()` 提取表格结构，保留行列信息

**交付物**：`ingestion/parsers/pdf_parser.py` + 单元测试

---

### TASK-008｜文档解析器 - Word Parser

**模块**：摄入层 - 解析器
**优先级**：P0
**前置**：TASK-007
**描述**：基于 python-docx 实现 Word 文档解析器。仅支持 .docx 格式。

**关键逻辑**：
- 使用 `python-docx` 直接解析 .docx 文件
- Word 中的表格通过 `python-docx` 提取原始 XML，记录表格在文档中的顺序位置
- 可获取合并单元格信息（用于判断表格复杂度）
- .doc 旧格式需要 LibreOffice 转换，推迟到后续 Phase

**交付物**：`ingestion/parsers/word_parser.py` + 单元测试

---

### TASK-008b｜文档解析器 - HTML Parser

**模块**：摄入层 - 解析器
**优先级**：P1（Phase 4）
**前置**：TASK-007
**描述**：基于 Unstructured 实现 HTML 文档解析器，处理网页、导出的 HTML 报告等格式。

**关键逻辑**：
- 使用 `unstructured.partition.html` 解析
- 过滤导航栏、页脚等噪音元素（通过 CSS 选择器黑名单配置）
- HTML 中的 `<table>` 标签识别为表格元素，交由混合块处理分支
- 提取 `<title>`、`<meta>` 标签中的元数据

```python
class HTMLParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedElement]: ...
    def supported_types(self) -> list[str]:
        return ["html", "htm"]
```

**交付物**：`ingestion/parsers/html_parser.py` + 单元测试

---

### TASK-008c｜文档解析器 - Markdown Parser

**模块**：摄入层 - 解析器
**优先级**：P1（Phase 4）
**前置**：TASK-007
**描述**：实现 Markdown 文档解析器，处理 `.md` 文件。Markdown 无坐标信息，段落边界由语法结构决定。

**关键逻辑**：
- 使用 `unstructured.partition.md` 或 `markdown-it-py` 解析
- 标题（`#`/`##`/`###`）识别为段落边界，触发新分块
- Markdown 表格（`| col | col |` 语法）识别为表格元素
- 代码块（` ``` `）作为独立的 `code` 类型 Element 保留，不做语义分块

```python
class MarkdownParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedElement]: ...
    def supported_types(self) -> list[str]:
        return ["md", "markdown"]
```

**注意**：Markdown 无页码概念，`page` 字段统一填 `1`，用 `chunk_index` 区分分块顺序。

**交付物**：`ingestion/parsers/markdown_parser.py` + 单元测试

---

### TASK-008d｜文档解析器 - Excel Parser

**模块**：摄入层 - 解析器
**优先级**：P0
**前置**：TASK-007
**描述**：基于 openpyxl 实现 Excel (.xlsx) 解析器，处理电力工程领域的铁塔统计、杆塔明细表等 Excel 数据。

**关键逻辑**：
- 使用 `openpyxl` 逐 sheet 读取数据
- 第一个非空行识别为表头，后续行按"列名:值"拼接为内容
- Excel 无页码概念，`page` 字段使用 sheet index（从 1 开始）
- 每个 sheet 按行数分组为多个 ParsedElement（避免单条 element 过长）
- 合并单元格通过 openpyxl 的 `merged_cells` 属性检测

```python
class ExcelParser(BaseParser):
    def parse(self, file_path: str) -> list[ParsedElement]: ...
    def supported_types(self) -> list[str]:
        return ["xlsx"]
```

**交付物**：`ingestion/parsers/excel_parser.py` + 单元测试

---

### TASK-009｜Parser 插件注册表

**模块**：摄入层 - 解析器
**优先级**：P0
**前置**：TASK-007、TASK-008
**描述**：实现 Parser 工厂，根据文件类型自动选择对应 Parser。

```python
# ingestion/parsers/registry.py
class ParserRegistry:
    _parsers: dict[str, BaseParser] = {}

    @classmethod
    def register(cls, parser: BaseParser) -> None:
        for t in parser.supported_types():
            cls._parsers[t] = parser

    @classmethod
    def get(cls, file_type: str) -> BaseParser:
        if file_type not in cls._parsers:
            raise UnsupportedFileTypeError(file_type)
        return cls._parsers[file_type]
```

**交付物**：`ingestion/parsers/registry.py`

---

### TASK-010｜段落边界识别模块

**模块**：摄入层 - 分块
**优先级**：P0
**前置**：TASK-009
**描述**：将扁平 Element 列表按语义段落边界聚合为段落组，这是混合块的核心逻辑。

**判断规则**：

```python
# ingestion/chunkers/paragraph_grouper.py

def is_new_paragraph_boundary(elem: ParsedElement, group: list[ParsedElement]) -> bool:
    """
    以下任一条件成立则认为是新段落边界：
    1. elem 类型为 "title"（标题级元素必然是新段落）
    2. elem 与 group 最后一个元素的垂直间距 > 阈值（默认 1.5 倍行高）
    3. elem 的缩进层级与 group 不同
    4. elem 在新的一页，且不是上一页末尾表格的延续
    """

def group_elements_by_paragraph(elements: list[ParsedElement]) -> list[list[ParsedElement]]:
    """
    输入：扁平 Element 列表
    输出：按段落分组的 Element 列表
    """
```

**边界情况处理**：
- 跨页段落：页尾最后一个文字 Element 与下一页第一个 Element 距离判断
- 孤立表格（前后无文字）：单独作为一个 table 段落组

**交付物**：`ingestion/chunkers/paragraph_grouper.py` + 单元测试（覆盖跨页场景）

---

### TASK-011｜表格截图模块

**模块**：摄入层 - 表格处理
**优先级**：P0
**前置**：TASK-004、TASK-010
**描述**：将文档中的表格区域渲染为高分辨率截图并上传 OSS。

```python
# ingestion/table_processor/screenshot.py

class TableScreenshot:
    def capture_pdf_table(
        self,
        pdf_path: str,
        page: int,
        bbox: tuple,          # (x0, y0, x1, y1)，Unstructured 提供的坐标
        doc_id: str,
        table_index: int,
        dpi: int = 150
    ) -> str:
        """
        1. pdf2image 渲染整页为图片（指定 dpi）
        2. 按 bbox 坐标 + padding 裁剪表格区域
        3. 上传至 OSS /table-images/
        4. 返回 OSS 内部路径
        """

    def capture_word_table(
        self,
        docx_path: str,
        table_index: int,
        doc_id: str,
        page: int
    ) -> str:
        """
        1. LibreOffice 将 docx 转 PDF
        2. 调用 capture_pdf_table
        """
```

**命名规范**：`{doc_id}_p{page}_t{table_index}.png`

**交付物**：`ingestion/table_processor/screenshot.py` + 集成测试

---

### TASK-012｜表格语义描述生成模块

**模块**：摄入层 - 表格处理
**优先级**：P0
**前置**：TASK-010
**描述**：为表格生成自然语言语义描述，用于后续向量化检索。Phase 1 仅实现规则描述路径，视觉模型路径在 Phase 3 (TASK-031) 补充。

**Phase 1 策略（仅规则路径）**：

```python
# ingestion/table_processor/describer.py

class TableDescriber:
    # Phase 1: 阈值设为极大值，所有表格走规则路径
    COMPLEX_THRESHOLD = 999

    def describe(self, elem: ParsedElement, image_path: str = None) -> str:
        # Phase 1: 所有表格走规则描述
        return self._describe_with_rules(elem)

    def _is_complex(self, elem: ParsedElement) -> bool:
        """判断是否为复杂表格（含合并单元格）"""

    def _describe_with_rules(self, elem: ParsedElement) -> str:
        """
        规则提取：
        1. 提取表头行
        2. 遍历每行，生成"列名:值"形式的描述
        3. 拼接为自然语言段落
        示例输出："表格共3列：区域、目标、实际完成。
                   华东区目标111万，实际完成120万；
                   华南区目标95万，实际完成98万。"
        """

    def _describe_with_vision(self, image_path: str) -> str:
        """
        调用 Qwen-VL，Prompt：
        "请描述这张表格的内容，包括表头和每行数据，用自然语言输出，不要使用Markdown格式。"
        """
```

**交付物**：`ingestion/table_processor/describer.py` + 单元测试

---

### TASK-013｜MixedChunk 组装器

**模块**：摄入层 - 分块
**优先级**：P0
**前置**：TASK-010、TASK-011、TASK-012
**描述**：将段落组装为 MixedChunk，生成 chunk_id 和元数据。

```python
# ingestion/chunkers/chunk_builder.py

class ChunkBuilder:
    def build(
        self,
        elements: list[ParsedElement],
        doc_id: str,
        page: int,
        chunk_index: int,
        screenshot: TableScreenshot,
        describer: TableDescriber
    ) -> MixedChunk:
        """
        1. 判断段落类型：纯文字 / 纯表格 / 混合
        2. 遍历 elements：
           - 文字元素：直接取 content，image_url=None
           - 表格元素：调用 screenshot 截图，调用 describer 生成描述
        3. 拼接 full_text（所有 content 串联）
        4. 收集 image_urls 列表
        5. 生成 ChunkMetadata（chunk_id = {doc_id}_p{page}_c{chunk_index}）
        6. 返回 MixedChunk
        """
```

**交付物**：`ingestion/chunkers/chunk_builder.py` + 单元测试

---

### TASK-052｜分块关联合并（group_id）

**模块**：摄入层 + 检索层
**优先级**：P0
**前置**：TASK-015、TASK-018
**描述**：大段落因 `max_chunk_size` 被拆分为多个子分块时，通过 `group_id` 关联。检索命中任一子分块时，自动获取同组全部兄弟分块并合并返回完整段落内容。

**算法设计**：

#### 摄入阶段

在 `_split_oversized_groups` 中，当一组被拆分为多个子组时，所有子组共享同一个 `group_id`；未拆分的组 `group_id` 为空串。

```
段落组 (1545 chars, 超过 1024)
  → split → 子组A (877 chars) group_id="doc_xxx_g3"
           子组B (668 chars) group_id="doc_xxx_g3"
```

#### 检索阶段

1. 向量搜索 → 得到 top-k 结果
2. 收集结果中有非空 `group_id` 的分块
3. 批量查询 Milvus：按 `group_id` 获取所有兄弟分块
4. 按 `(page, chunk_index)` 排序，拼接 `full_text`
5. 去重：同组多个命中只保留一个合并结果，取最高分

**涉及改动**：

| 文件 | 改动 |
|------|------|
| `ingestion/chunkers/paragraph_grouper.py` | `_split_oversized_groups` 接收 `doc_id`，拆分时打 `group_id` |
| `models/chunks.py` | `ChunkMetadata` 增加 `group_id: str = ""` |
| `models/documents.py` | `ChunkRecord` 增加 `group_id` 字段 |
| `storage/pg_models.py` | `ChunkORM` 增加 `group_id` 列 |
| `storage/milvus_store.py` | Schema 增加 `group_id`；新增 `fetch_by_group_ids` |
| `storage/ports.py` | `VectorStorePort` 增加 `fetch_by_group_ids` |
| `retrieval/vector_search.py` | 搜索后合并同组分块 |
| `ingestion/pipeline.py` | 构建 chunk 时传递 `group_id` |
| Alembic 迁移 | `rag_chunks` 表增加 `group_id` 列 + 索引 |

**Milvus Schema 变更**：

```python
FieldSchema("group_id", DataType.VARCHAR, max_length=128),
```

新增方法：

```python
# storage/milvus_store.py
def fetch_by_group_ids(self, group_ids: list[str]) -> list[dict]:
    """按 group_id 批量查询所有关联分块"""
    values = ', '.join(f'"{gid}"' for gid in group_ids)
    expr = f'group_id in [{values}]'
    results = self._collection.query(expr=expr, output_fields=[...])
    return results
```

**检索合并逻辑**：

```python
# retrieval/vector_search.py
def search(self, question, top_k, filters):
    chunks = self._vector_search(...)

    # 收集需要合并的 group
    group_map: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        if chunk.metadata.group_id:
            group_map.setdefault(chunk.metadata.group_id, []).append(chunk)

    if group_map:
        siblings = self._vector_store.fetch_by_group_ids(list(group_map.keys()))
        # 补充结果中未命中的兄弟分块
        for hit in siblings:
            gid = hit["group_id"]
            existing_ids = {c.metadata.chunk_id for c in group_map[gid]}
            if hit["chunk_id"] not in existing_ids:
                # 构造 RetrievedChunk 加入 group_map
                ...

        # 合并同组：拼接 full_text，取最高分
        merged = []
        seen = set()
        for chunk in chunks:
            gid = chunk.metadata.group_id
            if not gid:
                merged.append(chunk)
                continue
            if gid in seen:
                continue
            seen.add(gid)
            group = sorted(group_map[gid], key=lambda c: (c.metadata.page, c.metadata.chunk_index))
            chunk.full_text = "\n".join(c.full_text for c in group)
            chunk.score = max(c.score for c in group)
            merged.append(chunk)
        chunks = merged

    return chunks
```

**验证**：

1. 上传抱杆使用说明书 PDF，确认 2.1.4 被拆分后两个子分块具有相同 `group_id`
2. 向量检索命中任一子分块，验证返回结果包含完整的 2.1.4 内容

**交付物**：上述文件改动 + Alembic 迁移 + 集成测试

---

### TASK-051｜文档图片提取模块

**模块**：摄入层 - 图片处理
**优先级**：P0
**前置**：TASK-004、TASK-007、TASK-008
**描述**：从 PDF 和 Word 文档中提取内嵌图片，上传至 MinIO 对象存储，生成占位文本。图片仅作为上下文补充，不参与向量化检索。

**设计决策**：

| 决策点 | 结论 | 说明 |
|--------|------|------|
| 图片处理方式 | 截图 + 占位文本 | 提取图片原文件上传 MinIO，在 full_text 中插入 `[图片: xxx.png]` 占位符 |
| 图片检索角色 | 仅上下文补充 | 图片不参与向量化，只在命中文档时作为补充信息返回 |
| 视觉模型 | 不使用 | Phase 1 不调用 Qwen-VL，图注由周围文本推断 |
| 图片过滤 | 按尺寸过滤 | 忽略面积过小的图片（图标、装饰线），仅提取实质内容图片 |

**MinIO 存储规范**：

```
Bucket: rag-storage
└── /doc-images/
      ├── {doc_id}_p{page}_img{index}.{ext}   # 文档图片
      └── ...
```

**接口定义**：

```python
# ingestion/table_processor/image_extractor.py

class ImageExtractor:
    """文档图片提取器"""

    # 过滤阈值：图片面积占页面面积比例低于此值的忽略
    MIN_IMAGE_AREA_RATIO = 0.005
    # 过滤阈值：图片宽度或高度低于此像素值的忽略
    MIN_IMAGE_DIMENSION = 50

    def extract_pdf_images(
        self,
        pdf_path: str,
        doc_id: str,
    ) -> list[ParsedElement]:
        """
        从 PDF 中提取内嵌图片。

        使用 pymupdf API：
        1. page.get_images(full=True) → 获取页面图片引用列表 (xref, smask, w, h, ...)
        2. doc.extract_image(xref) → 提取图片原始数据 {"image": bytes, "ext": "png/jpeg", ...}
        3. page.get_image_info(xrefs=True) → 获取图片 bbox 坐标

        过滤规则：
        - 面积占页面面积比 < MIN_IMAGE_AREA_RATIO → 忽略（小图标）
        - 宽或高 < MIN_IMAGE_DIMENSION → 忽略（装饰线）
        - 与表格 bbox 重叠 > 50% → 忽略（表格内图片由表格截图处理）

        返回 elem_type="image" 的 ParsedElement 列表：
        - content: 占位文本 "[图片: {filename}]"
        - bbox: 图片在页面上的坐标
        - raw: {"image_bytes": bytes, "ext": str, "filename": str}
        """

    def extract_word_images(
        self,
        docx_path: str,
        doc_id: str,
    ) -> list[ParsedElement]:
        """
        从 Word 文档中提取内嵌图片。

        使用 python-docx：
        1. 遍历段落，检测 paragraph._element.xpath('.//w:drawing')
        2. 从 drawing 元素中提取 rId，通过 doc.part.related_parts 获取图片数据
        3. 记录图片在文档中的位置（段落索引）

        返回 elem_type="image" 的 ParsedElement 列表
        """

    def upload_image(
        self,
        image_bytes: bytes,
        ext: str,
        doc_id: str,
        page: int,
        index: int,
    ) -> str:
        """
        上传图片至 MinIO /doc-images/ 目录。
        命名规范：{doc_id}_p{page}_img{index}.{ext}
        返回内部 OSS 路径。
        """
```

**ParsedElement 扩展**：

```python
# ingestion/parsers/base.py 新增 elem_type 值

@dataclass
class ParsedElement:
    elem_type: str  # "text" | "table" | "title" | "list_item" | "image"  ← 新增 "image"
    content: str    # 图片元素为占位文本 "[图片: xxx.png]"
    page: int
    bbox: tuple     # 图片在页面上的坐标 (x0, y0, x1, y1)
    style: dict
    raw: Any        # {"image_bytes": bytes, "ext": str, "filename": str}
```

**ContentElement 扩展**：

```python
# models/chunks.py 新增 type 值

@dataclass
class ContentElement:
    type: str              # "text" | "table" | "image"  ← 新增 "image"
    content: str           # 图片元素为占位文本
    image_url: str | None  # 图片内部 OSS 路径
```

**ChunkBuilder 更新**：

```python
# ingestion/chunkers/chunk_assembler.py 新增图片元素处理

if elem.elem_type == "image":
    # 1. 从 elem.raw 取出图片数据
    # 2. 调用 ImageExtractor.upload_image 上传至 MinIO
    # 3. 构造 ContentElement(type="image", content="[图片: xxx]", image_url=oss_path)
```

**交付物**：`ingestion/table_processor/image_extractor.py` + 单元测试 + 更新 `models/chunks.py`、`ingestion/parsers/base.py`、`ingestion/chunkers/chunk_assembler.py`

---

### TASK-014｜Embedding 模型封装

**模块**：摄入层 - Embedding
**优先级**：P0
**前置**：TASK-006
**描述**：封装 DashScope text-embedding-v3 API，提供批量向量化接口。

```python
# ingestion/embedder.py

class Embedder:
    def __init__(self, api_key: str, model: str = "text-embedding-v3"):
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回 1024 维向量列表（通过 DashScope API）"""

    def embed_single(self, text: str) -> list[float]:
        """单条向量化"""
```

**配置项**（`config/settings.py`）：
```
DASHSCOPE_API_KEY    = "sk-..."       # DashScope API Key
EMBEDDING_MODEL      = "text-embedding-v3"
EMBEDDING_DIMENSION  = 1024
EMBEDDING_BATCH_SIZE = 10             # v3 批量上限为 10
```

**交付物**：`ingestion/embedder.py`

---

### TASK-015｜摄入主流程 Pipeline

**模块**：摄入层
**优先级**：P0
**前置**：TASK-009 ~ TASK-014
**描述**：串联解析 → 段落聚合 → 分块 → Embedding → 写库的完整摄入流程。Phase 1 采用同步执行，上传接口同步返回结果。

```python
# ingestion/pipeline.py

class IngestionPipeline:
    def ingest(self, doc_id: str, file_path: str, file_type: str) -> None:
        """
        1. 更新 documents.status = 'processing'
        2. 上传原始文件至 OSS /raw-docs/，更新 raw_file_url
        3. 调用 ParserRegistry 解析文档，得到 ParsedElement 列表
        4. 调用 ParagraphGrouper 聚合为段落组
        5. 遍历段落组，调用 ChunkBuilder 组装 MixedChunk
        6. 批量调用 Embedder (DashScope) 对 full_text 向量化
        7. 批量写入 Milvus（向量 + metadata）
        8. 批量写入 PostgreSQL chunks 表
        9. 更新 documents.status = 'done'
        异常时：更新 status = 'failed'，记录 error_msg
        """
```

**Phase 1 同步模式**：上传接口等待摄入完成后返回完整结果。Phase 4 引入 Celery 异步队列时，只需在外部包装 task 即可。

**交付物**：`ingestion/pipeline.py`

---

### TASK-015b｜摄入任务失败重试 & 死信队列

**模块**：摄入层 - 任务队列
**优先级**：P0
**前置**：TASK-015
**描述**：为摄入 Celery 任务配置自动重试策略和死信队列，保障文档摄入的可靠性。

**Celery 任务配置**：

```python
# ingestion/tasks.py

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,        # 首次重试等待 60 秒
    retry_backoff=True,            # 指数退避：60s / 120s / 240s
    queue="ingestion",
    acks_late=True,                # 任务完成后才 ack，防止消息丢失
)
def ingest_document_task(self, doc_id: str, file_path: str, file_type: str):
    try:
        pipeline.ingest(doc_id, file_path, file_type)
    except (ParseError, EmbeddingError) as exc:
        # 可重试异常：更新 retry_count，重新入队
        pg_store.update_retry_count(doc_id)
        raise self.retry(exc=exc)
    except Exception as exc:
        # 不可重试异常或超出重试次数：写入死信队列
        pg_store.update_status(doc_id, "failed", error_msg=str(exc))
        dead_letter_queue.publish(doc_id=doc_id, error=str(exc))
        raise
```

**死信队列处理**：
- 超过 max_retries 的任务发布到 `ingestion.dlq` 队列
- `documents.status` 更新为 `failed`，`error_msg` 记录最后一次错误
- 管理后台展示失败文档列表，支持手动触发重新摄入（调用 TASK-034 接口）
- 可选：接入告警通知（邮件/企业微信）

**PostgreSQL 新增字段**（已在 TASK-002 DDL 中定义）：
- `documents.retry_count`：当前已重试次数
- `documents.error_msg`：最后一次失败原因

**交付物**：`ingestion/tasks.py`（更新）、`ingestion/dead_letter.py`

---

### TASK-016｜LLM 客户端封装

**模块**：编排层
**优先级**：P0
**前置**：TASK-001
**描述**：封装 Qwen LLM 调用，通过 DashScope OpenAI 兼容接口访问，支持热替换。

```python
# orchestration/llm_client.py

class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list[dict], stream: bool = False) -> str | Generator: ...

class QwenClient(LLMClient):
    """调用 DashScope OpenAI 兼容接口"""
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 30): ...
    def complete(self, messages: list[dict], stream: bool = False) -> str | Generator: ...
```

**配置项**：
```
DASHSCOPE_API_KEY   = "sk-..."
LLM_BASE_URL        = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL           = "qwen-plus"
LLM_TIMEOUT         = 30
LLM_MAX_TOKENS      = 2048
LLM_TEMPERATURE     = 0.1
```

**交付物**：`orchestration/llm_client.py`

---

### TASK-017｜Prompt 构建器

**模块**：编排层
**优先级**：P0
**前置**：TASK-006
**描述**：将检索结果和用户问题组装为 LLM Prompt，image_url 不进入 Prompt。

```python
# orchestration/prompt_builder.py

SYSTEM_PROMPT = """你是一个严谨的问答助手。
请严格根据以下提供的参考资料回答用户问题。
如果参考资料中没有足够信息，请明确说明"根据现有资料无法回答"，不要编造内容。"""

class PromptBuilder:
    def build(self, question: str, chunks: list[RetrievedChunk]) -> list[dict]:
        """
        构建 messages 列表：
        - role: system → SYSTEM_PROMPT
        - role: user   → 参考资料块 + 用户问题

        参考资料格式：
        [来源{n} - {source} 第{page}页 - {chunk_type}]
        {element.content}  # 所有 element 的 content 按顺序拼接
        （image_url 不包含在内）
        """
```

**交付物**：`orchestration/prompt_builder.py`

---

### TASK-018｜基础检索模块（向量检索）

**模块**：检索层
**优先级**：P0
**前置**：TASK-003、TASK-014
**描述**：实现基于 Milvus 的向量检索，作为检索 Pipeline 的第一个节点。

```python
# retrieval/vector_search.py

class VectorSearcher:
    def search(
        self,
        question: str,
        top_k: int = 50,
        filters: dict = None        # 权限过滤条件，如 doc_id in [...]
    ) -> list[SearchResult]:
        """
        1. 调用 Embedder 对 question 向量化
        2. 调用 MilvusStore.search
        3. 返回 SearchResult 列表（含 chunk_id、score、metadata）
        """
```

**交付物**：`retrieval/vector_search.py`

---

### TASK-019｜编排主流程

**模块**：编排层
**优先级**：P0
**前置**：TASK-016、TASK-017、TASK-018
**描述**：串联检索 → Prompt 构建 → LLM 调用 → 后处理的完整问答流程。

```python
# orchestration/orchestrator.py

class RAGOrchestrator:
    def query(self, question: str, user_id: str = None) -> QueryResponse:
        """
        1. 向量检索（top_k=50）
        2. 构建 Prompt
        3. 调用 LLM
        4. 后处理（image_url 签名替换）
        5. 写入 query_logs
        6. 返回 QueryResponse
        """

    def query_stream(self, question: str, user_id: str = None) -> Generator:
        """流式版本，逐 token yield"""

    def _sign_image_urls(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """将 elements 中的内部 OSS 路径替换为签名 URL"""
```

**交付物**：`orchestration/orchestrator.py`

---

### TASK-020｜REST API - 文档上传接口

**模块**：用户交互层
**优先级**：P0
**前置**：TASK-015
**描述**：实现文档上传 API，触发异步摄入任务。

**接口定义**：

```
POST /api/v1/documents/upload
Content-Type: multipart/form-data

Request:
  file:        binary     必填，文件内容
  filename:    string     必填，原始文件名

Response 200:
{
  "doc_id":    "doc_abc123",
  "filename":  "2024年销售报告.pdf",
  "status":    "pending",
  "uploaded_at": "2024-01-15T10:30:00Z"
}

Response 400: 不支持的文件格式
Response 413: 文件过大（默认限制 50MB）
```

**Pydantic Schema**：
```python
class UploadResponse(BaseModel):
    doc_id:      str
    filename:    str
    status:      str
    uploaded_at: datetime
```

**交付物**：`api/routers/documents.py`

---

### TASK-021｜REST API - 文档状态查询接口

**模块**：用户交互层
**优先级**：P0
**前置**：TASK-020

```
GET /api/v1/documents/{doc_id}/status

Response 200:
{
  "doc_id":     "doc_abc123",
  "filename":   "2024年销售报告.pdf",
  "status":     "done",       # pending | processing | done | failed
  "error_msg":  null,
  "uploaded_at": "2024-01-15T10:30:00Z",
  "updated_at":  "2024-01-15T10:32:15Z"
}

Response 404: 文档不存在
```

**交付物**：`api/routers/documents.py`（追加路由）

---

### TASK-022｜REST API - 问答接口

**模块**：用户交互层
**优先级**：P0
**前置**：TASK-019

```
POST /api/v1/query

Request Body:
{
  "question": "2024年Q1华东区销售完成情况如何？",
  "top_k":    5         # 可选，默认 5
}

Response 200:
{
  "answer": "根据文档第3页...",
  "sources": [
    {
      "metadata": {
        "chunk_id":    "doc_001_p3_c2",
        "chunk_type":  "mixed",
        "source":      "2024年销售报告.pdf",
        "page":        3,
        "chunk_index": 2,
        "char_count":  128,
        "created_at":  "2024-01-15T10:30:00Z",
        "doc_id":      "doc_001",
        "score":       0.92
      },
      "elements": [
        { "type": "text",  "content": "Q1各区域完成情况如下：", "image_url": null },
        { "type": "table", "content": "表格：华东目标111万...", "image_url": "https://..." },
        { "type": "text",  "content": "其中华东超额完成8%...", "image_url": null }
      ]
    }
  ]
}

Response 400: question 为空
Response 503: LLM 服务不可用
```

**Pydantic Schema**：
```python
class QueryRequest(BaseModel):
    question: str
    top_k:    int = Field(default=5, ge=1, le=20)

class ElementSchema(BaseModel):
    type:      str
    content:   str
    image_url: Optional[str]

class ChunkMetadataSchema(BaseModel):
    chunk_id:    str
    chunk_type:  str
    source:      str
    page:        int
    chunk_index: int
    char_count:  int
    created_at:  str
    doc_id:      str
    score:       float

class SourceSchema(BaseModel):
    metadata: ChunkMetadataSchema
    elements: list[ElementSchema]

class QueryResponse(BaseModel):
    answer:  str
    sources: list[SourceSchema]
```

**交付物**：`api/routers/query.py`、`api/schemas/query.py`

---

### TASK-023｜WebSocket - 流式问答接口

**模块**：用户交互层
**优先级**：P1
**前置**：TASK-022

```
WS /api/v1/query/stream

Client → Server:
{ "question": "...", "top_k": 5 }

Server → Client（多次推送）:
# 阶段1：答案 token 逐步推送
{ "type": "token", "content": "根据" }
{ "type": "token", "content": "文档" }
...

# 阶段2：来源一次性推送
{ "type": "sources", "sources": [...] }

# 阶段3：结束信号
{ "type": "done" }

# 异常：
{ "type": "error", "message": "LLM 服务不可用" }
```

**交付物**：`api/routers/query_ws.py`

---

### TASK-023b｜REST API - 分块召回测试接口

**模块**：用户交互层 - 调试工具
**优先级**：P0
**前置**：TASK-018（Phase 1 基础向量检索完成即可使用，Phase 2 完成后自动升级为混合检索结果）
**描述**：绕过 LLM，直接返回检索 Pipeline 的分块召回结果，用于开发和调试阶段验证检索质量。支持逐步调试：可单独测试向量检索、BM25、重排序各节点效果，并支持在 hybrid 模式下**自定义 vector 和 bm25 的融合权重**。

**接口定义**：

```
POST /api/v1/debug/retrieve

Request Body:
{
  "question":      "2024年Q1华东区销售完成情况如何？",
  "top_k":         10,          # 可选，默认 10，最大 50
  "rerank":        true,        # 可选，默认 true；false 时跳过重排序，直接返回融合结果
  "search_mode":   "hybrid",    # 可选："vector" | "bm25" | "hybrid"（默认）
  "vector_weight": 0.7,         # 可选，仅 hybrid 模式生效，向量检索权重，默认 0.5，范围 0.0~1.0
  "bm25_weight":   0.3,         # 可选，仅 hybrid 模式生效，BM25 权重，默认 0.5，范围 0.0~1.0
                                # 注意：两者之和不要求为 1，系统内部归一化处理
  "show_prompt":   false        # 可选，默认 false；true 时额外返回会送入 LLM 的 Prompt 文本
}

Response 200:
{
  "question":        "2024年Q1华东区销售完成情况如何？",
  "search_mode":     "hybrid",
  "rerank":          true,
  "vector_weight":   0.7,       # 本次实际使用的向量权重（归一化后）
  "bm25_weight":     0.3,       # 本次实际使用的 BM25 权重（归一化后）
  "total_retrieved": 10,
  "retrieval_ms":    135,

  "chunks": [
    {
      "rank":     1,
      "metadata": {
        "chunk_id":    "doc_001_p3_c2",
        "chunk_type":  "mixed",
        "source":      "2024年销售报告.pdf",
        "page":        3,
        "chunk_index": 2,
        "char_count":  128,
        "created_at":  "2024-01-15T10:30:00Z",
        "doc_id":      "doc_001"
      },
      "scores": {
        "vector_score":        0.88,   # 向量检索余弦相似度原始分
        "bm25_score":          0.72,   # BM25 ts_rank 原始分
        "weighted_rrf_score":  0.038,  # 加权 RRF 融合分（hybrid 模式）
        "rerank_score":        0.92    # 重排序最终分（rerank=true 时有值）
      },
      "elements": [
        { "type": "text",  "content": "Q1各区域完成情况如下：",         "image_url": null },
        { "type": "table", "content": "表格：华东目标111万实际120万……", "image_url": "https://oss.../doc_001_p3_t1.png?token=xxx" },
        { "type": "text",  "content": "其中华东区超额完成8%……",         "image_url": null }
      ]
    }
  ],

  "prompt": null
}

Response 400: question 为空 / 参数非法（如 vector_weight 超出范围）
```

**Pydantic Schema**：

```python
# api/schemas/debug.py

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

class RetrieveRequest(BaseModel):
    question:       str
    top_k:          int     = Field(default=10, ge=1, le=50)
    rerank:         bool    = True
    search_mode:    Literal["vector", "bm25", "hybrid"] = "hybrid"
    vector_weight:  float   = Field(default=0.5, ge=0.0, le=1.0)
    bm25_weight:    float   = Field(default=0.5, ge=0.0, le=1.0)
    show_prompt:    bool    = False

    @model_validator(mode="after")
    def check_weights(self):
        """权重不能同时为 0"""
        if self.search_mode == "hybrid":
            if self.vector_weight == 0.0 and self.bm25_weight == 0.0:
                raise ValueError("vector_weight 和 bm25_weight 不能同时为 0")
        return self

    @property
    def normalized_vector_weight(self) -> float:
        total = self.vector_weight + self.bm25_weight
        return self.vector_weight / total

    @property
    def normalized_bm25_weight(self) -> float:
        total = self.vector_weight + self.bm25_weight
        return self.bm25_weight / total

class ChunkScores(BaseModel):
    vector_score:        Optional[float]  # 向量检索余弦相似度
    bm25_score:          Optional[float]  # BM25 ts_rank 分数
    weighted_rrf_score:  Optional[float]  # 加权 RRF 融合分
    rerank_score:        Optional[float]  # Cross-Encoder 重排序分

class DebugChunk(BaseModel):
    rank:     int
    metadata: ChunkMetadataSchema
    scores:   ChunkScores
    elements: list[ElementSchema]

class RetrieveResponse(BaseModel):
    question:         str
    search_mode:      str
    rerank:           bool
    vector_weight:    Optional[float]  # hybrid 模式下返回归一化后的值，其他模式为 null
    bm25_weight:      Optional[float]
    total_retrieved:  int
    retrieval_ms:     int
    chunks:           list[DebugChunk]
    prompt:           Optional[str]
```

**加权 RRF 融合逻辑**（更新 TASK-025 的 `RRFFusion`）：

```python
# retrieval/fusion.py

class RRFFusion:
    def fuse(
        self,
        results_list: list[list[SearchResult]],
        weights: list[float],    # 每路检索对应的权重，已归一化
        k: int = 60
    ) -> list[SearchResult]:
        """
        加权 RRF 公式：
          score(d) = Σ  weight_i × (1 / (k + rank_i(d)))

        默认等权重时退化为标准 RRF：
          score(d) = Σ  1 / (k + rank_i(d))
        """
        scores: dict[str, float] = defaultdict(float)
        for result_list, weight in zip(results_list, weights):
            for rank, item in enumerate(result_list, start=1):
                scores[item.chunk_id] += weight * (1.0 / (k + rank))
        # 按融合分降序返回
        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
        ...
```

**内部实现逻辑**：

```python
# api/routers/debug.py

@router.post("/debug/retrieve", response_model=RetrieveResponse)
async def retrieve_debug(req: RetrieveRequest):
    start = time.time()

    if req.search_mode == "vector":
        raw_results = vector_searcher.search(req.question, top_k=req.top_k * 5)
        v_weight, b_weight = None, None

    elif req.search_mode == "bm25":
        raw_results = bm25_searcher.search(req.question, top_k=req.top_k * 5)
        v_weight, b_weight = None, None

    else:  # hybrid：使用归一化后的权重传入 RRFFusion
        v_weight = req.normalized_vector_weight
        b_weight = req.normalized_bm25_weight
        vec_results  = vector_searcher.search(req.question, top_k=req.top_k * 5)
        bm25_results = bm25_searcher.search(req.question, top_k=req.top_k * 5)
        raw_results  = rrf_fusion.fuse(
            results_list=[vec_results, bm25_results],
            weights=[v_weight, b_weight]
        )

    if req.rerank:
        final_results = reranker.rerank(req.question, raw_results, top_k=req.top_k)
    else:
        final_results = raw_results[:req.top_k]

    chunks = enrich_and_sign(final_results)

    prompt_text = None
    if req.show_prompt:
        prompt_text = prompt_builder.build_text(req.question, chunks)

    retrieval_ms = int((time.time() - start) * 1000)
    return RetrieveResponse(
        question=req.question,
        search_mode=req.search_mode,
        rerank=req.rerank,
        vector_weight=v_weight,
        bm25_weight=b_weight,
        total_retrieved=len(chunks),
        retrieval_ms=retrieval_ms,
        chunks=[to_debug_chunk(c, rank+1) for rank, c in enumerate(chunks)],
        prompt=prompt_text
    )
```

**典型使用场景**：

| 场景 | 请求参数 | 目的 |
|------|---------|------|
| 验证向量检索效果 | `search_mode=vector, rerank=false` | 单独观察语义相似度召回结果 |
| 验证 BM25 效果 | `search_mode=bm25, rerank=false` | 单独观察关键词匹配召回结果 |
| 调试权重：偏语义 | `search_mode=hybrid, vector_weight=0.8, bm25_weight=0.2` | 语义理解优先，适合长文本问题 |
| 调试权重：偏关键词 | `search_mode=hybrid, vector_weight=0.2, bm25_weight=0.8` | 关键词命中优先，适合专有名词查询 |
| 验证重排序效果 | `search_mode=hybrid, rerank=true` | 对比 weighted_rrf_score 和 rerank_score 的排名变化 |
| 验证 Prompt 构建 | `show_prompt=true` | 确认送入 LLM 的上下文内容是否合理 |
| 快速定位召回问题 | `top_k=20, rerank=false` | 扩大观察范围，排查漏召回问题 |

**权重设计说明**：

两个权重值不要求归一化输入，系统内部自动处理：
- 输入 `vector_weight=0.7, bm25_weight=0.3` 与 `vector_weight=7, bm25_weight=3` 效果相同
- 仅设置一个权重为 0 等价于单路检索，但保留两路原始分便于对比
- 权重仅影响 RRF 融合阶段，不影响各路检索的原始分

**注意**：此接口仅供内部调试使用，生产环境应通过路由鉴权或网关限制访问，不对外暴露。

**交付物**：`api/routers/debug.py`、`api/schemas/debug.py`；同步更新 `retrieval/fusion.py` 支持权重参数

---

## Phase 2：检索质量提升

> 目标：混合检索 + 重排序，大幅提升召回精度

---

### TASK-024｜BM25 关键词检索

**模块**：检索层
**优先级**：P1
**前置**：TASK-002
**描述**：基于 PostgreSQL `full_text` 字段实现 BM25 全文检索。

```sql
-- 为 chunks 表添加全文索引
ALTER TABLE chunks ADD COLUMN fts_vector TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('simple', full_text)) STORED;

CREATE INDEX idx_chunks_fts ON chunks USING GIN(fts_vector);
```

```python
# retrieval/bm25_search.py

class BM25Searcher:
    def search(self, question: str, top_k: int = 50) -> list[SearchResult]:
        """
        使用 PostgreSQL ts_rank 函数实现 BM25 检索
        SQL:
          SELECT chunk_id, ts_rank(fts_vector, query) AS score
          FROM chunks, plainto_tsquery('simple', :question) query
          WHERE fts_vector @@ query
          ORDER BY score DESC LIMIT :top_k
        """
```

**交付物**：`retrieval/bm25_search.py` + Migration 脚本

---

### TASK-025｜RRF 结果融合

**模块**：检索层
**优先级**：P1
**前置**：TASK-018、TASK-024
**描述**：将向量检索和 BM25 检索结果通过加权 RRF 算法融合排序，支持自定义各路检索的权重。

```python
# retrieval/fusion.py

from collections import defaultdict

class RRFFusion:
    def fuse(
        self,
        results_list: list[list[SearchResult]],
        weights:      list[float] | None = None,  # 各路权重，None 时等权重
        k:            int = 60                     # RRF 常数，通常取 60
    ) -> list[SearchResult]:
        """
        加权 RRF 公式：
          score(d) = Σ  weight_i × (1 / (k + rank_i(d)))

        weights 为 None 或等权重时退化为标准 RRF：
          score(d) = Σ  1 / (k + rank_i(d))

        weights 传入前须已归一化（各值之和为 1），
        由调用方（RetrievalPipeline / debug 接口）负责归一化。
        """
        n = len(results_list)
        if weights is None:
            weights = [1.0 / n] * n

        scores:  dict[str, float]       = defaultdict(float)
        sources: dict[str, SearchResult] = {}

        for result_list, weight in zip(results_list, weights):
            for rank, item in enumerate(result_list, start=1):
                scores[item.chunk_id]  += weight * (1.0 / (k + rank))
                sources[item.chunk_id]  = item   # 保留原始 SearchResult 用于携带各路分数

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
        fused = []
        for cid in sorted_ids:
            item = sources[cid]
            item.weighted_rrf_score = scores[cid]   # 写回融合分
            fused.append(item)
        return fused
```

**SearchResult 数据结构**（需包含各路原始分，便于调试接口展示）：

```python
@dataclass
class SearchResult:
    chunk_id:           str
    vector_score:       float | None = None   # 向量检索余弦相似度
    bm25_score:         float | None = None   # BM25 ts_rank 分数
    weighted_rrf_score: float | None = None   # 加权 RRF 融合分（fuse 后写入）
    rerank_score:       float | None = None   # 重排序分（rerank 后写入）
```

**调用示例**：

```python
# 等权重（默认）
fused = rrf_fusion.fuse([vec_results, bm25_results])

# 自定义权重（已归一化）
fused = rrf_fusion.fuse(
    [vec_results, bm25_results],
    weights=[0.7, 0.3]
)
```

**配置项**（系统默认权重，可通过调试接口覆盖）：
```
RRF_VECTOR_WEIGHT = 0.5
RRF_BM25_WEIGHT   = 0.5
RRF_K             = 60
```

**交付物**：`retrieval/fusion.py` + 单元测试（覆盖等权重、自定义权重、单路退化三种场景）

---

### TASK-026｜BGE-Reranker 重排序

**模块**：检索层
**优先级**：P1
**前置**：TASK-025
**描述**：使用 BGE-Reranker Cross-Encoder 对融合结果精排，取 Top-5。

```python
# retrieval/reranker.py

class BGEReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        ...

    def rerank(
        self,
        question: str,
        candidates: list[SearchResult],
        top_k: int = 5
    ) -> list[SearchResult]:
        """
        1. 构建 (question, full_text) pair 列表
        2. 批量计算 Cross-Encoder 相关性分数
        3. 按分数降序取 top_k
        4. 更新 score 字段为重排后的分数
        """
```

**配置项**：
```
RERANKER_MODEL   = "BAAI/bge-reranker-v2-m3"
RERANKER_DEVICE  = "cuda"
RERANKER_TOP_K   = 5
RETRIEVAL_TOP_K  = 50       # 粗召回数量
```

**交付物**：`retrieval/reranker.py`

---

### TASK-027｜查询改写模块

**模块**：检索层
**优先级**：P1
**前置**：TASK-016
**描述**：对用户问题进行改写扩展，提高检索命中率。

```python
# retrieval/query_rewriter.py

REWRITE_PROMPT = """请对以下用户问题进行改写，
生成1-3个语义相近但表达不同的问题变体，用于提高文档检索的召回率。
只输出改写后的问题列表，每行一个，不要有编号或其他内容。
原始问题：{question}"""

class QueryRewriter:
    def rewrite(self, question: str) -> list[str]:
        """返回原始问题 + 改写变体列表"""
```

**交付物**：`retrieval/query_rewriter.py`

---

### TASK-028｜上下文压缩模块

**模块**：检索层
**优先级**：P1
**前置**：TASK-026
**描述**：压缩召回的 chunk 内容，只保留与问题高度相关的句子，减少 LLM Token 消耗。

```python
# retrieval/context_compressor.py

class ContextCompressor:
    def compress(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        max_tokens: int = 3000
    ) -> list[RetrievedChunk]:
        """
        策略：
        1. 计算当前所有 full_text 的总 token 数
        2. 若超过 max_tokens，按 score 从低到高逐步删除低分 chunk
        3. 若单个 chunk 仍过长，按句子粒度过滤（保留与 question 相关度高的句子）
        """
```

**交付物**：`retrieval/context_compressor.py`

---

### TASK-029｜完整检索 Pipeline 串联

**模块**：检索层
**优先级**：P1
**前置**：TASK-024 ~ TASK-028
**描述**：将查询改写、多路检索、RRF 融合、重排序、上下文压缩串联为完整 Pipeline。

```python
# retrieval/pipeline.py

class RetrievalPipeline:
    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        filters: dict = None
    ) -> list[RetrievedChunk]:
        """
        1. QueryRewriter.rewrite(question) → 得到问题变体列表
        2. 对每个变体分别执行 VectorSearcher.search + BM25Searcher.search
        3. RRFFusion.fuse 合并所有结果
        4. BGEReranker.rerank → top_k
        5. 从 PostgreSQL/Milvus 补全完整 chunk 数据（elements、metadata）
        6. ContextCompressor.compress
        7. 返回 RetrievedChunk 列表
        """
```

同步更新 `RAGOrchestrator.query` 改为调用 `RetrievalPipeline.retrieve`。

**交付物**：`retrieval/pipeline.py` + 集成测试

---

### TASK-053｜数据集存储层 — 数据模型 + Store 层

**模块**：存储层 - PostgreSQL
**优先级**：P0
**前置**：TASK-002
**描述**：新增 `rag_datasets` 表管理数据集元数据（名称全局唯一），`rag_documents` 表增加可空 `dataset_id` 外键关联数据集。Milvus Schema 不变——检索过滤通过 PG 解析数据集到 doc_ids 再注入 Milvus `doc_id in [...]` 过滤条件。

**PostgreSQL DDL**：

```sql
-- 数据集表
CREATE TABLE rag_datasets (
    dataset_id    VARCHAR(64)   PRIMARY KEY,
    name          VARCHAR(256)  NOT NULL UNIQUE,   -- 数据集名称，全局唯一
    description   TEXT,
    created_by    VARCHAR(64),
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_datasets_created_at ON rag_datasets(created_at DESC);

-- rag_documents 增加数据集关联（可空，允许裸文档）
ALTER TABLE rag_documents ADD COLUMN dataset_id VARCHAR(64) REFERENCES rag_datasets(dataset_id) ON DELETE CASCADE;
CREATE INDEX idx_documents_dataset_id ON rag_documents(dataset_id);
```

**ORM 模型**：

```python
# storage/pg_models.py 新增

class DatasetORM(Base):
    __tablename__ = "rag_datasets"

    dataset_id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False, unique=True)
    description = Column(Text)
    created_by = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    documents = relationship("DocumentORM", back_populates="dataset", passive_deletes=True)
```

**DocumentORM 更新**：

```python
# storage/pg_models.py 修改

class DocumentORM(Base):
    # ... 已有字段 ...
    dataset_id = Column(String(64), ForeignKey("rag_datasets.dataset_id", ondelete="CASCADE"))

    dataset = relationship("DatasetORM", back_populates="documents")
```

**DocumentStorePort 接口新增**：

```python
# storage/ports.py DocumentStorePort 新增方法

class DocumentStorePort(ABC):
    # ... 已有方法 ...

    @abstractmethod
    async def create_dataset(self, dataset_id: str, name: str, description: str = None, created_by: str = None) -> dict: ...

    @abstractmethod
    async def get_dataset(self, dataset_id: str) -> dict | None: ...

    @abstractmethod
    async def list_datasets(self, page: int = 1, size: int = 20) -> tuple[list[dict], int]: ...

    @abstractmethod
    async def update_dataset(self, dataset_id: str, name: str = None, description: str = None) -> dict | None: ...

    @abstractmethod
    async def delete_dataset(self, dataset_id: str) -> bool: ...

    @abstractmethod
    async def count_docs_by_dataset(self, dataset_id: str) -> int: ...

    @abstractmethod
    async def get_doc_ids_by_dataset_ids(self, dataset_ids: list[str]) -> list[str]: ...

    @abstractmethod
    async def get_doc_ids_by_filenames(self, filenames: list[str]) -> list[str]: ...
```

**涉及改动**：

| 文件 | 改动 |
|------|------|
| `alembic/versions/` | 新增迁移：创建 `rag_datasets` 表，`rag_documents` 增加 `dataset_id` 列 + 索引 |
| `storage/pg_models.py` | 新增 `DatasetORM`，`DocumentORM` 增加 `dataset_id` 字段和 relationship |
| `storage/pg_store.py` | 实现 `DocumentStorePort` 新增的数据集方法 + 文档名模糊查询方法 |
| `storage/ports.py` | `DocumentStorePort` 新增数据集相关抽象方法 |

**验证**：
1. `alembic upgrade head` 成功创建 `rag_datasets` 表和索引
2. `rag_datasets.name` 的 UNIQUE 约束生效（重复名称插入报错）
3. `rag_documents` 表新增 `dataset_id` 列，外键约束生效
4. `dataset_id=NULL` 的文档可正常插入（裸文档）

**交付物**：Alembic 迁移文件 + ORM 模型更新 + Store 层实现

---

### TASK-054｜数据集 CRUD API

**模块**：用户交互层 - 数据集管理
**优先级**：P0
**前置**：TASK-053
**描述**：实现数据集的创建、查询、列表、更新、删除 REST API。删除时默认拒绝有文档的数据集，需传 `force=true` 确认后级联删除。

**接口定义**：

#### 创建数据集

```
POST /api/v1/datasets

Request Body:
{
  "name":        "2024年输电线路工程",   // 必填，全局唯一
  "description": "包含设计交底、杆塔明细等文档"  // 可选
}

Response 201:
{
  "dataset_id":  "ds_abc123",
  "name":        "2024年输电线路工程",
  "description": "包含设计交底、杆塔明细等文档",
  "created_at":  "2024-01-15T10:30:00Z",
  "updated_at":  "2024-01-15T10:30:00Z"
}

Response 409: 数据集名称已存在
```

#### 数据集列表

```
GET /api/v1/datasets?page=1&size=20

Response 200:
{
  "total":  15,
  "page":   1,
  "size":   20,
  "items": [
    {
      "dataset_id":  "ds_abc123",
      "name":        "2024年输电线路工程",
      "description": "包含设计交底、杆塔明细等文档",
      "doc_count":   5,
      "created_at":  "2024-01-15T10:30:00Z",
      "updated_at":  "2024-01-20T14:00:00Z"
    }
  ]
}
```

注意：`doc_count` 由列表接口实时 `COUNT` 查询，不在数据集表中存储。

#### 数据集详情

```
GET /api/v1/datasets/{dataset_id}

Response 200:
{
  "dataset_id":  "ds_abc123",
  "name":        "2024年输电线路工程",
  "description": "包含设计交底、杆塔明细等文档",
  "doc_count":   5,
  "created_at":  "2024-01-15T10:30:00Z",
  "updated_at":  "2024-01-20T14:00:00Z"
}

Response 404: 数据集不存在
```

#### 更新数据集

```
PATCH /api/v1/datasets/{dataset_id}

Request Body:
{
  "name":        "2024年输电线路工程（更新）",  // 可选
  "description": "新增铁塔统计文档"            // 可选
}

Response 200:
{
  "dataset_id":  "ds_abc123",
  "name":        "2024年输电线路工程（更新）",
  "description": "新增铁塔统计文档",
  "doc_count":   5,
  "updated_at":  "2024-01-25T09:00:00Z"
}

Response 404: 数据集不存在
Response 409: 新名称与其他数据集冲突
```

#### 删除数据集

```
DELETE /api/v1/datasets/{dataset_id}?force=false

Response 200 (force=true):
{ "message": "删除成功", "dataset_id": "ds_abc123" }

Response 409 (force=false 且数据集下有文档):
{ "detail": "数据集下还有 5 个文档，请先删除文档或使用 force=true" }

Response 404: 数据集不存在
```

**删除级联逻辑**（仅 `force=true` 时执行）：
1. 查询数据集下所有 `doc_id`
2. 删除 Milvus 中这些 `doc_id` 的所有向量（`delete_by_doc_id`）
3. 删除 OSS 中 `raw-docs`、`table-images`、`doc-images` 下的相关文件
4. 删除 `rag_datasets` 记录（CASCADE 自动删除 `rag_documents` 和 `rag_chunks`）

**Pydantic Schema**：

```python
# api/schemas/datasets.py

class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None

class DatasetUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None

class DatasetResponse(BaseModel):
    dataset_id:  str
    name:        str
    description: Optional[str]
    doc_count:   int
    created_at:  datetime
    updated_at:  datetime

class DatasetListResponse(BaseModel):
    total: int
    page:  int
    size:  int
    items: list[DatasetResponse]
```

**交付物**：`api/routers/datasets.py`、`api/schemas/datasets.py`、`api/main.py`（注册路由）

---

### TASK-055｜文档上传支持数据集选择

**模块**：用户交互层 + 摄入层
**优先级**：P0
**前置**：TASK-053、TASK-054、TASK-020
**描述**：修改文档上传接口，增加可选的 `dataset_id` 参数。不传则为裸文档（无数据集归属），传入时校验数据集存在性。Milvus 无需变更。

**接口变更**：

```
POST /api/v1/documents
Content-Type: multipart/form-data

Request:
  file:        binary     必填，文件内容
  dataset_id:  string     选填，目标数据集 ID（不传则为裸文档）

Response 200:
{
  "doc_id":     "doc_abc123",
  "dataset_id": "ds_abc123",    // null 表示裸文档
  "filename":   "2024年销售报告.pdf",
  "status":     "pending",
  "uploaded_at": "2024-01-15T10:30:00Z"
}

Response 404: dataset_id 指定的数据集不存在
```

**涉及改动**：

| 文件 | 改动 |
|------|------|
| `api/routers/documents.py` | 上传接口新增 `dataset_id` 参数（可选 Form 字段），传入时校验数据集存在性 |
| `api/schemas/documents.py` | `UploadResponse` 新增 `dataset_id` 可空字段 |
| `storage/pg_store.py` | `save_document` 写入 `dataset_id` |

**验证**：
1. 创建数据集 → 上传文档到该数据集 → 查询文档 `dataset_id` 有值
2. 上传文档不传 `dataset_id` → 文档 `dataset_id` 为 NULL
3. 上传到不存在的 `dataset_id` → 返回 404

**交付物**：修改上述文件

---

### TASK-056｜检索支持数据集 / 文档过滤

**模块**：检索层 + 用户交互层
**优先级**：P0
**前置**：TASK-053、TASK-055
**描述**：问答接口和调试检索接口支持 `dataset_ids`、`doc_ids`、`doc_names` 三个独立的过滤参数。过滤在 API 层通过 PostgreSQL 解析为 doc_id 列表，再注入 Milvus `doc_id in [...]` 过滤条件。检索层接口不变，只接收 `filters` 字典。

**接口变更**：

#### 问答接口

```
POST /api/v1/query

Request Body:
{
  "question":    "杆塔型号 ZM3 的呼高是多少？",
  "dataset_ids": ["ds_abc123", "ds_def456"],   // 可选，按数据集过滤
  "doc_ids":     ["doc_001", "doc_002"],        // 可选，按文档 ID 过滤
  "doc_names":   ["杆塔明细表"],                  // 可选，按文件名模糊匹配过滤
  "top_k":       5
}
```

三个过滤参数独立使用，可传 0~3 个。都不传则不过滤，搜全部。

#### 调试检索接口

```
POST /api/v1/debug/retrieve

Request Body:
{
  "question":    "杆塔型号 ZM3 的呼高是多少？",
  "dataset_ids": ["ds_abc123"],   // 可选
  "doc_ids":     [],              // 可选
  "doc_names":   [],              // 可选
  "top_k":       10,
  "search_mode": "hybrid"
}
```

**过滤解析流程**：

```python
# api/routers/query.py / debug.py

async def resolve_filters(pg_store, dataset_ids, doc_ids, doc_names) -> dict | None:
    """将业务过滤参数解析为 Milvus filters 字典"""
    doc_id_list = []

    if dataset_ids:
        ids = await pg_store.get_doc_ids_by_dataset_ids(dataset_ids)
        doc_id_list.extend(ids)

    if doc_ids:
        doc_id_list.extend(doc_ids)

    if doc_names:
        # PG 模糊匹配: filename LIKE '%keyword%'
        ids = await pg_store.get_doc_ids_by_filenames(doc_names)
        doc_id_list.extend(ids)

    if not doc_id_list:
        return None  # 不过滤

    return {"doc_id": list(set(doc_id_list))}  # 去重
```

**DocumentStorePort 新增方法**（TASK-053 已定义）：

```python
async def get_doc_ids_by_dataset_ids(self, dataset_ids: list[str]) -> list[str]:
    """SELECT doc_id FROM rag_documents WHERE dataset_id IN (...)"""

async def get_doc_ids_by_filenames(self, filenames: list[str]) -> list[str]:
    """
    SELECT doc_id FROM rag_documents
    WHERE filename LIKE '%' || :name || '%'
    支持模糊匹配
    """
```

**涉及改动**：

| 文件 | 改动 |
|------|------|
| `api/schemas/query.py` | `QueryRequest` 新增 `dataset_ids`、`doc_ids`、`doc_names` 可选字段 |
| `api/schemas/debug.py` | `RetrieveRequest` 新增 `dataset_ids`、`doc_ids`、`doc_names` 可选字段 |
| `api/routers/query.py` | 调用 `resolve_filters` 将过滤参数转为 filters，传递给 orchestrator |
| `api/routers/debug.py` | 调用 `resolve_filters` 将过滤参数转为 filters，传递给 searcher |

**检索层无需改动**：`VectorSearcher`、`BM25Searcher`、`HybridSearcher` 已支持 `filters` 参数，MilvusStore 已支持 `filters={"doc_id": [...]}` 生成 `doc_id in [...]` 表达式。

**验证**：
1. 上传 2 个文档到数据集 A，上传 1 个文档到数据集 B，上传 1 个裸文档
2. 查询 `dataset_ids=["A"]` → 只召回数据集 A 的分块
3. 查询 `doc_ids=["doc_001"]` → 只召回指定文档的分块
4. 查询 `doc_names=["杆塔"]` → 召回文件名含"杆塔"的文档分块
5. 查询 `dataset_ids=["A", "B"]` → 召回两个数据集的分块
6. 不传过滤参数 → 召回全部分块（含裸文档）
7. debug/retrieve 接口验证三种 search_mode 均支持过滤

**交付物**：修改上述文件

---

### TASK-057｜分块管理 — 存储层查询接口

**模块**：存储层
**优先级**：P1
**前置**：TASK-005、TASK-002
**描述**：扩展 DocumentStorePort 和 VectorStorePort，支持分块粒度的查询和删除。

**DocumentStorePort 新增方法**：
- `get_chunk(chunk_id) -> Optional[ChunkRecord]` — 查询单个分块
- `get_chunks_by_ids(chunk_ids) -> list[ChunkRecord]` — 按 ID 列表批量查询
- `list_chunks_by_doc(doc_id, page, size) -> tuple[list[ChunkRecord], int]` — 文档分块分页列表
- `delete_chunks_by_ids(chunk_ids) -> int` — 按 ID 列表删除分块

**VectorStorePort 新增方法**：
- `delete_by_chunk_ids(chunk_ids) -> None` — 按 chunk_id 列表删除向量

**完成标志**：PgStore 和 MilvusStore 实现上述方法，单元测试通过

---

### TASK-058｜分块管理 — REST API（列表 / 详情 / 合并 / 拆分 / 删除 / 关联）

**模块**：API 层
**优先级**：P1
**前置**：TASK-057、TASK-014（Embedder）
**描述**：提供 7 个 REST 端点，支持用户浏览和手动调整文档分块。

**端点**：

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/documents/{doc_id}/chunks` | 文档分块列表（分页） |
| GET | `/api/v1/chunks/{chunk_id}` | 分块详情（完整 elements） |
| DELETE | `/api/v1/chunks/{chunk_id}` | 删除单个分块（含 OSS 图片清理） |
| POST | `/api/v1/chunks/merge` | 合并相邻分块 |
| POST | `/api/v1/chunks/{chunk_id}/split` | 按元素索引拆分分块 |
| POST | `/api/v1/chunks/link` | 关联多个分块到同一 group_id |
| POST | `/api/v1/chunks/unlink` | 取消分块的 group_id 关联 |

**合并校验**：
1. 所有 chunk 必须存在且属于同一文档
2. 通过 PG 查询确认选定范围（最小到最大 page+chunk_index）内无遗漏 chunk（不依赖 chunk_index 连续性）
3. 合并后 full_text 不得超过 2048 字符，超出拒绝（400）
4. 若被删除 chunk 有非空 group_id，自动将该组剩余兄弟 chunk 的 group_id 清空（PG + Milvus 同步更新）

**合并逻辑**：校验通过 → 合并 elements/full_text → 生成 embedding → 删旧 + 写新（PG + Milvus）。新 chunk_id 格式：`{doc_id}_m_{uuid_hex[:8]}`

**拆分逻辑**：
- 校验 `1 <= split_at < len(elements)`
- 按 split_at 切分 elements → 各自重建 full_text + embedding → 删旧 + 写新
- 支持 `link_group` 参数（默认 `false`）：为 true 时两子 chunk 共享新 group_id；为 false 时独立

**删除逻辑**：校验 chunk 存在 → 删除 PG + Milvus 记录 → 清理 OSS 图片文件（忽略失败）

**关联逻辑（link）**：
- 校验所有 chunk 存在且属于同一文档，至少 2 个
- 若 chunk 已有 group_id，先解散旧组（将该组剩余兄弟 group_id 清空）
- 为所有指定 chunk 分配新的共享 group_id，同步更新 PG + Milvus

**取消关联（unlink）**：
- 校验所有 chunk 存在
- 将指定 chunk 的 group_id 清空，同步更新 PG + Milvus
- 若清空后原组还有其他成员，保持它们不变（不自动解散）

**完成标志**：7 个端点功能正常，边界校验返回 400，合并/拆分后 Milvus 可检索到新分块，group_id 解散/关联逻辑正确

---

## Phase 3：混合块能力完善

> 目标：段落聚合、表格截图、MixedChunk 全链路打通（Phase 1 中已有基础实现，本阶段做完整测试和边界修复）

---

### TASK-030｜表格处理集成测试

**模块**：摄入层 - 表格
**优先级**：P1
**前置**：TASK-011、TASK-012、TASK-013
**描述**：针对复杂表格场景进行全链路集成测试和修复。

**测试用例覆盖**：
- 简单表格（无合并单元格）→ 规则描述路径
- 复杂表格（含合并单元格）→ Qwen-VL 视觉路径
- 混合段落（文字 + 表格 + 文字）
- 多表格段落（一个段落含2张表格）
- 跨页段落
- Word 转 PDF 截图对齐验证

**交付物**：`tests/integration/test_table_processing.py`

---

### TASK-031｜Qwen-VL 集成

**模块**：摄入层 - 表格理解
**优先级**：P1
**前置**：TASK-012
**描述**：完整集成 Qwen-VL 视觉模型用于复杂表格理解，与主 LLM 共享 vLLM 服务。

```python
# ingestion/table_processor/vision_client.py

class VisionClient:
    def describe_table(self, image_path: str) -> str:
        """
        调用 Qwen-VL（通过 vLLM OpenAI 兼容接口）
        传入图片 base64 + 描述指令
        返回表格自然语言描述
        """
```

**配置项**：
```
VISION_MODEL         = "Qwen/Qwen2-VL-7B-Instruct"
VISION_BASE_URL      = "http://vllm-server:8000/v1"
TABLE_COMPLEX_THRESHOLD = 3    # 合并单元格数量阈值
```

**交付物**：`ingestion/table_processor/vision_client.py`

---

### TASK-032｜管理后台 API - 文档列表

**模块**：用户交互层 - 管理后台
**优先级**：P1
**前置**：TASK-002

```
GET /api/v1/admin/documents?page=1&size=20&status=done

Response 200:
{
  "total":  100,
  "page":   1,
  "size":   20,
  "items": [
    {
      "doc_id":      "doc_001",
      "filename":    "2024年销售报告.pdf",
      "file_type":   "pdf",
      "file_size":   1048576,
      "status":      "done",
      "uploaded_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**交付物**：`api/routers/admin.py`

---

### TASK-033｜管理后台 API - 文档删除

**模块**：用户交互层 - 管理后台
**优先级**：P1
**前置**：TASK-032

```
DELETE /api/v1/admin/documents/{doc_id}

Response 200:
{ "message": "删除成功", "doc_id": "doc_001" }

Response 404: 文档不存在
```

**删除逻辑**：
1. 删除 Milvus 中该 doc_id 的所有向量
2. 删除 PostgreSQL chunks 表中的记录（CASCADE 自动处理）
3. 删除 PostgreSQL documents 表中的记录
4. 删除 OSS 中 raw-docs 和 table-images 下该 doc_id 的所有文件

**交付物**：`api/routers/admin.py`（追加路由）

---

### TASK-034｜管理后台 API - 文档重新摄入

**模块**：用户交互层 - 管理后台
**优先级**：P1
**前置**：TASK-033

```
POST /api/v1/admin/documents/{doc_id}/reingest

Response 200:
{ "message": "重新摄入任务已提交", "doc_id": "doc_001" }
```

**逻辑**：从 OSS `raw-docs` 下载原始文件，清空旧索引后重新走摄入流程。

**交付物**：`api/routers/admin.py`（追加路由）

---

### TASK-035｜管理后台 API - 原始文档下载

**模块**：用户交互层 - 管理后台
**优先级**：P1
**前置**：TASK-004

```
GET /api/v1/admin/documents/{doc_id}/download

Response 200:
  Content-Type: application/octet-stream
  Content-Disposition: attachment; filename="2024年销售报告.pdf"
  Body: 文件二进制内容

Response 404: 文档不存在
```

**交付物**：`api/routers/admin.py`（追加路由）

---

## Phase 4：工程化完善

---

### TASK-036｜Redis 查询缓存

**模块**：编排层 - 缓存
**优先级**：P1
**前置**：TASK-019

```python
# orchestration/orchestrator.py（更新）

def query(self, question: str) -> QueryResponse:
    cache_key = f"query:{hashlib.md5(question.encode()).hexdigest()}"

    # 1. 查缓存
    cached = cache.get(cache_key)
    if cached:
        return QueryResponse.parse_raw(cached)  # cache_hit=True

    # 2. 正常查询流程...

    # 3. 写缓存（TTL 1小时）
    cache.set(cache_key, response.json(), ttl=3600)
    return response
```

**配置项**：
```
CACHE_QUERY_TTL     = 3600    # 秒
CACHE_EMBEDDING_TTL = 86400   # Embedding 缓存24小时
```

**交付物**：更新 `orchestration/orchestrator.py`

---

### TASK-037｜Embedding 缓存

**模块**：摄入层 + 检索层
**优先级**：P1
**前置**：TASK-014、TASK-036

```python
# ingestion/embedder.py（更新）

def embed_single(self, text: str) -> list[float]:
    cache_key = f"emb:{hashlib.md5(text.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)
    vec = self._model_embed(text)
    cache.set(cache_key, json.dumps(vec), ttl=86400)
    return vec
```

**交付物**：更新 `ingestion/embedder.py`

---

### TASK-038｜统一配置中心

**模块**：工程基础
**优先级**：P1
**前置**：TASK-001

```python
# config/settings.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # DashScope API
    DASHSCOPE_API_KEY:    str

    # 存储
    POSTGRES_URL:         str
    MILVUS_HOST:          str = "localhost"
    MILVUS_PORT:          int = 19530
    REDIS_URL:            str = "redis://localhost:6379/0"
    MINIO_ENDPOINT:       str
    MINIO_ACCESS_KEY:     str
    MINIO_SECRET_KEY:     str
    MINIO_BUCKET:         str = "rag-storage"

    # LLM（DashScope OpenAI 兼容接口）
    LLM_BASE_URL:         str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL:            str = "qwen-plus"
    LLM_TIMEOUT:          int = 30
    LLM_MAX_TOKENS:       int = 2048
    LLM_TEMPERATURE:      float = 0.1

    # Embedding（DashScope text-embedding-v2）
    EMBEDDING_MODEL:      str = "text-embedding-v2"
    EMBEDDING_DIMENSION:  int = 1024

    # Reranker（Phase 2）
    RERANKER_MODEL:       str = "BAAI/bge-reranker-v2-m3"

    # 检索参数（运行时可调）
    RETRIEVAL_TOP_K:      int = 50
    RERANKER_TOP_K:       int = 5
    MAX_CONTEXT_TOKENS:   int = 3000
    TABLE_COMPLEX_THRESHOLD: int = 999  # Phase 1 所有表格走规则路径

    # 缓存（Phase 4 启用）
    CACHE_QUERY_TTL:      int = 3600
    CACHE_EMBEDDING_TTL:  int = 86400

    # 文件限制
    MAX_FILE_SIZE_MB:     int = 50

    # 支持的文件类型
    SUPPORTED_FILE_TYPES: list[str] = ["pdf", "docx", "xlsx"]

    class Config:
        env_file = ".env"

settings = Settings()
```

**交付物**：`config/settings.py`、`.env.example`

---

### TASK-039｜结构化日志 & 监控埋点

**模块**：横切 - 可观测性
**优先级**：P1
**前置**：TASK-019

**日志格式**（JSON 结构化）：
```json
{
  "timestamp":      "2024-01-15T10:30:00Z",
  "level":          "INFO",
  "event":          "query_completed",
  "question":       "...",
  "retrieval_ms":   120,
  "llm_ms":         800,
  "total_ms":       950,
  "token_count":    512,
  "cache_hit":      false,
  "chunks_retrieved": 5,
  "top_score":      0.92
}
```

**埋点位置**：
- 摄入：文档上传、解析开始/完成、截图成功/失败、Embedding 完成
- 检索：向量检索耗时、BM25 耗时、重排序耗时
- 问答：总耗时、Token 数、缓存命中

**交付物**：`utils/logger.py` + 各模块埋点更新

---

### TASK-040｜全局错误处理 & 降级策略

**模块**：编排层 + 用户交互层
**优先级**：P1
**前置**：TASK-019

```python
# api/middleware/error_handler.py

# 降级策略：
# 1. LLM 超时（>30s）→ 重试1次 → 返回 503
# 2. Milvus 不可用 → 返回 503，提示"检索服务暂时不可用"
# 3. 检索结果为空 → 不调用 LLM，直接返回"未找到相关内容"
# 4. OSS 签名失败 → image_url 返回 null，不影响文字答案
```

**统一错误响应格式**：
```json
{
  "error_code": "LLM_TIMEOUT",
  "message":    "生成服务暂时不可用，请稍后重试",
  "request_id": "req_xxx"
}
```

**交付物**：`api/middleware/error_handler.py`

---

## Phase 5：可观测落地

---

### TASK-041｜Grafana 监控面板

**模块**：监控
**优先级**：P2
**前置**：TASK-039
**描述**：基于结构化日志配置 Grafana Dashboard。

**核心指标面板**：
- 问答 QPS 和 P99 延迟趋势
- 缓存命中率
- LLM 平均耗时 vs 检索平均耗时
- 文档摄入成功率 / 失败率
- 表格截图成功率
- 每日 Token 消耗量

**交付物**：`deploy/grafana/dashboard.json`

---

### TASK-042｜query_logs 统计 API

**模块**：用户交互层 - 管理后台
**优先级**：P2
**前置**：TASK-039

```
GET /api/v1/admin/stats?start=2024-01-01&end=2024-01-31

Response 200:
{
  "total_queries":     1200,
  "cache_hit_rate":    0.35,
  "avg_total_ms":      850,
  "avg_retrieval_ms":  120,
  "avg_llm_ms":        680,
  "total_tokens":      850000
}
```

**交付物**：`api/routers/admin.py`（追加路由）

---

## Phase 6：高级能力

---

### TASK-043｜增量更新（局部重建索引）

**模块**：摄入层 + 存储层
**优先级**：P1（Phase 4）
**前置**：TASK-015、TASK-002、TASK-003
**描述**：当已摄入文档的内容发生变化时，只删除该文档的旧索引并重新摄入，不影响其他文档。

**实现逻辑**：

```python
# ingestion/pipeline.py（新增方法）

class IngestionPipeline:
    def reingest(self, doc_id: str) -> None:
        """
        增量更新流程：
        1. 从 OSS raw-docs 下载原始文件
        2. 删除 Milvus 中该 doc_id 的所有向量（MilvusStore.delete_by_doc_id）
        3. 删除 PostgreSQL chunks 表中的分块记录（CASCADE）
        4. 删除 OSS table-images 中该 doc_id 的截图文件
        5. 重新走完整摄入流程（ingest）
        """
```

**触发方式**：
- 管理后台手动触发（TASK-034 接口已支持）
- 未来可扩展为文件变更事件自动触发（Webhook / 文件监听）

**交付物**：`ingestion/pipeline.py`（新增 reingest 方法）+ 集成测试

---

### TASK-044｜API 鉴权中间件（JWT / API Key）

**模块**：用户交互层 - 安全
**优先级**：P0（Phase 5）
**前置**：TASK-001
**描述**：为所有 API 接口添加统一鉴权，支持 JWT Token 和 API Key 两种方式。

**PostgreSQL 新增表**：

```sql
-- API Key 管理表
CREATE TABLE api_keys (
    key_id        VARCHAR(64)   PRIMARY KEY,
    key_hash      VARCHAR(128)  NOT NULL UNIQUE,   -- SHA-256 散列，不存明文
    name          VARCHAR(128),                    -- 用途说明
    created_by    VARCHAR(64),
    expires_at    TIMESTAMP,                       -- NULL 表示永不过期
    last_used_at  TIMESTAMP,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);
```

**鉴权中间件逻辑**：

```python
# api/middleware/auth.py

class AuthMiddleware:
    """
    请求头优先级：
    1. Authorization: Bearer <JWT>   → 验证 JWT 签名和过期时间，提取 user_id
    2. X-API-Key: <key>              → 对 key 做 SHA-256 后查 api_keys 表，提取 created_by 作为 user_id
    3. 两者均无                       → 返回 401

    豁免路径（无需鉴权）：
    - POST /api/v1/auth/token（JWT 登录）
    - GET  /api/v1/health
    """
```

**接口**：
```
POST /api/v1/auth/token
Body: { "username": "...", "password": "..." }
Response: { "access_token": "...", "token_type": "bearer", "expires_in": 3600 }

POST /api/v1/admin/api-keys
Body: { "name": "前端应用", "expires_at": null }
Response: { "key_id": "...", "api_key": "<明文，仅返回一次>" }

DELETE /api/v1/admin/api-keys/{key_id}
```

**交付物**：`api/middleware/auth.py`、`api/routers/auth.py`、Migration 脚本

---

### TASK-045｜文档 ACL 权限过滤

**模块**：存储层 + 检索层 - 权限控制
**优先级**：P0（Phase 5）
**前置**：TASK-044、TASK-002、TASK-018
**描述**：实现文档级访问控制，检索时自动注入当前用户有权访问的文档 ID 过滤条件。

**PostgreSQL 新增表**：

```sql
-- 文档访问控制表
CREATE TABLE document_acl (
    acl_id        SERIAL        PRIMARY KEY,
    doc_id        VARCHAR(64)   NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    user_id       VARCHAR(64)   NOT NULL,
    granted_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    granted_by    VARCHAR(64),
    UNIQUE (doc_id, user_id)
);

CREATE INDEX idx_acl_user_id ON document_acl(user_id);
CREATE INDEX idx_acl_doc_id  ON document_acl(doc_id);
```

**ACLFilter 模块**：

```python
# retrieval/acl_filter.py

class ACLFilter:
    def get_allowed_doc_ids(self, user_id: str) -> list[str]:
        """
        查询 document_acl 表，返回该用户有权访问的 doc_id 列表。
        如果用户是管理员（admin 角色），返回 None 表示不过滤。
        """

    def build_milvus_filter(self, user_id: str) -> str | None:
        """
        返回 Milvus 过滤表达式：
        'doc_id in ["doc_001", "doc_002", ...]'
        用于注入向量检索的 expr 参数。
        """

    def build_pg_filter(self, user_id: str) -> str | None:
        """
        返回 PostgreSQL WHERE 子句片段：
        "AND doc_id = ANY(:allowed_ids)"
        用于注入 BM25 检索的 SQL 查询。
        """
```

**管理接口**：
```
POST   /api/v1/admin/documents/{doc_id}/acl
Body:  { "user_id": "user_001" }
Response: { "message": "授权成功" }

DELETE /api/v1/admin/documents/{doc_id}/acl/{user_id}
Response: { "message": "撤销成功" }

GET    /api/v1/admin/documents/{doc_id}/acl
Response: { "users": ["user_001", "user_002"] }
```

**RetrievalPipeline 更新**：所有检索调用前自动注入 ACL 过滤，调用方无感知。

**交付物**：`retrieval/acl_filter.py`、`api/routers/admin.py`（追加路由）、Migration 脚本

---

### TASK-046｜管理后台参数配置 API

**模块**：用户交互层 - 管理后台
**优先级**：P1（Phase 5）
**前置**：TASK-038、TASK-044
**描述**：提供运行时读写检索参数的 API，无需重启服务即可调整系统行为。参数持久化到 PostgreSQL，启动时加载覆盖默认值。

**PostgreSQL 新增表**：

```sql
CREATE TABLE system_config (
    config_key    VARCHAR(128)  PRIMARY KEY,
    config_value  TEXT          NOT NULL,
    description   VARCHAR(512),
    updated_by    VARCHAR(64),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- 初始化默认参数
INSERT INTO system_config VALUES
    ('retrieval.top_k',            '50',   '粗召回数量', 'system', NOW()),
    ('reranker.top_k',             '5',    '重排后取 Top-K', 'system', NOW()),
    ('rrf.vector_weight',          '0.5',  'RRF 向量检索权重', 'system', NOW()),
    ('rrf.bm25_weight',            '0.5',  'RRF BM25 权重', 'system', NOW()),
    ('llm.max_tokens',             '2048', 'LLM 最大输出 Token', 'system', NOW()),
    ('llm.temperature',            '0.1',  'LLM Temperature', 'system', NOW()),
    ('table.complex_threshold',    '3',    '触发视觉模型的合并单元格阈值', 'system', NOW()),
    ('context.max_tokens',         '3000', 'Prompt 上下文最大 Token', 'system', NOW()),
    ('cache.query_ttl',            '3600', '查询缓存过期时间（秒）', 'system', NOW());
```

**接口**：
```
GET /api/v1/admin/config
Response: { "configs": [{ "key": "retrieval.top_k", "value": "50", "description": "..." }] }

PATCH /api/v1/admin/config
Body: { "key": "retrieval.top_k", "value": "30" }
Response: { "message": "更新成功", "key": "retrieval.top_k", "value": "30" }
```

**Settings 模块更新**：启动时从 `system_config` 表加载配置，运行时变更通过 Redis Pub/Sub 通知各进程热更新。

**交付物**：`api/routers/admin.py`（追加路由）、`config/dynamic_settings.py`、Migration 脚本

---

### TASK-047｜多跳推理

**模块**：编排层
**优先级**：P2（Phase 6）
**前置**：TASK-029、TASK-019
**描述**：对需要跨文档、跨段落联合推理的复杂问题，自动触发多轮检索，每轮基于上一轮的中间结果生成新的子问题，最终合并生成答案。

**判断逻辑**：

```python
# orchestration/multi_hop.py

MULTI_HOP_PROMPT = """判断以下问题是否需要查阅多个独立信息源才能回答（是/否）：
问题：{question}
如果问题中包含"比较"、"区别"、"关系"、"影响"、"同时"等需要联合多个信息的词语，回答"是"。"""

class MultiHopOrchestrator:
    def needs_multi_hop(self, question: str) -> bool:
        """调用 LLM 判断，结果缓存 1 小时"""

    def query(self, question: str, user_id: str = None) -> QueryResponse:
        """
        多跳推理流程（最多 3 跳）：
        1. 第 1 跳：对原始问题检索，得到 contexts_1
        2. 用 LLM 基于 contexts_1 生成中间答案和子问题列表
        3. 第 2 跳：对子问题检索，得到 contexts_2
        4. 合并 contexts_1 + contexts_2，生成最终答案
        5. 若仍不足，执行第 3 跳（上限保护，避免无限循环）
        """
```

**RAGOrchestrator 更新**：`query()` 方法增加 `if self.needs_multi_hop(question)` 分支，路由到 `MultiHopOrchestrator`。

**交付物**：`orchestration/multi_hop.py`、`orchestration/orchestrator.py`（更新）

---

### TASK-048｜备用 LLM 降级切换

**模块**：编排层 - 容错
**优先级**：P1（Phase 6）
**前置**：TASK-016
**描述**：当主 LLM（Qwen vLLM）不可用时，自动降级到备用模型，保障服务可用性。

```python
# orchestration/llm_client.py（新增）

class FallbackLLMClient(LLMClient):
    def __init__(self, primary: LLMClient, fallback: LLMClient, timeout: int = 30):
        self.primary  = primary
        self.fallback = fallback
        self.timeout  = timeout

    def complete(self, messages: list[dict], stream: bool = False) -> str | Generator:
        """
        策略：
        1. 调用 primary，设置 timeout
        2. 超时或连接失败 → 记录日志，切换 fallback
        3. fallback 也失败 → 抛出 LLMUnavailableError，触发 TASK-040 降级响应
        """
```

**配置项**：
```
LLM_FALLBACK_BASE_URL   = "https://api.openai.com/v1"   # 或 Claude API
LLM_FALLBACK_MODEL      = "gpt-4o-mini"
LLM_FALLBACK_API_KEY    = "sk-..."
LLM_PRIMARY_TIMEOUT     = 30
```

**交付物**：`orchestration/llm_client.py`（更新）、`.env.example`（追加备用模型配置项）

---

### TASK-049｜签名 URL 统一服务模块

**模块**：存储层 - 安全
**优先级**：P0（Phase 5）
**前置**：TASK-004
**描述**：将分散在 TASK-004、TASK-019 中的签名 URL 生成逻辑统一抽取为独立服务模块，所有 image_url 的签名操作统一经过此模块。

```python
# storage/signed_url_service.py

class SignedUrlService:
    def __init__(self, oss: ObjectStorePort, default_expire: int = 3600):
        self.oss     = oss
        self.default = default_expire

    def sign(self, path: str, expire_seconds: int = None) -> str:
        """
        对 OSS 内部路径生成签名 URL。
        path 为空或 None 时直接返回 None（文字元素无图片）。
        """

    def sign_chunks(self, chunks: list[RetrievedChunk], expire_seconds: int = None) -> list[RetrievedChunk]:
        """
        批量对召回结果中所有 element.image_url 签名替换。
        原始内部路径不对外暴露。
        """

    def sign_raw_doc(self, doc_id: str, filename: str, expire_seconds: int = None) -> str:
        """
        对原始文档生成带时效的下载 URL（用于 TASK-035 下载接口）。
        """
```

**调用方更新**：
- `RAGOrchestrator.post_process` → 改为调用 `SignedUrlService.sign_chunks`
- `admin/documents/download` → 改为调用 `SignedUrlService.sign_raw_doc`
- `OSSStore.sign_url` 保留底层实现，上层统一走 `SignedUrlService`

**交付物**：`storage/signed_url_service.py` + 更新 `orchestration/orchestrator.py`、`api/routers/admin.py`

---

### TASK-050｜vLLM 推理服务部署配置

**模块**：部署 - 推理服务
**优先级**：P0（Phase 1 前完成）
**前置**：TASK-001
**描述**：配置 vLLM 服务用于 Qwen 主模型和 Qwen-VL 视觉模型的推理，提供 OpenAI 兼容接口。

**docker-compose 服务定义**：

```yaml
# docker-compose.yml（追加）

services:
  vllm-qwen:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
    command: >
      --model Qwen/Qwen2.5-7B-Instruct
      --served-model-name qwen-chat
      --max-model-len 8192
      --tensor-parallel-size 1
      --gpu-memory-utilization 0.6
      --port 8000
    ports:
      - "8000:8000"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  vllm-qwen-vl:
    image: vllm/vllm-openai:latest
    runtime: nvidia
    environment:
      - NVIDIA_VISIBLE_DEVICES=1
    command: >
      --model Qwen/Qwen2-VL-7B-Instruct
      --served-model-name qwen-vl
      --max-model-len 4096
      --gpu-memory-utilization 0.5
      --port 8001
    ports:
      - "8001:8001"
    volumes:
      - ~/.cache/huggingface:/root/.cache/huggingface
```

**GPU 资源规划**：

| 模型 | 显存占用 | 推荐 GPU |
|------|---------|---------|
| Qwen2.5-7B-Instruct | ~16GB | A100 40G / 4090 24G × 1 |
| Qwen2-VL-7B-Instruct | ~16GB | A100 40G / 4090 24G × 1 |
| 仅有单卡时 | 共享 | 两模型分时调用，`gpu-memory-utilization=0.45` |

**单卡共享配置**（资源受限时）：

```yaml
  vllm-shared:
    command: >
      --model Qwen/Qwen2.5-7B-Instruct
      --gpu-memory-utilization 0.45
      --max-model-len 4096
```

视觉任务降级为 `pdfplumber` 规则描述，不调用 Qwen-VL。

**配置项**（`.env`）：
```
VLLM_QWEN_URL    = "http://vllm-qwen:8000/v1"
VLLM_QWEN_VL_URL = "http://vllm-qwen-vl:8001/v1"
SINGLE_GPU_MODE  = false    # true 时禁用 Qwen-VL，表格全走规则描述
```

**交付物**：`docker-compose.yml`（更新）、`deploy/vllm/README.md`（部署说明）、`config/settings.py`（追加配置项）

---

## 附录：任务依赖关系汇总

```
TASK-001（工程初始化）
    ├── TASK-002（PG 建表）
    ├── TASK-003（Milvus 初始化）
    ├── TASK-004（MinIO 初始化）← TASK-049（签名URL服务）依赖此项
    └── TASK-006（数据模型）
            │
            ├── TASK-005（StoragePort）← 依赖 002/003/004
            ├── TASK-007（PDF Parser - pymupdf）
            │       ├── TASK-008（Word Parser - python-docx）
            │       ├── TASK-008d（Excel Parser - openpyxl）← Phase 1 新增
            │       ├── TASK-008b（HTML Parser）← Phase 4
            │       └── TASK-008c（Markdown Parser）← Phase 4
            └── TASK-014（Embedder - DashScope text-embedding-v2）
                    │
                    ├── TASK-009（Parser 注册表）← 依赖 007/008/008d/008b/008c
                    │       └── TASK-010（段落聚合）
                    │               ├── TASK-011（表格截图）← 依赖 004
                    │               ├── TASK-012（表格描述 - Phase 1 仅规则路径）
                    │               ├── TASK-051（文档图片提取）← 依赖 004/007/008
                    │               └── TASK-013（Chunk 组装）← 依赖 011/012/051
                    │                       └── TASK-015（摄入 Pipeline - 同步版）← 依赖 009~014
                    │                               └── TASK-015b（重试/死信队列）← Phase 4，依赖 Celery
                    │                                       └── TASK-043（增量更新）← 依赖 015/015b
                    │
                    └── TASK-018（向量检索）← 依赖 003
                            │
                            ├── TASK-016（LLM 客户端 - DashScope）
                            │       ├── TASK-017（Prompt 构建）
                            │       │       └── TASK-019（编排主流程）← 依赖 016/017/018
                            │       │               └── TASK-047（多跳推理）← Phase 6
                            │       └── TASK-048（备用LLM降级）← Phase 6
                            │
                            ├── TASK-024（BM25）← 依赖 002，Phase 2
                            ├── TASK-025（RRF 加权融合）← 依赖 018/024，Phase 2
                            ├── TASK-026（Reranker）← 依赖 025，Phase 2
                            ├── TASK-027（查询改写）← 依赖 016，Phase 2
                            ├── TASK-028（上下文压缩）← 依赖 026，Phase 2
                            └── TASK-029（检索 Pipeline）← 依赖 024~028，Phase 2
                                    └── TASK-045（ACL 过滤注入）← Phase 5，依赖 044

TASK-019 → TASK-020/021/022/023b（API 接口）
TASK-029 → 更新 TASK-019

数据集管理依赖链（Phase 2）：
TASK-002 → TASK-053（数据集存储层：PG 表 + ORM + Store，Milvus 不变）
TASK-053 → TASK-054（数据集 CRUD API，含 force 删除）
TASK-053 + TASK-020 → TASK-055（文档上传支持可选 dataset_id）
TASK-053 + TASK-055 → TASK-056（检索支持 dataset_ids / doc_ids / doc_names 过滤，PG 解析 → Milvus doc_id 过滤）

安全 / 工程化依赖链：
TASK-001 → TASK-044（JWT/API Key 鉴权）← Phase 5
TASK-044 → TASK-045（ACL 权限过滤）← Phase 5
TASK-044 → TASK-046（参数配置 API）← Phase 5
TASK-004 → TASK-049（签名URL统一服务）← Phase 5
TASK-049 → 更新 TASK-019（orchestrator.post_process）
TASK-049 → 更新 TASK-035（文档下载接口）
TASK-038 → TASK-046（动态参数配置）

已取消 / 推迟的任务：
- TASK-050（vLLM 部署）→ 已取消，使用 DashScope 云端 API
- TASK-023（WebSocket 流式接口）→ 推迟到 Phase 2
- TASK-031（Qwen-VL 集成）→ 推迟到 Phase 3
```

---

*共计 60 个开发任务（含新增 TASK-008d、TASK-051~056），覆盖 7 个 Phase。*
*Phase 1 按 Batch 1~5 顺序开发，使用 DashScope 云端 API 替代 vLLM 本地部署，同步摄入替代 Celery 异步队列。*
*建议按 Phase 1 开发顺序分批提交，确保每个 Batch 的测试通过后再进入下一个 Batch。*
*Phase 2 新增数据集管理功能（TASK-053~056），支持文档按数据集组织、检索时按数据集过滤。*
