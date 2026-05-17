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
            <a-button type="link" size="small" @click="openSplitModal(record)">拆分</a-button>
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
      centered
    >
      <p>将在指定字符位置拆分此分块为两个。</p>
      <a-input-number
        v-model:value="splitAt"
        :min="1"
        :max="currentChunk?.char_count ?? 1"
        style="width: 100%"
        addon-before="拆分位置"
      />
      <div style="margin-top: 8px">
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
  type ChunkListItem,
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

function openSplitModal(chunk: ChunkListItem) {
  currentChunk.value = chunk
  splitAt.value = Math.floor(chunk.char_count / 2)
  linkAfterSplit.value = false
  splitModalVisible.value = true
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
</style>
