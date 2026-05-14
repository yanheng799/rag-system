<template>
  <div class="query-layout">
    <div class="session-sidebar">
      <div class="sidebar-header">
        <span>对话历史</span>
        <a-button type="text" size="small" @click="handleNewSession">
          <plus-outlined />
        </a-button>
      </div>
      <div class="session-list">
        <div
          v-for="s in store.sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === store.activeSessionId }"
          @click="store.switchSession(s.id)"
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
            <a-button type="text" size="small" @click.stop="startRename(s)">
              <edit-outlined />
            </a-button>
            <a-button type="text" size="small" danger @click.stop="store.deleteSession(s.id)">
              <delete-outlined />
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
              <user-outlined v-if="msg.role === 'user'" />
              <robot-outlined v-else />
            </div>
            <div class="message-content">
              <div class="message-text" v-html="renderMarkdown(msg.content)"></div>
              <div v-if="msg.total_ms" class="message-meta">耗时 {{ msg.total_ms.toFixed(0) }}ms</div>
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
                            <a-image v-if="el.image_url" :src="el.image_url" :width="200" />
                            <div class="table-desc markdown-body" v-html="renderMarkdown(el.content)"></div>
                          </template>
                          <template v-else-if="el.type === 'image'">
                            <a-image v-if="el.image_url" :src="el.image_url" :width="200" />
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
          <div class="message-avatar"><robot-outlined /></div>
          <div class="message-content">
            <a-spin size="small" /> 思考中…
          </div>
        </div>
      </div>

      <div class="chat-input">
        <a-textarea
          v-model:value="question"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          placeholder="输入问题，按 Enter 发送，Shift+Enter 换行"
          @pressEnter="handleSend"
          :disabled="loading"
        />
        <a-button type="primary" :loading="loading" @click="handleSend" :disabled="!question.trim()">
          发送
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
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

const store = useQuerySessionStore()
const question = ref('')
const loading = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const editingId = ref<string | null>(null)
const editTitle = ref('')
const renameInput = ref<InstanceType<typeof HTMLInputElement> | null>(null)

const activeSession = computed(() => store.getActiveSession())

function handleNewSession() {
  store.createSession()
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

async function handleSend(e?: { shiftKey?: boolean }) {
  if (e?.shiftKey) return
  e?.preventDefault?.()

  const q = question.value.trim()
  if (!q || loading.value) return

  if (!activeSession.value) {
    store.createSession()
  }
  const session = store.getActiveSession()!
  const now = new Date().toISOString()

  store.addMessage(session.id, { role: 'user', content: q, timestamp: now })
  question.value = ''
  loading.value = true

  try {
    const res = await queryRag({ question: q })
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
</script>

<style scoped>
.query-layout {
  display: flex;
  height: calc(100vh - 64px);
}

.session-sidebar {
  width: 260px;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  font-weight: 600;
  border-bottom: 1px solid #f0f0f0;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.session-item:hover {
  background: #e6f4ff;
}

.session-item.active {
  background: #e6f4ff;
  font-weight: 500;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
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
  padding: 24px;
}

.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
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
  font-size: 16px;
  background: #f0f0f0;
}

.message-row.user .message-avatar {
  background: #1677ff;
  color: #fff;
}

.message-row.assistant .message-avatar {
  background: #f6ffed;
  color: #52c41a;
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
  padding: 10px 16px;
  border-radius: 12px;
  background: #f5f5f5;
  text-align: left;
  line-height: 1.6;
  word-break: break-word;
}

.message-row.user .message-text {
  background: #1677ff;
  color: #fff;
}

.message-meta {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.sources-section {
  margin-top: 8px;
}

.source-card {
  padding: 8px 0;
  border-bottom: 1px solid #f5f5f5;
}

.source-card:last-child {
  border-bottom: none;
}

.source-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
  font-size: 12px;
  color: #666;
}

.source-element {
  font-size: 13px;
  color: #333;
  margin-bottom: 4px;
}

.table-desc {
  font-size: 12px;
  color: #888;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #d9d9d9;
  padding: 6px 12px;
  text-align: left;
  font-size: 13px;
}

.markdown-body :deep(th) {
  background: #fafafa;
  font-weight: 600;
}

.markdown-body :deep(tr:nth-child(even)) {
  background: #fafafa;
}

.markdown-body :deep(img) {
  max-width: 100%;
}

.markdown-body :deep(pre) {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
}

.markdown-body :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #f0f0f0;
  background: #fff;
}

.chat-input .ant-input-textarea {
  flex: 1;
}
</style>
