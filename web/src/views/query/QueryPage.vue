<template>
  <div class="query-layout">
    <aside class="session-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">对话历史</span>
        <a-button type="text" size="small" @click="handleNewSession" aria-label="新建对话" class="new-session-btn">
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
          <div class="session-dot"></div>
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
            <button type="button" class="session-action-btn" @click.stop="startRename(s)" aria-label="重命名">
              <edit-outlined />
            </button>
            <button type="button" class="session-action-btn session-action-danger" @click.stop="store.deleteSession(s.id)" aria-label="删除对话">
              <delete-outlined />
            </button>
          </div>
        </div>
        <div v-if="store.sessions.length === 0" class="sidebar-empty">
          <message-outlined class="sidebar-empty-icon" />
          <span>暂无对话</span>
        </div>
      </div>
    </aside>

    <div class="chat-area">
      <div class="chat-messages" ref="messagesRef">
        <div v-if="!activeSession || activeSession.messages.length === 0" class="chat-empty">
          <div class="chat-empty-icon-wrap">
            <robot-outlined class="chat-empty-icon" />
          </div>
          <h3 class="chat-empty-title">智能问答</h3>
          <p class="chat-empty-desc">输入问题开始对话，系统将基于知识库内容回答</p>
        </div>
        <template v-for="(msg, idx) in activeSession?.messages" :key="idx">
          <div :class="['message-row', msg.role]">
            <div class="message-avatar">
              <user-outlined v-if="msg.role === 'user'" aria-hidden="true" />
              <svg v-else viewBox="0 0 24 24" fill="none" class="avatar-bot-icon">
                <rect width="24" height="24" rx="6" fill="#312e81"/>
                <path d="M9 6h4.5c2 0 3.5 1 3.5 2.8 0 1.3-.8 2.2-1.8 2.6l2.2 6.6h-2.8l-2-5.2H11.4V18H9V6zm2.4 1.8v3.2h2c1 0 1.7-.6 1.7-1.6s-.7-1.6-1.7-1.6h-2z" fill="white" fill-opacity="0.9"/>
              </svg>
            </div>
            <div class="message-content">
              <div v-if="msg.content" class="message-text" v-html="renderMarkdown(msg.content)"></div>
              <div v-else-if="msg.role === 'assistant'" class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
              <div v-if="msg.total_ms" class="message-meta tabular-nums">耗时 {{ msg.total_ms.toFixed(0) }}ms</div>
              <div v-if="msg.sources && msg.sources.length > 0" class="sources-section">
                <a-collapse size="small" :bordered="false" class="sources-collapse">
                  <a-collapse-panel header="引用来源">
                    <div v-for="(src, si) in msg.sources" :key="si" class="source-card">
                      <div class="source-header">
                        <a-tag>{{ src.metadata.filename }}</a-tag>
                        <span class="source-meta">第 {{ src.metadata.page }} 页</span>
                        <span class="source-meta tabular-nums">相似度 {{ src.metadata.score.toFixed(4) }}</span>
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
          placeholder="输入问题，按 Enter 发送…"
          @pressEnter="handleSend"
          :disabled="loading"
          name="question"
          autocomplete="off"
          class="chat-textarea"
        />
        <a-button type="primary" :loading="loading" @click="handleSend" :disabled="!question.trim()" class="send-btn">
          <send-outlined v-if="!loading" />
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  UserOutlined,
  RobotOutlined,
  MessageOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import { useQuerySessionStore } from '@/stores/querySession'
import { queryRagStream } from '@/api/query'
import type { SourceData } from '@/stores/querySession'
import { renderMarkdown } from '@/utils/markdown'
import { resolveImageUrl } from '@/utils/imageAuth'
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

async function handleSend(e?: { shiftKey?: boolean; preventDefault?: () => void }) {
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
    // 先插入一条空的 assistant 消息，流式过程中逐 token 更新
    store.addMessage(session.id, {
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
    })

    await queryRagStream(
      {
        question: q,
        dataset_ids: selectedDatasetIds.value.length > 0 ? selectedDatasetIds.value : undefined,
        doc_ids: selectedDocIds.value.length > 0 ? selectedDocIds.value : undefined,
      },
      {
        onToken: (content) => {
          const sess = store.getActiveSession()
          if (sess) {
            const last = sess.messages[sess.messages.length - 1]
            if (last && last.role === 'assistant') last.content += content
          }
          scrollToBottom()
        },
        onResult: async (data) => {
          const sources: SourceData[] = (data.sources || []).map((s: any) => ({
            metadata: {
              chunk_id: s.metadata.chunk_id,
              filename: s.metadata.filename,
              page: s.metadata.page,
              chunk_index: s.metadata.chunk_index,
              score: s.metadata.score,
            },
            elements: s.elements.map((el: any) => ({
              type: el.type,
              content: el.content,
              image_url: el.image_url,
            })),
          }))
          for (const src of sources) {
            for (const el of src.elements) {
              if (el.image_url) el.image_url = await resolveImageUrl(el.image_url)
            }
          }
          store.updateLastAssistant(session.id, { total_ms: data.total_ms, sources })
        },
        onError: (err) => {
          store.updateLastAssistant(session.id, { content: `请求失败: ${err.message}` })
        },
      },
    )
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

/* ── Sidebar ── */
.session-sidebar {
  width: 280px;
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  background: var(--color-bg-dark);
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-4);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.sidebar-title {
  font-weight: 600;
  font-size: var(--font-size-sm);
  color: #a5b4fc;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.new-session-btn {
  color: #a5b4fc !important;
  border-radius: var(--radius-md);
}

.new-session-btn:hover {
  color: #ffffff !important;
  background: rgba(255, 255, 255, 0.1) !important;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.session-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  margin-bottom: 2px;
  transition: all var(--transition-fast);
  color: #c7d2fe;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.session-item.active {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
}

.session-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.4;
  flex-shrink: 0;
}

.session-item.active .session-dot {
  opacity: 1;
  background: #f59e0b;
  box-shadow: 0 0 6px rgba(245, 158, 11, 0.5);
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
  gap: 2px;
}

.session-item:hover .session-actions {
  display: flex;
}

.session-action-btn {
  background: none;
  border: none;
  color: #a5b4fc;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  display: flex;
  align-items: center;
  transition: all var(--transition-fast);
}

.session-action-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.1);
}

.session-action-danger:hover {
  color: #f87171 !important;
}

.sidebar-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  color: #6366f1;
  font-size: var(--font-size-sm);
}

.sidebar-empty-icon {
  font-size: 24px;
  opacity: 0.5;
}

/* ── Chat Area ── */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-base);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6) var(--space-8);
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  opacity: 0;
  animation: fade-in 0.5s ease forwards;
}

@keyframes fade-in {
  to { opacity: 1; }
}

.chat-empty-icon-wrap {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-xl);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-5);
}

.chat-empty-icon {
  font-size: 32px;
  color: var(--color-primary);
}

.chat-empty-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.chat-empty-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  max-width: 320px;
}

/* ── Messages ── */
.message-row {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  animation: msg-in 0.3s ease;
}

@keyframes msg-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 15px;
  background: var(--color-bg-sunken);
}

.message-row.user .message-avatar {
  background: linear-gradient(135deg, var(--color-primary), color-mix(in srgb, var(--color-primary) 80%, #6366f1));
  color: #fff;
  border-radius: var(--radius-md);
  box-shadow: 0 1px 6px -1px color-mix(in srgb, var(--color-primary) 40%, transparent);
}

.avatar-bot-icon {
  width: 30px;
  height: 30px;
}

.message-content {
  max-width: 60%;
  min-width: 40px;
}

.message-row.user .message-content {
  text-align: right;
}

.message-text {
  display: inline-block;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  text-align: left;
  line-height: 1.7;
  word-break: break-word;
  font-size: var(--font-size-base);
  box-shadow: var(--shadow-xs);
}

.message-row.user .message-text {
  background: linear-gradient(135deg, var(--color-primary) 0%, color-mix(in srgb, var(--color-primary) 85%, #6366f1) 100%);
  color: #ffffff;
  padding: 8px 14px;
  line-height: 1.5;
  border-radius: 14px 14px 4px 14px;
  box-shadow: 0 1px 6px -1px color-mix(in srgb, var(--color-primary) 30%, transparent);
  font-weight: 500;
  font-size: var(--font-size-sm);
  letter-spacing: 0.005em;
}

.message-row.assistant .message-text {
  border-bottom-left-radius: var(--radius-sm);
}

.message-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
}

/* ── Typing Indicator ── */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border-bottom-left-radius: var(--radius-sm);
  box-shadow: var(--shadow-xs);
}

.typing-indicator span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-tertiary);
  animation: typing-bounce 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── Sources ── */
.sources-section {
  margin-top: var(--space-2);
}

.sources-collapse {
  background: var(--color-bg-sunken) !important;
  border-radius: var(--radius-md) !important;
}

.source-card {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border);
}

.source-card:last-child {
  border-bottom: none;
}

.source-header {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  margin-bottom: var(--space-2);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.source-meta {
  color: var(--color-text-tertiary);
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

/* ── Filter & Input ── */
.filter-bar {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-8);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
}

.chat-input {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-8);
  background: var(--color-bg-elevated);
  border-top: 1px solid var(--color-border);
}

.chat-textarea {
  flex: 1;
  border-radius: var(--radius-lg) !important;
}

.chat-textarea :deep(.ant-input) {
  border-radius: var(--radius-lg);
}

.send-btn {
  border-radius: var(--radius-lg);
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.chat-input :deep(.ant-input-textarea) {
  flex: 1;
}
</style>
