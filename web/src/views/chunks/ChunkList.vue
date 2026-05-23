<template>
  <div class="page-container">
    <div class="detail-header">
      <a-button type="text" @click="router.back()" class="back-btn">
        <arrow-left-outlined /> 返回
      </a-button>
      <div class="detail-info">
        <h2 class="page-title" style="margin: 0">{{ breadcrumb }}</h2>
      </div>
      <div class="header-actions">
        <a-button
          type="primary"
          :disabled="selectedKeys.length < 2"
          @click="handleMerge"
        >
          合并选中 ({{ selectedKeys.length }})
        </a-button>
        <a-button
          :disabled="selectedKeys.length < 2"
          @click="handleLink"
        >
          关联选中
        </a-button>
        <a-button
          :disabled="selectedKeys.length < 1"
          danger
          @click="handleBatchDelete"
        >
          删除选中
        </a-button>
      </div>
    </div>

    <a-table
      :columns="columns"
      :data-source="chunks"
      :loading="loading"
      :pagination="{ current: page, pageSize: size, total, showSizeChanger: true }"
      :row-selection="{ selectedRowKeys: selectedKeys, onChange: (keys: string[]) => selectedKeys = keys }"
      row-key="chunk_id"
      size="small"
      class="chunk-table"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'chunk_id'">
          <router-link :to="chunkDetailLink(record.chunk_id)" class="chunk-id-link">
            {{ record.chunk_id.slice(0, 20) }}…
          </router-link>
        </template>
        <template v-if="column.key === 'full_text'">
          <span class="text-preview">{{ record.full_text?.slice(0, 100) }}{{ record.full_text?.length > 100 ? '…' : '' }}</span>
        </template>
        <template v-if="column.key === 'action'">
          <a-space>
            <router-link :to="chunkDetailLink(record.chunk_id)">查看</router-link>
            <a-button type="link" size="small" :disabled="record.element_count <= 1" @click="openSplitModal(record)">拆分</a-button>
            <a-popconfirm title="确定删除？" @confirm="handleDelete(record.chunk_id)">
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="splitModalVisible"
      title="拆分分块"
      @ok="handleSplit"
      :confirm-loading="splitting"
      :ok-button-props="{ disabled: splitAt <= 0 || !chunkDetail }"
      centered
      width="560px"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="chunkDetail">
          <p style="color: var(--color-text-secondary); margin-bottom: 12px">
            点击元素之间的分割线选拆分位置
          </p>

          <div class="element-list">
            <template v-for="(elem, idx) in chunkDetail.elements" :key="idx">
              <!-- 分割线 (第一个元素之前不显示) -->
              <div
                v-if="idx > 0"
                class="split-divider"
                :class="{ active: splitAt === idx }"
                @click="splitAt = idx"
              >
                <span class="divider-label">在元素 {{ idx }} 后拆分</span>
              </div>
              <!-- 元素行 -->
              <div class="element-row">
                <a-tag :color="elem.type === 'table' ? 'blue' : elem.image_url ? 'purple' : 'default'" size="small">
                  {{ elementTypeLabel(elem) }}
                </a-tag>
                <span class="element-content">{{ elementPreview(elem) }}</span>
              </div>
            </template>
          </div>

          <!-- 拆分结果预览 -->
          <div v-if="splitAt > 0" class="split-preview">
            {{ splitPreviewText() }}
          </div>
        </template>
      </a-spin>

      <div style="margin-top: 12px">
        <a-checkbox v-model:checked="linkAfterSplit">拆分后关联</a-checkbox>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  listChunks,
  deleteChunk,
  mergeChunks,
  splitChunk,
  linkChunks,
  getChunkDetail,
  type ChunkListItem,
  type ChunkDetail,
} from '@/api/chunks'
import { getDocumentStatus } from '@/api/documents'
import { getDataset } from '@/api/datasets'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()
const docId = route.params.docId as string

const docName = ref('')
const datasetName = ref('')
const breadcrumb = ref('分块列表')

const chunks = ref<ChunkListItem[]>([])
const loading = ref(false)
const page = ref(Number(route.query.page) || 1)
const size = ref(Number(route.query.size) || 20)
const total = ref(0)
const selectedKeys = ref<string[]>([])

const splitModalVisible = ref(false)
const splitting = ref(false)
const splitAt = ref(0)
const linkAfterSplit = ref(false)
const currentChunk = ref<ChunkListItem | null>(null)
const chunkDetail = ref<ChunkDetail | null>(null)
const detailLoading = ref(false)

const columns = [
  { title: 'ID', key: 'chunk_id', width: 160 },
  { title: '组ID', dataIndex: 'group_id', key: 'group_id', width: 120, customRender: ({ text }: { text: string }) => text || '-' },
  { title: '页码', dataIndex: 'page', key: 'page', width: 60 },
  { title: '序号', dataIndex: 'chunk_index', key: 'chunk_index', width: 60 },
  { title: '类型', dataIndex: 'chunk_type', key: 'chunk_type', width: 80 },
  { title: '字数', dataIndex: 'char_count', key: 'char_count', width: 70 },
  { title: '内容预览', key: 'full_text', ellipsis: true },
  { title: '操作', key: 'action', width: 180 },
]

async function fetchChunks() {
  loading.value = true
  try {
    const res = await listChunks(docId, { page: page.value, size: size.value })
    chunks.value = res.items
    total.value = res.total
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function syncQuery() {
  router.replace({ query: { page: String(page.value), size: String(size.value) } })
}

function chunkDetailLink(chunkId: string) {
  return { path: `/chunks/${chunkId}`, query: { from: 'chunks', page: String(page.value), size: String(size.value) } }
}

function handleTableChange(pag: { current?: number; pageSize?: number }) {
  page.value = pag.current ?? 1
  size.value = pag.pageSize ?? 20
  syncQuery()
  fetchChunks()
}

async function handleDelete(chunkId: string) {
  try {
    await deleteChunk(chunkId)
    message.success('删除成功')
    fetchChunks()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function handleBatchDelete() {
  Modal.confirm({
    title: '确认删除',
    content: `将删除 ${selectedKeys.value.length} 个分块，确定？`,
    okType: 'danger',
    onOk: async () => {
      try {
        for (const id of selectedKeys.value) {
          await deleteChunk(id)
        }
        message.success('删除成功')
        selectedKeys.value = []
        fetchChunks()
      } catch (e: unknown) {
        message.error((e as Error).message)
      }
    },
  })
}

async function handleMerge() {
  try {
    const res = await mergeChunks(selectedKeys.value)
    message.success(`合并成功，新分块 ${res.merged_chunk_id}`)
    selectedKeys.value = []
    fetchChunks()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function handleLink() {
  try {
    const res = await linkChunks(selectedKeys.value)
    message.success(`已关联到组 ${res.group_id}`)
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function openSplitModal(chunk: ChunkListItem) {
  currentChunk.value = chunk
  splitAt.value = Math.floor(chunk.element_count / 2)
  linkAfterSplit.value = false
  chunkDetail.value = null
  detailLoading.value = true
  splitModalVisible.value = true
  try {
    chunkDetail.value = await getChunkDetail(chunk.chunk_id)
  } catch (e: unknown) {
    message.error((e as Error).message)
    splitModalVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function elementPreview(elem: { type: string; content: string; image_url?: string }) {
  if (elem.type === 'table') {
    const lines = elem.content.split('\n').filter((l: string) => l.trim())
    return `表格 (${lines.length} 行)`
  }
  if (elem.image_url) {
    return `图片`
  }
  return elem.content.slice(0, 50) + (elem.content.length > 50 ? '…' : '')
}

function elementTypeLabel(elem: { type: string; image_url?: string }) {
  if (elem.image_url) return 'image'
  return elem.type || 'text'
}

function splitPreviewText() {
  if (!chunkDetail.value || splitAt.value <= 0) return ''
  const elems = chunkDetail.value.elements
  const aElems = elems.slice(0, splitAt.value)
  const bElems = elems.slice(splitAt.value)
  const aChars = aElems.reduce((s, e) => s + (e.content?.length ?? 0), 0)
  const bChars = bElems.reduce((s, e) => s + (e.content?.length ?? 0), 0)
  return `A 部分 (${aElems.length} 个元素, ${aChars} 字)  |  B 部分 (${bElems.length} 个元素, ${bChars} 字)`
}

async function handleSplit() {
  if (!currentChunk.value) return
  splitting.value = true
  try {
    await splitChunk(currentChunk.value.chunk_id, splitAt.value, linkAfterSplit.value)
    message.success('拆分成功')
    splitModalVisible.value = false
    fetchChunks()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    splitting.value = false
  }
}

async function fetchBreadcrumb() {
  try {
    const doc = await getDocumentStatus(docId)
    docName.value = doc.filename
    if (doc.dataset_id) {
      const ds = await getDataset(doc.dataset_id)
      datasetName.value = ds.name
      breadcrumb.value = `${ds.name}  ›  ${doc.filename}`
    } else {
      breadcrumb.value = doc.filename
    }
  } catch { /* ignore */ }
}

onMounted(() => {
  fetchBreadcrumb()
  fetchChunks()
})
</script>

<style scoped>
.page-container {
  padding: var(--space-6) var(--space-8);
  max-width: 1400px;
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

.header-actions {
  display: flex;
  gap: var(--space-2);
}

.chunk-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.chunk-id-link {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-primary);
}

.text-preview {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.element-list {
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 4px 0;
}

.element-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  font-size: var(--font-size-sm);
}

.element-content {
  color: var(--color-text-secondary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.split-divider {
  position: relative;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.15s;
  margin: 0 8px;
  border-radius: var(--radius-sm);
}

.split-divider::before {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  top: 50%;
  height: 1px;
  background: var(--color-border);
  transition: background-color 0.15s;
}

.split-divider:hover {
  background-color: var(--color-primary-bg);
}

.split-divider:hover::before {
  background: var(--color-primary);
}

.split-divider.active {
  background-color: var(--color-primary-bg);
}

.split-divider.active::before {
  height: 2px;
  background: var(--color-primary);
}

.divider-label {
  position: relative;
  z-index: 1;
  background: var(--color-bg-container);
  padding: 0 8px;
  font-size: 12px;
  color: var(--color-text-quaternary);
  opacity: 0;
  transition: opacity 0.15s;
  pointer-events: none;
}

.split-divider:hover .divider-label,
.split-divider.active .divider-label {
  opacity: 1;
  color: var(--color-primary);
}

.split-preview {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--color-fill-quaternary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  text-align: center;
}
</style>
