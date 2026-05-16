<template>
  <div class="page-container">
    <a-page-header
      :title="chunk?.chunk_id || '加载中…'"
      @back="router.back()"
    >
      <template #extra>
        <a-button v-if="!editing" type="primary" @click="startEdit">编辑</a-button>
        <template v-else>
          <a-button @click="cancelEdit">取消</a-button>
          <a-button type="primary" :loading="saving" @click="handleSave">保存</a-button>
        </template>
      </template>
    </a-page-header>

    <a-spin :spinning="loading">
      <template v-if="chunk">
        <a-descriptions bordered size="small" :column="2" style="margin-bottom: var(--space-6)">
          <a-descriptions-item label="文档 ID">{{ chunk.doc_id }}</a-descriptions-item>
          <a-descriptions-item label="类型">{{ chunk.chunk_type }}</a-descriptions-item>
          <a-descriptions-item label="页码">{{ chunk.page }}</a-descriptions-item>
          <a-descriptions-item label="序号">{{ chunk.chunk_index }}</a-descriptions-item>
          <a-descriptions-item label="字数">{{ chunk.char_count }}</a-descriptions-item>
          <a-descriptions-item label="关联组">{{ chunk.group_id || '无' }}</a-descriptions-item>
        </a-descriptions>

        <h3>全文内容</h3>
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
          <h3>元素列表</h3>
          <div class="elements-list">
            <a-card v-for="(el, i) in chunk.elements" :key="i" size="small" class="element-card">
              <template #title>
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
          <h3>图片</h3>
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

const router = useRouter()
const route = useRoute()
const chunkId = route.params.chunkId as string

const chunk = ref<ChunkDetail | null>(null)
const loading = ref(false)
const editing = ref(false)
const saving = ref(false)
const editText = ref('')

async function fetchChunk() {
  loading.value = true
  try {
    chunk.value = await getChunkDetail(chunkId)
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
  padding: 0 var(--space-6) var(--space-6);
}

.full-text-display {
  background: var(--color-bg-subtle);
  padding: var(--space-4);
  border-radius: var(--radius-md);
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
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
