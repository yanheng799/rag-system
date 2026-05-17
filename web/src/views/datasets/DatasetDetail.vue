<template>
  <div class="page-container">
    <div class="detail-header">
      <a-button type="text" @click="router.push('/datasets')" class="back-btn">
        <arrow-left-outlined /> 返回
      </a-button>
      <div class="detail-info" v-if="dataset">
        <h1 class="detail-name">{{ dataset.name }}</h1>
        <p class="detail-desc" v-if="dataset.description">{{ dataset.description }}</p>
      </div>
    </div>

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
        <div class="upload-icon-wrap">
          <upload-outlined aria-hidden="true" />
        </div>
        <div class="upload-text">
          <span class="upload-main">拖拽文件到此处，或点击上传</span>
          <span class="upload-formats">PDF / Word / Excel / TXT / MD / CSV，单文件最大 50MB</span>
        </div>
      </div>
    </a-upload-dragger>

    <div v-if="uploadQueue.length > 0" class="upload-queue">
      <div v-for="item in uploadQueue" :key="item.uid" class="upload-item">
        <div class="upload-item-info">
          <file-outlined aria-hidden="true" class="upload-file-icon" />
          <span class="upload-filename">{{ item.filename }}</span>
          <a-tag v-if="item.status === 'uploading'" color="processing">上传中</a-tag>
          <a-tag v-else-if="item.status === 'done'" color="success">已上传</a-tag>
          <a-tag v-else-if="item.status === 'error'" color="error">失败</a-tag>
        </div>
        <a-progress v-if="item.status === 'uploading'" :percent="item.percent" size="small" :show-info="false" />
        <div v-if="item.errorMsg" class="upload-error">{{ item.errorMsg }}</div>
      </div>
    </div>

    <!-- 解析策略配置 -->
    <div class="strategy-section">
      <div class="strategy-header">
        <div>
          <h3 class="strategy-title">解析策略</h3>
          <p class="strategy-subtitle">选择文档的分块方式，不同策略影响检索精度</p>
        </div>
        <a-popover trigger="click" placement="bottomRight" overlay-class-name="strategy-popover">
          <template #content>
            <div class="advanced-form">
              <div class="advanced-title">高级参数</div>
              <div class="advanced-item">
                <label class="advanced-label">最大分块字符数</label>
                <a-input-number v-model:value="chunkForm.max_size" :min="100" :max="8192" placeholder="默认 1024" size="small" class="advanced-input" />
              </div>
              <div v-if="chunkForm.strategy === 'fixed_size'" class="advanced-item">
                <label class="advanced-label">重叠字符数</label>
                <a-input-number v-model:value="chunkForm.overlap" :min="0" :max="512" placeholder="默认 0" size="small" class="advanced-input" />
              </div>
              <div v-if="chunkForm.strategy === 'paragraph'" class="advanced-item">
                <label class="advanced-label">垂直间距阈值(px)</label>
                <a-input-number v-model:value="chunkForm.vertical_gap" :min="0" :max="100" :step="0.5" placeholder="默认 15" size="small" class="advanced-input" />
              </div>
              <div class="advanced-item">
                <label class="advanced-label">最小分块字符数</label>
                <a-input-number v-model:value="chunkForm.min_size" :min="0" :max="500" placeholder="默认 50" size="small" class="advanced-input" />
              </div>
            </div>
          </template>
          <a-button type="text" size="small" class="strategy-advanced-btn">
            <setting-outlined /> 高级设置
          </a-button>
        </a-popover>
      </div>
      <div class="strategy-pills">
        <div class="strategy-pill" :class="{ active: chunkForm.strategy === 'paragraph' }" @click="chunkForm.strategy = 'paragraph'">
          <align-left-outlined />
          <span>段落分块</span>
          <span class="strategy-pill-badge">推荐</span>
        </div>
        <div class="strategy-pill" :class="{ active: chunkForm.strategy === 'heading' }" @click="chunkForm.strategy = 'heading'">
          <read-outlined />
          <span>标题分块</span>
        </div>
        <div class="strategy-pill" :class="{ active: chunkForm.strategy === 'fixed_size' }" @click="chunkForm.strategy = 'fixed_size'">
          <column-width-outlined />
          <span>固定大小</span>
        </div>
        <div class="strategy-pill" :class="{ active: chunkForm.strategy === 'page' }" @click="chunkForm.strategy = 'page'">
          <file-text-outlined />
          <span>逐页分块</span>
        </div>
        <div class="strategy-pill" :class="{ active: chunkForm.strategy === 'qa' }" @click="chunkForm.strategy = 'qa'">
          <message-outlined />
          <span>QA 分块</span>
        </div>
        <span class="strategy-hint">{{ strategyDesc }}</span>
      </div>
    </div>

    <div class="table-toolbar">
      <h3 class="section-title">文档列表</h3>
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
          <reload-outlined /> 刷新
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
      class="doc-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
        </template>
        <template v-if="column.key === 'file_type'">
          <span class="file-type-badge">{{ record.file_type || '-' }}</span>
        </template>
        <template v-if="column.key === 'file_size'">
          <span class="tabular-nums">{{ formatFileSize(record.file_size) }}</span>
        </template>
        <template v-if="column.key === 'chunk_count'">
          <span class="tabular-nums">{{ record.chunk_count || '-' }}</span>
        </template>
        <template v-if="column.key === 'chunk_options'">
          <template v-if="record.chunk_options">
            <a-tag size="small">{{ strategyLabel(record.chunk_options.strategy) }}</a-tag>
            <a-tooltip :title="formatChunkParamsFull(record.chunk_options)">
              <span class="chunk-params-text">{{ formatChunkParams(record.chunk_options) }}</span>
            </a-tooltip>
          </template>
          <span v-else class="text-muted">-</span>
        </template>
        <template v-if="column.key === 'error_msg'">
          <a-tooltip v-if="record.error_msg" :title="record.error_msg">
            <span class="error-text">{{ record.error_msg }}</span>
          </a-tooltip>
          <span v-else class="text-muted">-</span>
        </template>
        <template v-if="column.key === 'action'">
          <a-space :size="4">
            <a-tooltip v-if="record.status === 'done'" title="查看文档">
              <router-link :to="`/documents/${record.doc_id}/viewer`">
                <a-button type="text" size="small" class="action-btn-primary"><EyeOutlined /></a-button>
              </router-link>
            </a-tooltip>
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

    <a-modal v-model:open="editModalVisible" title="编辑知识库" @ok="handleEditSubmit" :confirm-loading="editSubmitting" centered>
      <a-form layout="vertical" :model="editForm" :rules="editFormRules" ref="editFormRef" style="margin-top: 16px">
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
import { UploadOutlined, SettingOutlined, InfoCircleOutlined, ReloadOutlined, SearchOutlined, FileSearchOutlined, UnorderedListOutlined, RedoOutlined, DeleteOutlined, FileOutlined, ArrowLeftOutlined, EyeOutlined, AlignLeftOutlined, ReadOutlined, ColumnWidthOutlined, FileTextOutlined, MessageOutlined } from '@ant-design/icons-vue'
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
  { title: '分块', key: 'chunk_count', width: 60 },
  { title: '策略', key: 'chunk_options', width: 180 },
  { title: '状态', key: 'status', width: 80 },
  { title: '错误信息', key: 'error_msg', width: 160, ellipsis: true },
  { title: '操作', key: 'action', width: 260 },
]

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const strategyLabels: Record<string, string> = {
  paragraph: '段落', heading: '标题', fixed_size: '固定', page: '逐页', qa: 'QA',
}

function strategyLabel(s: unknown) {
  return strategyLabels[s as string] || (s as string) || '-'
}

function formatChunkParams(opts: Record<string, unknown>): string {
  const parts: string[] = []
  if (opts.max_size) parts.push(`最大${opts.max_size}`)
  if (opts.min_size) parts.push(`最小${opts.min_size}`)
  if (opts.overlap) parts.push(`重叠${opts.overlap}`)
  if (opts.vertical_gap) parts.push(`间距${opts.vertical_gap}`)
  return parts.join(' / ')
}

function formatChunkParamsFull(opts: Record<string, unknown>): string {
  const lines = [`策略: ${strategyLabels[opts.strategy as string] || opts.strategy}`]
  if (opts.max_size) lines.push(`最大分块: ${opts.max_size} 字符`)
  if (opts.min_size) lines.push(`最小分块: ${opts.min_size} 字符`)
  if (opts.overlap) lines.push(`重叠字符: ${opts.overlap}`)
  if (opts.vertical_gap) lines.push(`垂直间距: ${opts.vertical_gap}px`)
  return lines.join('\n')
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
      chunk_options: d.chunk_options,
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
        chunk_options: null,
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
  padding: var(--space-6) var(--space-8);
  max-width: 1400px;
  margin: 0 auto;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.back-btn {
  margin-top: 2px;
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
}

.back-btn:hover {
  color: var(--color-primary);
}

.detail-info {
  flex: 1;
}

.detail-name {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  letter-spacing: -0.02em;
}

.detail-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
}

.compact-uploader :deep(.ant-upload-drag) {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-lg);
  border: 2px dashed var(--color-border-strong);
  background: var(--color-bg-elevated);
  transition: all var(--transition-normal);
}

.compact-uploader :deep(.ant-upload-drag:hover) {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.compact-upload-inner {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.upload-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: var(--color-primary);
  flex-shrink: 0;
}

.upload-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.upload-main {
  font-size: var(--font-size-base);
  color: var(--color-text-primary);
  font-weight: 500;
}

.upload-formats {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.upload-queue {
  margin-top: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-elevated);
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

.upload-file-icon {
  color: var(--color-primary);
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

/* ── Strategy Section ── */
.strategy-section {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, #ffffff 0%, #faf8ff 100%);
}

.strategy-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.strategy-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.strategy-subtitle {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin: 0;
  line-height: 1.4;
}

.strategy-advanced-btn {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  flex-shrink: 0;
}

.strategy-advanced-btn:hover {
  color: var(--color-primary);
}

.strategy-pills {
  display: flex;
  gap: 6px;
  margin-top: var(--space-2);
  flex-wrap: wrap;
}

.strategy-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--transition-fast);
  background: var(--color-bg-elevated);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  position: relative;
  white-space: nowrap;
}

.strategy-pill:hover {
  border-color: var(--color-primary-border);
  color: var(--color-text-primary);
}

.strategy-pill.active {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
  color: var(--color-primary);
  font-weight: 500;
}

.strategy-pill-badge {
  font-size: 10px;
  color: var(--color-accent);
  background: var(--color-accent-bg);
  padding: 0 5px;
  border-radius: var(--radius-full);
  line-height: 1.5;
}

.strategy-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-left: auto;
  white-space: nowrap;
}

/* ── Table Toolbar ── */
.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: var(--space-6) 0 var(--space-4);
}

.section-title {
  margin: 0;
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
}

.advanced-form {
  width: 260px;
  padding: var(--space-1) 0;
}

.advanced-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

.advanced-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.advanced-item:last-child {
  margin-bottom: 0;
}

.advanced-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.advanced-input {
  width: 110px;
}

.doc-table {
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.file-type-badge {
  font-size: var(--font-size-xs);
  font-weight: 500;
  text-transform: uppercase;
  color: var(--color-text-secondary);
}

.error-text {
  color: var(--color-error);
  font-size: var(--font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  max-width: 140px;
}

.chunk-params-text {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.text-muted {
  color: var(--color-text-tertiary);
}

.action-btn-info { color: var(--color-primary) !important; }
.action-btn-purple { color: #7c3aed !important; }
.action-btn-primary { color: var(--color-success) !important; }
.action-btn-warning { color: var(--color-warning) !important; }
</style>
