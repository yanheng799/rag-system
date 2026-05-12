# RAG 系统整体设计文档

> 版本：v1.7 | 状态：Phase 2 开发中

---

## 一、项目目标

构建一套**生产级 RAG（检索增强生成）系统**，实现以下核心目标：

- **精准检索**：在大规模文档库中准确找到与问题相关的内容
- **可信生成**：基于检索内容生成答案，附带来源溯源，抑制幻觉
- **易维护扩展**：分层解耦设计，任意组件可独立替换升级
- **用户友好**：提供 REST API、流式对话、可视化管理后台三种接入方式

---

## 二、功能需求

### 2.1 数据摄入

- 支持多格式文档解析：PDF、Word (.docx)、Excel (.xlsx)，各格式有独立 Parser 实现，通过插件注册表统一管理。旧格式 (.doc, .xls) 及 HTML/Markdown 支持推迟到后续 Phase
- 智能分块：按语义段落边界切割，保持段落内文字与表格的整体性
- 元数据提取：来源、时间、作者、章节等自动提取
- Phase 1 同步摄入，Phase 4 引入 Celery 异步任务队列，支持失败自动重试（最多 3 次），超限后进入死信队列并告警
- **混合块支持**：同一段落内的文字与表格作为一个整体分块，召回时文字描述与表格截图一并返回
- **文档图片提取**：提取 PDF/Word 文档中内嵌的图片（施工图、示意图、设备照片等），上传至对象存储，作为上下文补充返回给用户
- **分块关联合并**：大段落因 `max_chunk_size` 被拆分为多个子分块时，通过 `group_id` 关联；检索命中任一子分块时自动合并返回完整段落内容
- **增量更新**：文档内容变化时，仅删除该文档的旧向量和分块记录，重新摄入生成新索引，无需重建全量索引

### 2.2 检索能力

- 混合检索：向量语义检索 + BM25 关键词检索结合，加权 RRF 算法融合结果，vector/bm25 权重可配置
- 多路召回与重排序：粗召回 20-50 条候选，精排后取 Top-5
- 查询改写：对模糊问题自动扩展，提高命中率
- 上下文压缩：裁剪无关内容，减少送入 LLM 的 Token 数量
- **权限过滤**：检索前自动根据当前用户的 ACL 注入文档 ID 过滤条件，确保用户只能召回有权限的内容
- **多跳推理**：对需要跨文档联合推理的复杂问题，自动触发多轮检索与中间答案合并，再生成最终答案

### 2.3 生成与可信度

- 来源溯源：每个答案标注文档来源和具体段落
- 幻觉抑制：系统提示严格限制模型只基于检索内容作答
- 置信度评估：检索结果不足时明确告知用户

### 2.4 数据集管理

- **数据集创建**：用户通过 API 创建数据集，指定名称（全局唯一）和描述，系统自动分配 `dataset_id`
- **文档归属**：文件上传时可选择目标数据集（选填），文档归属于指定数据集；也可上传不属于任何数据集的裸文档
- **范围检索**：问答和调试接口支持按数据集 ID、文档 ID、文档名称（模糊匹配）独立过滤，缩小召回范围
- **安全删除**：有文档的数据集默认拒绝删除，需传 `force=true` 确认后级联删除其下所有文档（含分块记录、向量索引、OSS 文件）
- **过滤解析**：检索过滤不侵入 Milvus Schema，在 API 层通过 PostgreSQL 解析数据集 ID / 文档名称为 doc_id 列表，再注入 Milvus `doc_id in [...]` 过滤条件

### 2.5 工程与运维

- 增量更新：文档变化时只重建变化部分的索引
- 查询缓存：高频问题缓存结果，降低延迟和成本
- 权限控制：文档级别 ACL，不同用户访问不同内容
- 可观测性：记录检索召回率、答案质量、延迟等指标

---

## 三、系统架构

### 3.1 整体分层设计

核心原则：**每一层只做一件事**，层与层之间通过标准接口通信。

```
┌─────────────────────────────────────┐
│         用户交互层 (Interface)        │  REST API / WebSocket / 管理后台
├─────────────────────────────────────┤
│         编排调度层 (Orchestration)    │  LangChain Pipeline
├─────────────────────────────────────┤
│         检索增强层 (Retrieval)        │  BGE-Reranker + 混合检索
├─────────────────────────────────────┤
│         存储索引层 (Storage)          │  Milvus + PostgreSQL + 对象存储
├─────────────────────────────────────┤
│         数据摄入层 (Ingestion)        │  pymupdf + python-docx + openpyxl + 混合块处理
└─────────────────────────────────────┘
```

### 3.2 第一层：数据摄入层

**职责**：将原始文档转化为可检索的标准格式。Phase 1 采用同步执行，Phase 4 引入 Celery 异步队列。

#### 3.2.1 段落边界识别与混合块组装

解析器输出的是扁平的 Element 列表（文字、表格、图片交替），需要先按语义段落边界聚合，再组装为统一的 Chunk 结构。

```
原始文档段落示例：
┌─────────────────────────────┐
│  文字：Q1各区域完成情况如下：  │
│  ┌───┬──────┬──────┐        │
│  │区域│目标  │实际  │        │  ← 表格属于这个段落
│  ├───┼──────┼──────┤        │
│  │华东│111万 │120万 │        │
│  └───┴──────┴──────┘        │
│  文字：其中华东超额完成8%…   │
└─────────────────────────────┘
         ↓ 整体作为一个 MixedChunk
```

**段落边界聚合逻辑（伪代码）**：

```python
def group_elements_by_paragraph(elements):
    paragraphs = []
    current_group = []
    for elem in elements:
        if is_new_paragraph_boundary(elem, current_group):
            if current_group:
                paragraphs.append(current_group)
            current_group = [elem]
        else:
            current_group.append(elem)  # 文字、表格、图片都加入当前段落组
    return paragraphs
```

#### 3.2.2 完整摄入流程

```
原始文档（PDF / Word）
        │
        ▼
[pymupdf / python-docx / openpyxl 解析]  →  扁平 Element 列表（文字、表格、图片交替）
        │
        ▼
[段落边界识别]  →  按坐标 + 语义将 Elements 聚合为段落组
        │
        ▼
[判断段落类型]
        │
        ├── 纯文字段落  ──────────────────────────────────────┐
        │                                                     │
        ├── 纯表格段落  ──▶ [截图] + [语义描述生成] ────────────┤
        │                                                     │
        └── 混合段落    ──▶ [逐元素处理]                       │
                               │                             │
                    ┌──────────┼──────────┐                  │
                    ▼          ▼          ▼                  │
              文字元素     表格元素     图片元素               │
              直接保留     截图→OSS    提取→OSS               │
              content     语义描述    占位文本                 │
                          →content   →content                │
                    └──────────┬──────────┘                  │
                               ▼                             │
                      [组装 MixedChunk]                      │
                      拼接 full_text                         │
                      收集 image_urls                        │
                      生成 chunk_id 与元数据                  │
                               │                             │
                               └─────────────────────────────┤
                                                             ▼
                                                   [Embedding]
                                                   只对 full_text 向量化
                                                   1个段落 = 1条向量记录
                                                             │
                                                             ▼
                                                   [写入 Milvus]
                                                   elements JSON 作为 metadata
```

#### 3.2.3 Chunk 数据结构定义

```python
@dataclass
class ContentElement:
    type:      str        # "text" | "table" | "image"
    content:   str        # 文字原文 / 表格语义描述 / 图片占位文本（送入 LLM）
    image_url: str | None # table 和 image 有值，文字元素为 None

@dataclass
class ChunkMetadata:
    chunk_id:    str       # 全局唯一 ID，格式：{doc_id}_p{page}_c{index}
    chunk_type:  str       # "text" | "table" | "mixed" | "image"
    source:      str       # 原始文档文件名
    page:        int       # 所在页码
    chunk_index: int       # 该页第几个分块（从 0 起）
    char_count:  int       # full_text 字符数
    created_at:  str       # 摄入时间，ISO 8601 格式
    doc_id:      str       # 所属文档 ID
    group_id:    str       # 分块组标识，空串表示独立分块；非空表示属于同一逻辑段落（因超长拆分）

@dataclass
class MixedChunk:
    metadata:   ChunkMetadata
    elements:   list[ContentElement]  # 段落内有序子元素，保持原文顺序
    full_text:  str                   # 所有 content 拼接，用于向量化
    image_urls: list[str]             # 段落内所有图片/表格截图 URL 的快速索引
```

**实例**：

```python
MixedChunk(
    metadata = ChunkMetadata(
        chunk_id    = "doc_001_p3_c2",
        chunk_type  = "mixed",
        source      = "2024年销售报告.pdf",
        page        = 3,
        chunk_index = 2,
        char_count  = 128,
        created_at  = "2024-01-15T10:30:00Z",
        doc_id      = "doc_001"
    ),
    elements = [
        ContentElement(
            type      = "text",
            content   = "Q1各区域完成情况如下：",
            image_url = None
        ),
        ContentElement(
            type      = "table",
            content   = "表格：华东目标111万实际120万，华南目标95万实际98万……",
            image_url = "table-images/doc_001_p3_t1.png"
        ),
        ContentElement(
            type      = "image",
            content   = "[图片: 施工现场总平面布置图]",
            image_url = "doc-images/doc_001_p3_img1.png"
        ),
        ContentElement(
            type      = "text",
            content   = "其中华东区超额完成8%，为全年最佳表现区域。",
            image_url = None
        ),
    ],
    full_text  = "Q1各区域完成情况如下：表格：华东目标111万实际120万……[图片: 施工现场总平面布置图]其中华东区超额完成8%……",
    image_urls = ["table-images/doc_001_p3_t1.png", "doc-images/doc_001_p3_img1.png"]
)
```

### 3.3 第二层：存储索引层

五库协同，统一通过 `StoragePort` 接口访问。

| 存储类型 | 选型 | 存储内容 |
|----------|------|---------|
| 向量数据库 | Milvus | Embedding 向量 + elements/metadata JSON |
| 文档数据库 | PostgreSQL | 文档管理信息、完整分块记录、查询日志 |
| 对象存储 | MinIO / S3 | **原始文档文件**（PDF、Word、Excel 原件）+ 表格截图 + 文档图片 |
| 缓存层 | Redis | Phase 4 引入：查询结果缓存、Embedding 缓存、Celery Broker |
| 任务队列 | Celery + Redis | Phase 4 引入：异步摄入任务调度、失败重试（最多 3 次）、死信队列 |

**对象存储目录结构**：

```
MinIO / S3
├── /raw-docs/                      ← 原始文档原件
│     ├── doc_001.pdf
│     ├── doc_002.docx
│     └── ...
│
├── /table-images/                  ← 表格截图
│     ├── doc_001_p3_t1.png
│     ├── doc_001_p5_t2.png
│     └── ...
│
└── /doc-images/                    ← 文档内嵌图片
      ├── doc_001_p3_img1.png
      ├── doc_001_p5_img2.png
      └── ...
```

原始文档与截图使用同一套对象存储，目录隔离，统一权限管理。原始文档的主要用途：

| 用途 | 说明 |
|------|------|
| 重新摄入 | 分块策略或 Embedding 模型升级时，无需用户重新上传 |
| 用户下载 | 管理后台支持查看和下载原始文件 |
| 溯源核查 | 用户对答案存疑时，可直接取原始文件核对 |

**PostgreSQL 数据管理表**：

```sql
-- 数据集表
CREATE TABLE datasets (
    dataset_id    VARCHAR(64)   PRIMARY KEY,
    name          VARCHAR(256)  NOT NULL UNIQUE,    -- 数据集名称，全局唯一
    description   TEXT,
    created_by    VARCHAR(64),
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_datasets_created_at ON datasets(created_at DESC);

-- 文档管理表（原始文件信息）
CREATE TABLE documents (
    doc_id        VARCHAR(64)   PRIMARY KEY,
    dataset_id    VARCHAR(64)   REFERENCES datasets(dataset_id) ON DELETE CASCADE,  -- 可空，裸文档无数据集归属
    filename      VARCHAR(512)  NOT NULL,
    raw_file_url  VARCHAR(1024) NOT NULL,          -- 原始文件在 OSS 的内部路径（非签名URL）
    file_size     BIGINT,                          -- 文件大小（字节）
    file_type     VARCHAR(16),                     -- pdf | docx | xlsx
    status        VARCHAR(16)   NOT NULL DEFAULT 'pending',
                                                   -- pending | processing | done | failed
    error_msg     TEXT,                            -- 失败时记录错误信息
    retry_count   INT           NOT NULL DEFAULT 0, -- 已重试次数
    created_by    VARCHAR(64),                     -- 上传用户 ID
    uploaded_at   TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_dataset_id ON documents(dataset_id);

-- 分块记录表（摄入后的分块详情）
CREATE TABLE chunks (
    chunk_id      VARCHAR(128)  PRIMARY KEY,       -- 格式：{doc_id}_p{page}_c{index}
    doc_id        VARCHAR(64)   NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_type    VARCHAR(16)   NOT NULL,           -- text | table | mixed
    full_text     TEXT          NOT NULL,
    elements      JSONB         NOT NULL,           -- ContentElement 有序列表
    image_urls    JSONB         NOT NULL DEFAULT '[]',
    page          INT           NOT NULL,
    chunk_index   INT           NOT NULL,
    char_count    INT           NOT NULL,
    created_at    TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- 查询日志表（监控 / 统计用）
CREATE TABLE query_logs (
    log_id            VARCHAR(64)  PRIMARY KEY,
    question          TEXT         NOT NULL,
    answer            TEXT,
    retrieved_chunks  JSONB,                       -- 召回的 chunk_id 列表及分数
    retrieval_ms      INT,
    llm_ms            INT,
    total_ms          INT,
    token_count       INT,
    cache_hit         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by        VARCHAR(64),
    created_at        TIMESTAMP    NOT NULL DEFAULT NOW()
);
```

**Milvus Schema**：

```python
fields = [
    FieldSchema("id",          DataType.INT64,        is_primary=True),
    FieldSchema("embedding",   DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema("full_text",   DataType.VARCHAR,      max_length=8192),
    FieldSchema("chunk_type",  DataType.VARCHAR,      max_length=16),    # text | table | mixed
    FieldSchema("elements",    DataType.VARCHAR,      max_length=16384), # JSON 序列化的有序子元素
    FieldSchema("image_urls",  DataType.VARCHAR,      max_length=2048),  # JSON 数组，快速取图
    FieldSchema("chunk_id",    DataType.VARCHAR,      max_length=64),
    FieldSchema("doc_id",      DataType.VARCHAR,      max_length=64),
    FieldSchema("group_id",    DataType.VARCHAR,      max_length=128),   # 分块组标识（拆分关联）
    FieldSchema("source",      DataType.VARCHAR,      max_length=256),
    FieldSchema("page",        DataType.INT32),
    FieldSchema("chunk_index", DataType.INT32),
    FieldSchema("char_count",  DataType.INT32),
    FieldSchema("created_at",  DataType.VARCHAR,      max_length=32),
]
```

**StoragePort 接口**隔离具体实现，未来替换向量库只修改实现类，业务代码不变。

### 3.4 第三层：检索增强层

检索流水线（Pipeline）设计，每个节点独立可替换：

```
用户问题 (+ 可选过滤: dataset_ids / doc_ids / doc_names)
   │
   ▼
[查询理解]   → 意图识别、关键词提取、查询改写
   │
   ▼
[过滤解析]   → API 层将 dataset_ids / doc_names 通过 PG 解析为 doc_ids 列表
   │
   ▼
[多路检索]   → 向量检索 ║ BM25 关键词检索
   │            注入 doc_id in [...] 过滤条件（来源于数据集/文档ID/文档名称）
   ▼
[结果融合]   → RRF 算法合并多路结果
   │
   ▼
[重排序]     → BGE-Reranker Cross-Encoder 精排 Top-5
   │
   ▼
[上下文压缩] → 只保留与问题相关的句子（基于 full_text）
   │
   ▼
输出：RetrievedChunk 列表（含完整 elements 和 metadata）
```

**召回结果数据结构**：

```python
@dataclass
class RetrievedChunk:
    metadata:   ChunkMetadata        # 完整分块元数据
    elements:   list[ContentElement] # 有序子元素，含 image_url
    full_text:  str                  # 完整文本，已送入 LLM
    image_urls: list[str]            # 快速访问所有截图 URL
    score:      float                # 召回相关性分数（重排后）
```

**分块关联合并**：大段落因 `max_chunk_size` 被拆分时，所有子分块共享同一个 `group_id`。向量检索命中任一子分块后：

1. 收集结果中所有非空的 `group_id`
2. 批量查询 Milvus 获取同组全部兄弟分块
3. 按 `(page, chunk_index)` 排序后拼接 `full_text`，合并为完整段落
4. 去重：同组多个命中只保留一个合并结果，取最高分

```
段落组 (1545 chars) → 拆分为:
  子分块A (877 chars, group_id="doc_xxx_g3")
  子分块B (668 chars, group_id="doc_xxx_g3")

检索命中 子分块B (score=0.85)
  → 获取 group_id="doc_xxx_g3" 的所有兄弟
  → 合并 A + B 的 full_text
  → 返回完整段落 (1545 chars, score=0.85)
```

**性能策略**：粗召回阶段取 Top 20-50，重排序后取 Top 5，平衡召回率与延迟。

### 3.5 第四层：编排调度层

```python
class RAGOrchestrator:
    def query(self, question):
        # 1. 判断是否需要多跳推理
        if needs_multi_hop(question):
            chunks = multi_hop_retrieve(question)
        else:
            chunks = single_retrieve(question)

        # 2. 构建 Prompt（只用 full_text，image_url 不进 Prompt）
        prompt = prompt_builder.build(question, chunks)

        # 3. 调用 LLM（通过统一接口，可热替换）
        answer = llm_client.complete(prompt)

        # 4. 后处理：来源标注 + image_url 签名
        return post_process(answer, chunks)

    def post_process(self, answer, chunks):
        # 对 image_url 生成带时效的签名 URL（权限控制）
        for chunk in chunks:
            for elem in chunk.elements:
                if elem.image_url:
                    elem.image_url = oss_client.sign_url(elem.image_url, expire=3600)
        return build_response(answer, chunks)
```

同时负责：流式输出、超时重试、降级策略（检索失败时的兜底处理）。

### 3.6 第五层：用户交互层

| 接口类型 | 协议 | 适用场景 |
|----------|------|---------|
| REST API | HTTP | 标准问答，同步返回 |
| WebSocket | WS | 流式对话，实时输出 |
| 管理后台 | HTTP | 文档上传、索引状态、参数调整、日志查看 |

**API 端点一览**：

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/v1/datasets` | 创建数据集 |
| GET | `/api/v1/datasets` | 数据集列表（分页） |
| GET | `/api/v1/datasets/{dataset_id}` | 数据集详情 |
| PATCH | `/api/v1/datasets/{dataset_id}` | 更新数据集（名称/描述） |
| DELETE | `/api/v1/datasets/{dataset_id}?force=false` | 删除数据集（有文档时需 `force=true`） |
| POST | `/api/v1/documents` | 上传文档（`dataset_id` 选填） |
| POST | `/api/v1/query` | 问答（支持 `dataset_ids` / `doc_ids` / `doc_names` 过滤） |
| POST | `/api/v1/debug/retrieve` | 调试检索（支持 `dataset_ids` / `doc_ids` / `doc_names` 过滤） |

---

## 四、召回响应结构

### 4.1 完整响应格式

召回结果在 `sources` 数组中返回，每个元素包含 **`metadata`（分块元数据）** 和 **`elements`（有序内容列表）** 两个核心字段。

```json
{
  "answer": "根据文档第3页，华东区Q1实际完成120万，超出目标8%，为全年最佳表现区域……",

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
        {
          "type":      "text",
          "content":   "Q1各区域完成情况如下：",
          "image_url": null
        },
        {
          "type":      "table",
          "content":   "表格：华东目标111万实际120万，华南目标95万实际98万……",
          "image_url": "https://oss.example.com/tables/doc_001_p3_t1.png?token=xxx&expires=1706000000"
        },
        {
          "type":      "text",
          "content":   "其中华东区超额完成8%，为全年最佳表现区域。",
          "image_url": null
        }
      ]
    },
    {
      "metadata": {
        "chunk_id":    "doc_001_p4_c0",
        "chunk_type":  "text",
        "source":      "2024年销售报告.pdf",
        "page":        4,
        "chunk_index": 0,
        "char_count":  95,
        "created_at":  "2024-01-15T10:30:00Z",
        "doc_id":      "doc_001",
        "score":       0.78
      },
      "elements": [
        {
          "type":      "text",
          "content":   "Q2完成率下滑的主要原因是原材料供应链出现延迟，导致交付周期拉长……",
          "image_url": null
        }
      ]
    }
  ]
}
```

### 4.2 字段说明

**metadata 字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `chunk_id` | string | 分块全局唯一 ID，格式 `{doc_id}_p{page}_c{index}` |
| `chunk_type` | string | 分块类型：`text` / `table` / `mixed` |
| `source` | string | 原始文档文件名 |
| `page` | int | 所在页码 |
| `chunk_index` | int | 该页第几个分块（从 0 起） |
| `char_count` | int | full_text 字符数 |
| `created_at` | string | 文档摄入时间，ISO 8601 格式 |
| `doc_id` | string | 所属文档唯一 ID |
| `score` | float | 重排序后的相关性分数（0~1） |

**elements 子元素字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 元素类型：`text` / `table` / `image` |
| `content` | string | 文字原文、表格语义描述或图片占位文本，用于 LLM 推理 |
| `image_url` | string / null | 表格截图或文档图片的签名 URL（1小时有效），文字元素为 null |

### 4.3 前端渲染逻辑

```
for each source in sources:
    展示来源标注（source.metadata.source + 第 page 页）

    for each element in source.elements:
        if element.type == "text":
            渲染文字段落

        if element.type == "table":
            渲染 <img src={element.image_url} />
            渲染折叠的语义描述（可点击展开，便于复制文字）

        if element.type == "image":
            渲染 <img src={element.image_url} />
            渲染图片占位文本（可折叠）
```

### 4.4 LLM Prompt 构建规则

`image_url` 不进入 Prompt，LLM 只接收文字内容：

```
[来源1 - 第3页 - mixed]
Q1各区域完成情况如下：
表格：华东目标111万实际120万，华南目标95万实际98万……
其中华东区超额完成8%，为全年最佳表现区域。

[来源2 - 第4页 - text]
Q2完成率下滑的主要原因是原材料供应链出现延迟……
```

---

## 五、技术选型

### 5.1 选型总览

| 层次 | 技术 | 说明 |
|------|------|------|
| 文档解析（PDF） | pymupdf (fitz) | 快速、精确的文字+坐标+表格提取 |
| 文档解析（Word） | python-docx | 直接访问 .docx 表格结构，含合并单元格信息 |
| 文档解析（Excel） | openpyxl | 电力工程 Excel 数据文件（铁塔统计、杆塔明细表等） |
| 段落聚合 | 自研 | 基于坐标 + 语义的段落边界识别 |
| 表格截图（PDF） | pymupdf + Pillow | 渲染页面后裁剪表格区域 |
| 表格截图（Word） | python-docx → pymupdf（转 PDF 后截图） | 转 PDF 后统一截图流程 |
| 表格理解（Phase 1） | 规则提取 | 提取表头行，生成"列名:值"格式描述 |
| 表格理解（Phase 3） | Qwen-VL via DashScope | 视觉语言模型，理解合并单元格等复杂结构 |
| 对象存储 | MinIO（私有）/ S3（云端） | 存储原始文档原件 + 表格截图，URL 签名保障安全 |
| 向量数据库 | Milvus (pymilvus) | HNSW 索引，COSINE 度量，高性能 |
| 文档存储 | PostgreSQL (SQLAlchemy 2.0 async) | 存储原文、分块内容、元数据 |
| 缓存 | Redis | Phase 4 引入：查询缓存 + Embedding 缓存 |
| Embedding 模型 | DashScope text-embedding-v3 | 1024 维云端 API，零部署 |
| 任务队列 | Phase 1 同步；Phase 4 Celery + Redis | 异步摄入、失败重试、死信队列 |
| API 鉴权 | JWT / API Key | Phase 5 引入：统一鉴权中间件 |
| 重排序 | BGE-Reranker-v2-m3 | Phase 2 引入：BAAI 出品，中文优秀，完全本地化 |
| 大语言模型 | Qwen via DashScope | 中文能力强，云端 API 调用，零部署 |
| 数据库迁移 | Alembic | 版本化管理 Schema 变更 |
| 配置管理 | pydantic-settings | `.env` 文件 + 环境变量覆盖 |
| 监控（一期） | 结构化日志 + Grafana | 轻量，快速上线 |
| 监控（二期） | Phoenix / LangSmith | LLM 专项可观测，检索质量评估 |

### 5.2 各技术关键决策

**pymupdf (PDF 解析)**
- 替代原 Unstructured 方案，体积小、速度快、表格提取精确
- 提供每个 Element 的 bbox 坐标，支撑后续表格截图裁剪
- 保留坐标、字体、缩进等样式信息，供段落边界识别使用

**python-docx (Word 解析)**
- 直接访问 .docx 表格 XML 结构，可获取合并单元格信息
- 表格在文档中的顺序位置可精确定位
- .doc 旧格式需要 LibreOffice 转换，推迟到后续 Phase

**openpyxl (Excel 解析)**
- 电力工程领域大量 Excel 数据（铁塔统计、杆塔明细表）
- Excel 无"页面"概念，`page` 字段使用 sheet index 代替
- 支持 .xlsx，.xls 旧格式推迟

**段落边界识别（自研）**
- 依据 Element 的坐标、缩进、样式信息判断是否同属一个段落
- 需处理跨页段落：页尾文字与下一页表格可能是同一逻辑段落

**表格截图方案**
- PDF：`pymupdf` 直接渲染页面为图片，按 bbox 坐标裁剪表格区域
- Word：`python-docx` 提取表格 → 转 PDF → 同 PDF 截图流程
- 截图命名规范：`{doc_id}_p{page}_t{table_index}.png`，便于溯源

**表格语义描述（Phase 1）**
- Phase 1 所有表格统一走规则描述路径（`_describe_with_rules`）
- 规则提取：提取表头行，遍历每行生成"列名:值"形式描述
- Qwen-VL 视觉模型推迟到 Phase 3，用于复杂合并单元格表格

**DashScope API (Embedding + LLM)**
- Embedding 使用 text-embedding-v3（1024 维云端 API，支持自定义维度）
- LLM 使用 Qwen（通过 DashScope OpenAI 兼容接口）
- 零部署成本，Phase 1 快速验证；vLLM 本地部署推迟到有明确性能需求时

**文档图片提取**
- PDF：使用 pymupdf 的 `page.get_images()` 获取图片引用列表，`doc.extract_image(xref)` 提取图片原始数据，`page.get_image_info(xrefs=True)` 获取图片 bbox 坐标
- Word：通过 python-docx 检测段落中的 `<w:drawing>` 元素，提取内嵌图片数据
- 图片仅作为上下文补充，不参与向量化检索：在 `full_text` 中插入 `[图片: 文件名]` 占位文本，图片本身上传至 MinIO `/doc-images/` 目录
- 图片的 `image_url` 与表格截图一样，返回时替换为签名 URL

**Milvus**
- 使用 pymilvus 同步客户端，Phase 1 无需 async wrapper
- `elements` 字段 JSON 序列化后存为 VARCHAR，召回时反序列化还原
- `image_url` 在后处理阶段统一替换为签名 URL，原始路径不对外暴露
- 通过 StoragePort 接口抽象，方便切换 Qdrant 等替代方案

**PostgreSQL (SQLAlchemy 2.0 async ORM)**
- 与 FastAPI async 框架配合，避免阻塞事件循环
- Alembic 管理数据库迁移，版本化 Schema 变更

**BGE-Reranker（Phase 2）**
- Cross-Encoder 延迟随候选数量线性增长，粗召回控制在 20-50 条
- Phase 2 引入，Phase 1 仅使用向量检索

**依赖注入**
- 使用 FastAPI `app.state` 手动组装，在 `main.py` 中实例化所有组件
- 组件数量有限（十几个类），手动实例化最直观

**测试策略**
- 核心逻辑（Parser、ChunkBuilder、PromptBuilder）使用单元测试 + mock 存储
- 关键路径使用 test-files 中的真实电力工程文档进行集成测试

---

## 六、横切关注点

| 关注点 | 实现方式 |
|--------|---------|
| 可观测性 | 每个节点记录耗时、召回数量、模型调用次数 |
| 缓存 | 查询结果缓存 + Embedding 缓存，降低成本和延迟 |
| 权限控制 | API 层 JWT / API Key 鉴权；文档级 ACL 表记录用户与文档的访问关系，检索时自动注入 `doc_id in [...]` 过滤条件；image_url 使用签名 URL（1小时有效），签名逻辑统一由 `SignedUrlService` 模块管理 |
| 配置中心 | 分块大小、Top-K、模型选择、表格处理策略等参数运行时可调 |
| 错误降级 | 检索失败 → 返回兜底回答；LLM 超时 → 重试或切换备用模型 |

---

## 七、数据流全链路

### 7.1 摄入链路

```
PDF / Word / Excel 文档上传
       │
       ├──▶ [原始文件存储] ──▶ MinIO/S3 /raw-docs/   ← 原件永久保存
       │     记录 raw_file_url 到 PostgreSQL documents 表
       │
       ▼
[pymupdf / python-docx / openpyxl 解析]  →  扁平 Element 列表（文字/表格/图片）
       │
       ▼
[段落边界识别]  →  Elements 聚合为段落组
       │
       ├── 纯文字段落  ──▶ [分块] ──────────────────────────────▶ [Embedding] ──▶ [Milvus]
       │
       ├── 纯表格段落  ──▶ [截图 → OSS /table-images/]
       │                   [语义描述生成] ──────────────────────▶ [Embedding] ──▶ [Milvus]
       │
       ├── 纯图片段落  ──▶ [提取图片 → OSS /doc-images/]
       │                   [生成占位文本] ──────────────────────▶ [Embedding] ──▶ [Milvus]
       │
       └── 混合段落    ──▶ [逐元素处理：文字保留 / 表格截图+描述 / 图片提取+占位]
                           [组装 MixedChunk，拼接 full_text] ──▶ [Embedding] ──▶ [Milvus]
                                                                  分块记录同步写入 PostgreSQL chunks 表
```

### 7.2 查询链路

```
用户提问 (+ 可选过滤: dataset_ids / doc_ids / doc_names)
    │
    ▼
[查询理解]  →  改写 / 意图识别
    │
    ▼
[过滤解析]  →  API 层将 dataset_ids / doc_names 通过 PG 解析为 doc_ids 列表
    │
    ▼
[多路检索]  →  Milvus(向量) + BM25，注入 doc_id in [...] 过滤
    ▼
[RRF 融合]  →  合并排序
    │
    ▼
[BGE-Reranker]  →  精排 Top-5
    │
    ▼
[上下文压缩]  →  基于 full_text 裁剪
    │
    ▼
[Prompt 构建]  →  只用 content 字段，image_url 不进 Prompt
    │
    ▼
[Qwen via DashScope]  →  生成答案
    │
    ▼
[后处理]  →  来源标注 + image_url 签名替换
    │
    ▼
返回：{ answer, sources: [ { metadata, elements } ] }
```

---

## 八、监控策略

### 8.1 第一阶段（系统上线初期）

用结构化日志记录关键指标，存入数据库，Grafana 可视化：

- 每次查询的检索耗时、召回文档数量
- LLM 调用耗时、Token 消耗量
- 缓存命中率、接口错误率
- 表格截图成功率、Qwen-VL 调用耗时

### 8.2 第二阶段（优化阶段）

接入 LLM 专项可观测平台（Phoenix 或 LangSmith）：

- 完整 Prompt 和 Context 内容追踪
- 答案质量自动评分（相关性、忠实度）
- 幻觉率监控
- 检索召回质量（NDCG、MRR 指标）

---

## 九、扩展原则

- **新增文档格式** → 实现 `BaseParser` 接口，注册到 Parser 工厂，无需改动主流程
- **替换向量库** → 修改 `VectorStorePort` 实现类，业务代码不动
- **升级 LLM** → 修改 `LLMClient` 配置项，切换模型端点；`FallbackLLMClient` 自动降级到备用模型
- **优化检索策略** → 替换 Pipeline 中的单个节点，其余节点不受影响；RRF 权重通过配置中心运行时调整
- **增加新接口** → 在用户交互层新增 Handler，通过鉴权中间件统一保护
- **切换对象存储** → 修改 `ObjectStoragePort` 实现，所有签名 URL 生成统一由 `SignedUrlService` 封装
- **扩展元数据字段** → 在 `ChunkMetadata` 中新增字段，同步更新 Milvus Schema 和响应结构
- **扩展权限模型** → 在 `document_acl` 表中新增权限维度（如部门、标签），`ACLFilter` 自动适配

---

## 十、里程碑规划（参考）

| 阶段 | 目标 | 关键交付物 |
|------|------|-----------|
| Phase 1 | 主链路跑通 | Unstructured 解析 + Milvus 存储 + Qwen 问答（PDF/Word） |
| Phase 2 | 检索质量提升 | 混合检索 + BGE-Reranker + 查询改写 + 调试接口 |
| Phase 3 | 混合块能力 | 段落聚合 + 表格截图 + MixedChunk 召回 |
| Phase 4 | 格式扩展 | HTML / Markdown Parser + 增量更新 |
| Phase 5 | 工程化完善 | JWT 鉴权 + ACL 权限过滤 + 签名 URL 服务 + 参数配置 API + 管理后台 |
| Phase 6 | 高级能力 | 多跳推理 + 备用 LLM 降级 + 缓存优化 |
| Phase 7 | 可观测落地 | 监控指标、质量评估体系、vLLM 部署规范 |

---

*文档持续更新，以实际开发进展为准。*
