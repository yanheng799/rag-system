<template>
  <div class="page-container">
    <div class="detail-header">
      <a-button type="text" @click="router.back()" class="back-btn">
        <arrow-left-outlined /> 返回
      </a-button>
      <div class="detail-info">
        <h2 class="detail-title">{{ chunk?.chunk_id || '加载中…' }}</h2>
      </div>
      <div class="header-actions">
        <a-button v-if="!editing" type="primary" @click="startEdit">编辑</a-button>
        <template v-else>
          <a-button @click="cancelEdit">取消</a-button>
          <a-button type="primary" :loading="saving" @click="handleSave">保存</a-button>
        </template>
      </div>
    </div>

    <a-spin :spinning="loading">
      <template v-if="chunk">
        <div class="meta-grid">
          <div class="meta-card">
            <span class="meta-label">文档 ID</span>
            <span class="meta-value">{{ chunk.doc_id }}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">类型</span>
            <span class="meta-value">{{ chunk.chunk_type }}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">页码</span>
            <span class="meta-value">{{ chunk.page }}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">序号</span>
            <span class="meta-value">{{ chunk.chunk_index }}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">字数</span>
            <span class="meta-value tabular-nums">{{ chunk.char_count }}</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">关联组</span>
            <span class="meta-value">{{ chunk.group_id || '无' }}</span>
          </div>
        </div>

        <div class="section-header">
          <h3>全文内容</h3>
        </div>
        <div v-if="!editing" class="full-text-display markdown-body" v-html="renderMarkdown(chunk.full_text)"></div>
        <a-textarea
          v-else
          v-model:value="editText"
          :rows="10"
          placeholder="编辑分块内容…"
          name="chunk_text"
        />

        <template v-if="chunk.elements && chunk.elements.length > 0">
          <a-divider />
          <div class="section-header">
            <h3>元素列表</h3>
            <span class="section-count">{{ chunk.elements.length }} 个元素</span>
          </div>
          <div class="elements-list">
            <a-card v-for="(el, i) in chunk.elements" :key="i" size="small" class="element-card">
              <template #title>
                <span class="element-index">#{{ i + 1 }}</span>
                <a-tag :color="el.type === 'table' ? 'orange' : el.type === 'image' ? 'purple' : 'blue'">{{ el.type }}</a-tag>
              </template>
              <template v-if="el.type === 'table'">
                <a-image v-if="el.image_url" :src="el.image_url" :width="400" alt="表格截图" />
                <div class="table-content markdown-body" v-html="renderMarkdown(el.content)"></div>
              </template>
              <template v-else-if="el.type === 'image'">
                <a-image v-if="el.image_url" :src="el.image_url" :width="400" alt="图片" />
                <div v-else class="element-content">{{ el.content }}</div>
              </template>
              <template v-else>
                <div class="element-content markdown-body" v-html="renderMarkdown(el.content)"></div>
              </template>
            </a-card>
          </div>
        </template>

        <template v-if="chunk.image_urls && chunk.image_urls.length > 0">
          <a-divider />
          <div class="section-header">
            <h3>图片</h3>
            <span class="section-count">{{ chunk.image_urls.length }} 张</span>
          </div>
          <div class="image-list">
            <a-image
              v-for="(url, i) in chunk.image_urls"
              :key="i"
              :src="url"
              :width="300"
              :alt="'图片 ' + (i + 1)"
            />
          </div>
        </template>
      </template>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { getChunkDetail, editChunk, deleteChunk, type ChunkDetail } from '@/api/chunks'
import { renderMarkdown } from '@/utils/markdown'
import { resolveImageUrl } from '@/utils/imageAuth'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const chunkId = route.params.chunkId as string

const chunk = ref<ChunkDetail | null>(null)
const loading = ref(false)
const editing = ref(false)
const saving = ref(false)
const editText = ref('')

function resolveElementImages() {
  if (!chunk.value) return
  chunk.value.elements?.forEach((el) => {
    if (el.image_url) resolveImageUrl(el.image_url).then((url) => { el.image_url = url })
  })
  chunk.value.image_urls?.forEach((url, i) => {
    resolveImageUrl(url).then((resolved) => { chunk.value!.image_urls![i] = resolved })
  })
}

async function fetchChunk() {
  loading.value = true
  try {
    chunk.value = await getChunkDetail(chunkId)
    resolveElementImages()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function startEdit() {
  editText.value = chunk.value?.full_text || ''
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function handleSave() {
  saving.value = true
  try {
    const res = await editChunk(chunkId, editText.value)
    if (chunk.value) {
      chunk.value.full_text = res.full_text
      chunk.value.char_count = res.char_count
    }
    editing.value = false
    message.success('保存成功')
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  try {
    await deleteChunk(chunkId)
    message.success('删除成功')
    router.back()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

onMounted(fetchChunk)
</script>

<style scoped>
.page-container {
  padding: var(--space-6) var(--space-8);
  max-width: 1200px;
  margin: 0 auto;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.back-btn {
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
}

.back-btn:hover {
  color: var(--color-primary);
}

.detail-info {
  flex: 1;
}

.detail-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: var(--color-text-primary);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-actions {
  display: flex;
  gap: var(--space-2);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-3);
  margin-bottom: var(--space-6);
}

.meta-card {
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.meta-label {
  display: block;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-1);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.meta-value {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: 500;
  word-break: break-all;
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.section-header h3 {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.full-text-display {
  background: var(--color-bg-elevated);
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  line-height: 1.8;
  font-size: var(--font-size-base);
  max-height: 600px;
  overflow-y: auto;
}

.elements-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.element-index {
  font-size: var(--font-size-xs);
  font-weight: 700;
  color: var(--color-primary);
  margin-right: var(--space-2);
}

.element-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md) !important;
}

.element-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}

.table-content {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  white-space: pre-wrap;
}

.image-list {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
}
</style>
