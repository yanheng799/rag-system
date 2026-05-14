# RAG 系统前端

RAG（检索增强生成）系统的 Web 前端，基于 Vue 3 + TypeScript + Ant Design Vue 构建。

## 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | Vue 3.5（Composition API + `<script setup>`） |
| 类型 | TypeScript 6 |
| 构建 | Vite 8 |
| UI | Ant Design Vue 4 |
| 路由 | Vue Router 4 |
| 状态管理 | Pinia 3 |
| HTTP | Axios |
| Markdown | marked + DOMPurify |

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器（http://localhost:5173）
npm run dev

# 生产构建
npm run build

# 预览构建产物
npm run preview
```

开发时 `/api` 请求自动代理到 `http://localhost:8000`（后端 API）。

## 页面结构

```
/                       → 重定向到 /datasets
/datasets               → 知识库列表（创建、编辑、删除）
/datasets/:id           → 知识库详情（上传文档、解析、状态轮询）
/query                  → 智能问答（多轮对话、引用来源）
/retrieve               → 分块检索（向量/BM25/混合，按知识库/文档过滤）
/documents/:docId/chunks → 分块列表（合并、拆分、关联、删除）
/chunks/:chunkId        → 分块详情（Markdown 渲染、图片展示、编辑）
```

## 目录结构

```
src/
├── main.ts              # 入口，注册 Pinia / Router / Ant Design
├── App.vue              # 根组件
├── router/index.ts      # 路由配置（懒加载）
├── stores/
│   └── querySession.ts  # 问答会话状态（localStorage 持久化）
├── api/
│   ├── request.ts       # Axios 实例（baseURL /api/v1）
│   ├── datasets.ts      # 知识库 CRUD
│   ├── documents.ts     # 文档上传、列表、摄入、状态、删除
│   ├── query.ts         # RAG 问答
│   ├── retrieve.ts      # 分块检索
│   └── chunks.ts        # 分块管理（查看、编辑、合并、拆分、关联）
├── utils/
│   └── markdown.ts      # Markdown 渲染（GFM 表格 + DOMPurify 消毒）
├── layouts/
│   └── MainLayout.vue   # 全局布局（顶部导航 + router-view）
└── views/
    ├── datasets/         # 知识库列表、详情
    ├── query/            # 问答页面
    ├── retrieve/         # 检索页面
    └── chunks/           # 分块列表、详情
```
