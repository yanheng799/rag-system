<template>
  <div class="query-layout">
    <div class="session-sidebar">
      <div class="sidebar-header">
        <span>对话历史</span>
        <a-button type="text" size="small" @click="handleNewSession" aria-label="新建对话">
          <plus-outlined aria-hidden="true" />
        </a-button>
      </div>
      <div class="session-list">
        <div
          v-for="s in store.sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === store.activeSessionId }"
          role="button"
          tabindex="0"
          @click="handleSwitchSession(s.id)"
          @keydown.enter="handleSwitchSession(s.id)"
        >
          <div class="session-title" v-if="editingId !== s.id">
            {{ s.title }}
          </div>
          <a-input
            v-else
            v-model:value="editTitle"
            size="small"
            @pressEnter="confirmRename(s.id)"
            @blur="confirmRename(s.id)"
            ref="renameInput"
          />
          <div class="session-actions">
            <a-button type="text" size="small" @click.stop="startRename(s)" aria-label="重命名">
              <edit-outlined aria-hidden="true" />
            </a-button>
            <a-button type="text" size="small" danger @click.stop="store.deleteSession(s.id)" aria-label="删除对话">
              <delete-outlined aria-hidden="true" />
            </a-button>
          </div>
        </div>
        <a-empty v-if="store.sessions.length === 0" description="暂无对话" :image-style="{ height: '40px' }" />
      </div>
    </div>

    <div class="chat-area">
      <div class="chat-messages" ref="messagesRef">
        <a-empty v-if="!activeSession || activeSession.messages.length === 0" description="输入问题开始对话" />
        <template v-for="(msg, idx) in activeSession?.messages" :key="idx">
          <div :class="['message-row', msg.role]">
            <div class="message-avatar">
              <user-outlined v-if="msg.role === 'user'" aria-hidden="true" />
              <robot-outlined v-else aria-hidden="true" />
            </div>
            <div class="message-content">
              <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
              <div v-if="msg.total_ms" class="message-meta tabular-nums">耗时 {{ msg.total_ms.toFixed(0) }}ms</div>
              <div v-if="msg.sources && msg.sources.length > 0" class="sources-section">
                <a-collapse size="small" :bordered="false">
                  <a-collapse-panel header="引用来源">
                    <div v-for="(src, si) in msg.sources" :key="si" class="source-card">
                      <div class="source-header">
                        <a-tag>{{ src.metadata.filename }}</a-tag>
                        <span>第 {{ src.metadata.page }} 页</span>
                        <span>相似度 {{ src.metadata.score.toFixed(4) }}</span>
                      </div>
                      <div class="source-elements">
                        <div v-for="(el, ei) in src.elements" :key="ei" class="source-element">
                          <template v-if="el.type === 'table'">
                            <a-image v-if="el.image_url" :src="el.image_url" :width="200" alt="表格截图" />
                            <div class="table-desc markdown-body" v-html="renderMarkdown(el.content)"></div>
                          </template>
                          <template v-else-if="el.type === 'image'">
                            <a-image v-if="el.image_url" :src="el.image_url" :width="200" alt="图片" />
                            <div v-else>{{ el.content }}</div>
                          </template>
                          <template v-else>
                            <div class="markdown-body" v-html="renderMarkdown(el.content)"></div>
                          </template>
                        </div>
                      </div>
                    </div>
                  </a-collapse-panel>
                </a-collapse>
              </div>
            </div>
          </div>
        </template>
        <div v-if="loading" class="message-row assistant">
          <div class="message-avatar"><robot-outlined aria-hidden="true" /></div>
          <div class="message-content">
            <a-spin size="small" /> 思考中…
          </div>
        </div>
      </div>

      <div class="filter-bar">
        <a-select
          v-model:value="selectedDatasetIds"
          mode="multiple"
          placeholder="选择知识库（可选）"
          style="min-width: 200px"
          :options="datasetOptions"
          allow-clear
          :max-tag-count="2"
        />
        <a-select
          v-model:value="selectedDocIds"
          mode="multiple"
          placeholder="选择文档（可选）"
          style="min-width: 200px"
          :options="docOptions"
          allow-clear
          :max-tag-count="2"
          :disabled="docLoading"
        />
      </div>

      <div class="chat-input">
        <a-textarea
          v-model:value="question"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          placeholder="输入问题，按 Enter 发送，Shift+Enter 换行…"
          @pressEnter="handleSend"
          :disabled="loading"
          name="question"
          autocomplete="off"
        />
        <a-button type="primary" :loading="loading" @click="handleSend" :disabled="!question.trim()">
          发送
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UserOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import { useQuerySessionStore } from '@/stores/querySession'
import { queryRag } from '@/api/query'
import type { SourceData } from '@/stores/querySession'
import { renderMarkdown } from '@/utils/markdown'
import { listDatasets, type DatasetResponse } from '@/api/datasets'
import { listDocuments, type DocumentListItem } from '@/api/documents'

const store = useQuerySessionStore()
const route = useRoute()

const question = ref('')
const loading = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const editingId = ref<string | null>(null)
const editTitle = ref('')
const renameInput = ref<any>(null)

const datasets = ref<DatasetResponse[]>([])
const selectedDatasetIds = ref<string[]>([])
const docs = ref<DocumentListItem[]>([])
const selectedDocIds = ref<string[]>([])
const docLoading = ref(false)

const datasetOptions = computed(() =>
  datasets.value.map((ds) => ({ label: ds.name, value: ds.dataset_id }))
)

const docOptions = computed(() =>
  docs.value.map((d) => ({ label: d.filename, value: d.doc_id }))
)

const activeSession = computed(() => store.getActiveSession())

function handleNewSession() {
  const session = store.createSession()
  session.dataset_ids = [...selectedDatasetIds.value]
  session.doc_ids = [...selectedDocIds.value]
}

function handleSwitchSession(id: string) {
  store.switchSession(id)
  const session = store.getActiveSession()
  if (session) {
    selectedDatasetIds.value = [...session.dataset_ids]
    selectedDocIds.value = [...session.doc_ids]
    if (session.dataset_ids.length > 0) fetchDocs()
  }
}

function startRename(s: { id: string; title: string }) {
  editingId.value = s.id
  editTitle.value = s.title
  nextTick(() => {
    renameInput.value?.focus()
  })
}

function confirmRename(id: string) {
  if (editTitle.value.trim()) {
    store.renameSession(id, editTitle.value.trim())
  }
  editingId.value = null
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

watch(() => activeSession.value?.messages?.length, scrollToBottom)

async function fetchDatasets() {
  try {
    const res = await listDatasets({ size: 100 })
    datasets.value = res.items
  } catch { /* ignore */ }
}

async function fetchDocs() {
  if (selectedDatasetIds.value.length === 0) {
    docs.value = []
    return
  }
  docLoading.value = true
  try {
    const allDocs: DocumentListItem[] = []
    for (const dsId of selectedDatasetIds.value) {
      const res = await listDocuments({ dataset_id: dsId, size: 100 })
      allDocs.push(...res.items)
    }
    docs.value = allDocs
  } catch { /* ignore */ }
  finally {
    docLoading.value = false
  }
}

watch(selectedDatasetIds, () => {
  selectedDocIds.value = []
  syncToSession()
  fetchDocs()
})

watch(selectedDocIds, () => {
  syncToSession()
})

function syncToSession() {
  const session = store.getActiveSession()
  if (session) {
    session.dataset_ids = [...selectedDatasetIds.value]
    session.doc_ids = [...selectedDocIds.value]
  }
}

function parseUrlIds(param: string | string[] | undefined): string[] {
  if (!param) return []
  if (Array.isArray(param)) return param
  return [param]
}

async function handleSend(e?: { shiftKey?: boolean }) {
  if (e?.shiftKey) return
  e?.preventDefault?.()

  const q = question.value.trim()
  if (!q || loading.value) return

  if (!activeSession.value) {
    const session = store.createSession()
    session.dataset_ids = [...selectedDatasetIds.value]
    session.doc_ids = [...selectedDocIds.value]
  }
  const session = store.getActiveSession()!
  const now = new Date().toISOString()

  store.addMessage(session.id, { role: 'user', content: q, timestamp: now })
  question.value = ''
  loading.value = true

  try {
    const res = await queryRag({
      question: q,
      dataset_ids: selectedDatasetIds.value.length > 0 ? selectedDatasetIds.value : undefined,
      doc_ids: selectedDocIds.value.length > 0 ? selectedDocIds.value : undefined,
    })
    const sources: SourceData[] = res.sources.map((s) => ({
      metadata: {
        chunk_id: s.metadata.chunk_id,
        filename: s.metadata.filename,
        page: s.metadata.page,
        chunk_index: s.metadata.chunk_index,
        score: s.metadata.score,
      },
      elements: s.elements.map((el) => ({
        type: el.type,
        content: el.content,
        image_url: el.image_url,
      })),
    }))
    store.addMessage(session.id, {
      role: 'assistant',
      content: res.answer,
      total_ms: res.total_ms,
      sources,
      timestamp: new Date().toISOString(),
    })
  } catch (e: unknown) {
    store.addMessage(session.id, {
      role: 'assistant',
      content: `请求失败: ${(e as Error).message}`,
      timestamp: new Date().toISOString(),
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  await fetchDatasets()

  const urlDatasetIds = parseUrlIds(route.query.dataset_ids as string | string[] | undefined)
  const urlDocIds = parseUrlIds(route.query.doc_ids as string | string[] | undefined)

  if (urlDatasetIds.length > 0 || urlDocIds.length > 0) {
    selectedDatasetIds.value = urlDatasetIds
    if (urlDatasetIds.length > 0) await fetchDocs()
    selectedDocIds.value = urlDocIds
  }
})
</script>

<style scoped>
.query-layout {
  display: flex;
  height: calc(100vh - var(--layout-header-height));
}

.session-sidebar {
  width: 260px;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  background: var(--color-bg-subtle);
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4);
  font-weight: 600;
  border-bottom: 1px solid var(--color-border);
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  margin-bottom: var(--space-1);
  transition: background 0.2s;
}

.session-item:hover {
  background: var(--color-primary-bg);
}

.session-item.active {
  background: var(--color-primary-bg);
  font-weight: 500;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.session-actions {
  display: none;
  flex-shrink: 0;
}

.session-item:hover .session-actions {
  display: flex;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

.message-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: var(--font-size-lg);
  background: var(--color-border);
}

.message-row.user .message-avatar {
  background: var(--color-primary);
  color: #fff;
}

.message-row.assistant .message-avatar {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.message-content {
  max-width: 70%;
  min-width: 60px;
}

.message-row.user .message-content {
  text-align: right;
}

.message-text {
  display: inline-block;
  padding: 10px var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-muted);
  text-align: left;
  line-height: 1.6;
  word-break: break-word;
}

.message-row.user .message-text {
  background: var(--color-bg-chat-user);
  color: #fff;
}

.message-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
}

.sources-section {
  margin-top: var(--space-2);
}

.source-card {
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--color-bg-muted);
}

.source-card:last-child {
  border-bottom: none;
}

.source-header {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-1);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.source-element {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.table-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.filter-bar {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-6);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-subtle);
}

.chat-input {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-base);
}

.chat-input .ant-input-textarea {
  flex: 1;
}
</style>
