<template>
  <div class="page-container">
    <a-page-header
      :title="dataset?.name || '加载中…'"
      :sub-title="dataset?.description"
      @back="router.push('/datasets')"
    >
    </a-page-header>

    <a-skeleton v-if="!dataset" active :paragraph="{ rows: 2 }" />

    <template v-if="dataset">
    <a-upload-dragger
      class="compact-uploader"
      :multiple="true"
      accept=".pdf,.docx,.xlsx,.txt,.md,.csv"
      :custom-request="handleUpload"
      :show-upload-list="false"
      :disabled="uploading"
    >
      <div class="compact-upload-inner">
        <upload-outlined aria-hidden="true" />
        <span>拖拽文件到此处，或点击上传</span>
        <span class="upload-formats">PDF / Word / Excel / TXT / MD / CSV，单文件最大 50MB</span>
      </div>
    </a-upload-dragger>

    <div v-if="uploadQueue.length > 0" class="upload-queue">
      <div v-for="item in uploadQueue" :key="item.uid" class="upload-item">
        <div class="upload-item-info">
          <file-outlined aria-hidden="true" />
          <span class="upload-filename">{{ item.filename }}</span>
          <a-tag v-if="item.status === 'uploading'" color="processing">上传中</a-tag>
          <a-tag v-else-if="item.status === 'done'" color="success">已上传</a-tag>
          <a-tag v-else-if="item.status === 'error'" color="error">失败</a-tag>
        </div>
        <a-progress v-if="item.status === 'uploading'" :percent="item.percent" size="small" :show-info="false" />
        <div v-if="item.errorMsg" class="upload-error">{{ item.errorMsg }}</div>
      </div>
    </div>

    <div class="table-toolbar">
      <div class="toolbar-left">
        <h3 style="margin: 0">文档列表</h3>
        <a-select v-model:value="chunkForm.strategy" style="width: 130px" size="small">
          <a-select-option value="paragraph">段落分块</a-select-option>
          <a-select-option value="heading">标题分块</a-select-option>
          <a-select-option value="fixed_size">固定大小</a-select-option>
          <a-select-option value="page">逐页分块</a-select-option>
          <a-select-option value="qa">QA 分块</a-select-option>
        </a-select>
        <a-tooltip :title="strategyDesc">
          <info-circle-outlined style="color: var(--color-text-tertiary); cursor: help" aria-hidden="true" />
        </a-tooltip>
        <a-popover trigger="click" placement="bottomLeft">
          <template #content>
            <div class="advanced-form">
              <a-form layout="vertical" size="small">
                <a-form-item label="最大分块字符数">
                  <a-input-number v-model:value="chunkForm.max_size" :min="100" :max="8192" placeholder="默认 1024" name="max_size" />
                </a-form-item>
                <a-form-item v-if="chunkForm.strategy === 'fixed_size'" label="重叠字符数">
                  <a-input-number v-model:value="chunkForm.overlap" :min="0" :max="512" placeholder="默认 0" name="overlap" />
                </a-form-item>
                <a-form-item v-if="chunkForm.strategy === 'paragraph'" label="垂直间距阈值(px)">
                  <a-input-number v-model:value="chunkForm.vertical_gap" :min="0" :max="100" :step="0.5" placeholder="默认 15" name="vertical_gap" />
                </a-form-item>
                <a-form-item label="最小分块字符数">
                  <a-input-number v-model:value="chunkForm.min_size" :min="0" :max="500" placeholder="默认 50" name="min_size" />
                </a-form-item>
              </a-form>
            </div>
          </template>
          <a-button type="text" size="small"><setting-outlined aria-hidden="true" /> 高级</a-button>
        </a-popover>
      </div>
      <a-space>
        <a-button
          type="primary"
          :disabled="selectedPending.length === 0"
          :loading="ingesting"
          @click="handleIngest"
        >
          开始解析（{{ selectedPending.length }}）
        </a-button>
        <a-button :loading="refreshing" @click="handleRefresh" aria-label="刷新">
          <reload-outlined aria-hidden="true" /> 刷新
        </a-button>
      </a-space>
    </div>
    <a-table
      :columns="columns"
      :data-source="docs"
      :loading="loadingDocs"
      :pagination="false"
      :row-selection="rowSelection"
      row-key="doc_id"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
        </template>
        <template v-if="column.key === 'file_type'">
          <span>{{ record.file_type || '-' }}</span>
        </template>
        <template v-if="column.key === 'file_size'">
          <span>{{ formatFileSize(record.file_size) }}</span>
        </template>
        <template v-if="column.key === 'chunk_count'">
          <span>{{ record.chunk_count || '-' }}</span>
        </template>
        <template v-if="column.key === 'error_msg'">
          <span v-if="record.error_msg" class="error-text">{{ record.error_msg }}</span>
          <span v-else>-</span>
        </template>
        <template v-if="column.key === 'action'">
          <a-space :size="4">
            <a-tooltip v-if="record.status === 'done'" title="查看分块">
              <router-link :to="`/documents/${record.doc_id}/chunks`">
                <a-button type="text" size="small" class="action-btn-info"><UnorderedListOutlined /></a-button>
              </router-link>
            </a-tooltip>
            <a-tooltip v-if="record.status === 'done'" title="语义检索">
              <router-link :to="{ path: '/retrieve', query: { dataset_ids: datasetId, doc_ids: record.doc_id } }">
                <a-button type="text" size="small" class="action-btn-purple"><FileSearchOutlined /></a-button>
              </router-link>
            </a-tooltip>
            <a-tooltip v-if="record.status === 'done'" title="智能问答">
              <router-link :to="{ path: '/query', query: { dataset_ids: datasetId, doc_ids: record.doc_id } }">
                <a-button type="text" size="small" class="action-btn-primary"><SearchOutlined /></a-button>
              </router-link>
            </a-tooltip>
            <a-tooltip v-if="record.status === 'done'" title="重新解析">
              <a-button type="text" size="small" class="action-btn-warning" @click="confirmReparse(record)"><RedoOutlined /></a-button>
            </a-tooltip>
            <a-tooltip v-if="record.status === 'failed'" title="重试解析">
              <a-button type="text" size="small" class="action-btn-warning" @click="confirmReparse(record)"><RedoOutlined /></a-button>
            </a-tooltip>
            <a-tooltip title="删除">
              <a-popconfirm title="确定删除？" @confirm="handleDeleteDoc(record.doc_id)">
                <a-button type="text" size="small" danger><DeleteOutlined /></a-button>
              </a-popconfirm>
            </a-tooltip>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal v-model:open="editModalVisible" title="编辑知识库" @ok="handleEditSubmit" :confirm-loading="editSubmitting">
      <a-form layout="vertical" :model="editForm" :rules="editFormRules" ref="editFormRef">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="editForm.name" name="name" autocomplete="off" />
        </a-form-item>
        <a-form-item label="描述" name="description">
          <a-textarea v-model:value="editForm.description" :rows="3" name="description" />
        </a-form-item>
      </a-form>
    </a-modal>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { UploadOutlined, SettingOutlined, InfoCircleOutlined, ReloadOutlined, SearchOutlined, FileSearchOutlined, UnorderedListOutlined, RedoOutlined, DeleteOutlined, FileOutlined } from '@ant-design/icons-vue'
import { getDataset, updateDataset, deleteDataset, type DatasetResponse } from '@/api/datasets'
import { uploadDocuments, ingestDocuments, getDocumentStatus, deleteDocument, listDocuments, type DocumentStatusResponse, type ChunkOptions } from '@/api/documents'

const router = useRouter()
const route = useRoute()
const datasetId = route.params.id as string

const dataset = ref<DatasetResponse | null>(null)
const docs = ref<DocumentStatusResponse[]>([])
const loadingDocs = ref(false)
const uploading = ref(false)
const uploadQueue = ref<{ uid: number; filename: string; status: 'uploading' | 'done' | 'error'; percent: number; errorMsg?: string }[]>([])
let uploadUid = 0
const ingesting = ref(false)
const refreshing = ref(false)
const selectedPending = ref<string[]>([])
const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ name: '', description: '' })
const editFormRef = ref()

const editFormRules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

const chunkForm = ref({
  strategy: 'paragraph',
  max_size: null as number | null,
  min_size: null as number | null,
  overlap: null as number | null,
  vertical_gap: null as number | null,
})

const strategyDesc = computed(() => ({
  paragraph: '按段落边界分块，适合书籍、论文、连续文本（PDF/Word 推荐）',
  heading: '按标题章节边界分块，适合技术文档、法规文件（PDF/Word 推荐）',
  fixed_size: '按固定字符数切割，适合通用场景',
  page: '按页码分块，适合表格密集文档（Excel 推荐）',
  qa: '逐行分块，适合 CSV/Excel 问答对、知识条目',
}[chunkForm.value.strategy] || ''))

let pollTimer: ReturnType<typeof setInterval> | null = null

const selectableStatuses = new Set(['pending', 'failed', 'accepted', 'done'])

const rowSelection = computed(() => ({
  selectedRowKeys: selectedPending.value,
  onChange: (keys: string[]) => {
    selectedPending.value = keys
  },
  getCheckboxProps: (record: DocumentStatusResponse) => ({
    disabled: !selectableStatuses.has(record.status),
  }),
}))

const columns = [
  { title: '文件名', dataIndex: 'filename', key: 'filename' },
  { title: '类型', key: 'file_type', width: 70 },
  { title: '大小', key: 'file_size', width: 90 },
  { title: '分块', key: 'chunk_count', width: 70 },
  { title: '状态', key: 'status', width: 100 },
  { title: '错误信息', key: 'error_msg', ellipsis: true },
  { title: '操作', key: 'action', width: 260 },
]

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function statusColor(s: string) {
  return { pending: 'default', processing: 'processing', done: 'success', failed: 'error', accepted: 'processing' }[s] || 'default'
}

function statusLabel(s: string) {
  return { pending: '待处理', processing: '处理中', done: '已完成', failed: '失败', accepted: '已提交' }[s] || s
}

async function fetchDataset() {
  try {
    dataset.value = await getDataset(datasetId)
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function fetchDocs() {
  loadingDocs.value = true
  try {
    const res = await listDocuments({ dataset_id: datasetId, size: 100 })
    docs.value = res.items.map((d) => ({
      doc_id: d.doc_id,
      filename: d.filename,
      status: d.status,
      error_msg: d.error_msg,
      file_size: d.file_size,
      file_type: d.file_type,
      chunk_count: d.chunk_count,
      uploaded_at: d.uploaded_at,
      updated_at: d.updated_at,
    }))
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loadingDocs.value = false
  }
}

async function handleRefresh() {
  refreshing.value = true
  try {
    await Promise.all([fetchDataset(), fetchDocs()])
    message.success('刷新成功')
  } finally {
    refreshing.value = false
  }
}

async function handleUpload(options: { file: File; onSuccess?: () => void; onError?: (e: Error) => void }) {
  const uid = ++uploadUid
  const queueItem = { uid, filename: options.file.name, status: 'uploading' as const, percent: 0 }
  uploadQueue.value.push(queueItem)
  uploading.value = true
  try {
    const res = await uploadDocuments([options.file], datasetId)
    const uploaded = Array.isArray(res) ? res : res.data
    for (const u of uploaded) {
      docs.value.unshift({
        doc_id: u.doc_id,
        filename: u.filename,
        status: 'pending',
        error_msg: null,
        file_size: options.file.size,
        file_type: options.file.name.split('.').pop() || null,
        chunk_count: 0,
        uploaded_at: u.uploaded_at,
        updated_at: null,
      })
    }
    const item = uploadQueue.value.find((i) => i.uid === uid)
    if (item) { item.status = 'done'; item.percent = 100 }
    message.success(`${options.file.name} 上传成功`)
    fetchDataset()
    options.onSuccess?.()
  } catch (e: unknown) {
    const item = uploadQueue.value.find((i) => i.uid === uid)
    const errMsg = (e as Error).message
    if (item) { item.status = 'error'; item.errorMsg = errMsg }
    message.error(errMsg)
    options.onError?.(e as Error)
  } finally {
    uploading.value = uploadQueue.value.some((i) => i.status === 'uploading')
  }
}

async function handleIngest() {
  if (selectedPending.value.length === 0) return
  ingesting.value = true
  try {
    await ingestDocuments(selectedPending.value, buildChunkOptions())
    message.success('已提交解析任务')
    for (const id of selectedPending.value) {
      const d = docs.value.find((d) => d.doc_id === id)
      if (d) d.status = 'processing'
    }
    selectedPending.value = []
    startPolling()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    ingesting.value = false
  }
}

async function pollStatus(docId: string) {
  try {
    const res = await getDocumentStatus(docId)
    const idx = docs.value.findIndex((d) => d.doc_id === docId)
    if (idx >= 0) docs.value[idx] = res
  } catch { /* ignore */ }
}

async function retryDoc(docId: string) {
  try {
    await ingestDocuments([docId], buildChunkOptions())
    const d = docs.value.find((d) => d.doc_id === docId)
    if (d) d.status = 'processing'
    message.success('已重新提交')
    startPolling()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

function confirmReparse(record: DocumentStatusResponse) {
  const strategyName: Record<string, string> = {
    paragraph: '按段落', heading: '按标题', fixed_size: '固定大小', page: '按页码', qa: '逐行(QA)',
  }
  const s = chunkForm.value.strategy
  const lines = [`策略: ${strategyName[s] || s}`]
  if (chunkForm.value.max_size != null) lines.push(`最大分块: ${chunkForm.value.max_size} 字符`)
  if (chunkForm.value.min_size != null) lines.push(`最小分块: ${chunkForm.value.min_size} 字符`)
  if (chunkForm.value.overlap != null) lines.push(`重叠字符: ${chunkForm.value.overlap}`)
  if (chunkForm.value.vertical_gap != null) lines.push(`垂直间距: ${chunkForm.value.vertical_gap}`)
  const isRedo = record.status === 'done'
  Modal.confirm({
    title: isRedo ? `重新解析「${record.filename}」？` : `重试解析「${record.filename}」？`,
    content: isRedo
      ? `将清除现有分块和向量，使用以下参数重新解析：\n${lines.join('\n')}`
      : `使用以下参数重新解析：\n${lines.join('\n')}`,
    okText: '确认解析',
    async onOk() {
      await retryDoc(record.doc_id)
    },
  })
}

async function handleDeleteDoc(docId: string) {
  try {
    await deleteDocument(docId)
    docs.value = docs.value.filter((d) => d.doc_id !== docId)
    message.success('删除成功')
    fetchDataset()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    const processing = docs.value.filter((d) => d.status === 'processing')
    if (processing.length === 0) {
      stopPolling()
      return
    }
    for (const d of processing) {
      await pollStatus(d.doc_id)
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function openEditModal() {
  editForm.value = { name: dataset.value?.name || '', description: dataset.value?.description || '' }
  editModalVisible.value = true
}

async function handleEditSubmit() {
  try {
    await editFormRef.value?.validateFields()
  } catch {
    return
  }
  editSubmitting.value = true
  try {
    await updateDataset(datasetId, editForm.value)
    message.success('更新成功')
    editModalVisible.value = false
    fetchDataset()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    editSubmitting.value = false
  }
}

function buildChunkOptions(): ChunkOptions | undefined {
  const opts: ChunkOptions = {}
  let hasValue = false
  if (chunkForm.value.strategy) { opts.strategy = chunkForm.value.strategy; hasValue = true }
  if (chunkForm.value.max_size != null) { opts.max_size = chunkForm.value.max_size; hasValue = true }
  if (chunkForm.value.min_size != null) { opts.min_size = chunkForm.value.min_size; hasValue = true }
  if (chunkForm.value.overlap != null) { opts.overlap = chunkForm.value.overlap; hasValue = true }
  if (chunkForm.value.vertical_gap != null) { opts.vertical_gap = chunkForm.value.vertical_gap; hasValue = true }
  return hasValue ? opts : undefined
}

function confirmDeleteDataset() {
  Modal.confirm({
    title: '确认删除知识库？',
    content: '将删除知识库及其所有文档、分块和向量数据',
    okType: 'danger',
    onOk: async () => {
      try {
        await deleteDataset(datasetId, true)
        message.success('删除成功')
        router.push('/datasets')
      } catch (e: unknown) {
        message.error((e as Error).message)
      }
    },
  })
}

onMounted(() => {
  fetchDataset()
  fetchDocs()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.page-container {
  padding: 0 var(--space-6) var(--space-6);
}

.compact-uploader :deep(.ant-upload-drag) {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
}

.compact-upload-inner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

.upload-formats {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.error-text {
  color: var(--color-error);
  font-size: var(--font-size-xs);
}

.action-btn-info { color: #1677ff !important; }
.action-btn-purple { color: #722ed1 !important; }
.action-btn-primary { color: #52c41a !important; }
.action-btn-warning { color: #fa8c16 !important; }

.upload-queue {
  margin-top: var(--space-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
}

.upload-item {
  padding: var(--space-2) 0;
}

.upload-item + .upload-item {
  border-top: 1px solid var(--color-border);
}

.upload-item-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
}

.upload-filename {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-error {
  font-size: var(--font-size-xs);
  color: var(--color-error);
  margin-top: var(--space-1);
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: var(--space-4) 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.advanced-form {
  width: 240px;
}
</style>
