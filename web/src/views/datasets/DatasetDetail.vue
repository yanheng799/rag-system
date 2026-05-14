<template>
  <div class="page-container">
    <a-page-header
      :title="dataset?.name || '加载中…'"
      :sub-title="dataset?.description"
      @back="router.push('/datasets')"
    >
      <template #extra>
        <a-button @click="openEditModal">编辑</a-button>
        <a-button danger @click="confirmDeleteDataset">删除</a-button>
      </template>
    </a-page-header>

    <a-upload-dragger
      :multiple="true"
      accept=".pdf,.docx,.xlsx"
      :custom-request="handleUpload"
      :show-upload-list="false"
      :disabled="uploading"
    >
      <p class="ant-upload-drag-icon"><inbox-outlined /></p>
      <p class="ant-upload-text">拖拽文件到此处，或点击上传</p>
      <p class="ant-upload-hint">支持 PDF、Word (.docx)、Excel (.xlsx)，单文件最大 50MB</p>
    </a-upload-dragger>

    <a-spin :spinning="uploading" tip="上传中…">
      <div></div>
    </a-spin>

    <a-divider />

    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h3 style="margin: 0">文档列表</h3>
      <a-space>
        <a-button
          type="primary"
          :disabled="selectedPending.length === 0"
          :loading="ingesting"
          @click="handleIngest"
        >
          开始解析选中（{{ selectedPending.length }}）
        </a-button>
        <a-button :loading="refreshing" @click="handleRefresh">
          <reload-outlined /> 刷新
        </a-button>
      </a-space>
    </div>
    <a-table
      :columns="columns"
      :data-source="docs"
      :pagination="false"
      :row-selection="rowSelection"
      row-key="doc_id"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
        </template>
        <template v-if="column.key === 'error_msg'">
          <span v-if="record.error_msg" class="error-text">{{ record.error_msg }}</span>
          <span v-else>-</span>
        </template>
        <template v-if="column.key === 'action'">
          <a-space>
            <router-link v-if="record.status === 'done'" :to="`/documents/${record.doc_id}/chunks`">查看分块</router-link>
            <a-button v-if="record.status === 'failed'" type="link" size="small" @click="retryDoc(record.doc_id)">重试</a-button>
            <a-popconfirm title="确定删除？" @confirm="handleDeleteDoc(record.doc_id)">
              <a-button type="link" danger size="small">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-modal v-model:open="editModalVisible" title="编辑知识库" @ok="handleEditSubmit" :confirm-loading="editSubmitting">
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="editForm.name" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="editForm.description" :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { InboxOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { getDataset, updateDataset, deleteDataset, type DatasetResponse } from '@/api/datasets'
import { uploadDocuments, ingestDocuments, getDocumentStatus, deleteDocument, listDocuments, type DocumentStatusResponse } from '@/api/documents'

const router = useRouter()
const route = useRoute()
const datasetId = route.params.id as string

const dataset = ref<DatasetResponse | null>(null)
const docs = ref<DocumentStatusResponse[]>([])
const uploading = ref(false)
const ingesting = ref(false)
const refreshing = ref(false)
const selectedPending = ref<string[]>([])
const editModalVisible = ref(false)
const editSubmitting = ref(false)
const editForm = ref({ name: '', description: '' })

let pollTimer: ReturnType<typeof setInterval> | null = null

const selectableStatuses = new Set(['pending', 'failed'])

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
  { title: '状态', key: 'status', width: 100 },
  { title: '错误信息', key: 'error_msg', ellipsis: true },
  { title: '操作', key: 'action', width: 200 },
]

function statusColor(s: string) {
  return { pending: 'default', processing: 'processing', done: 'success', failed: 'error' }[s] || 'default'
}

function statusLabel(s: string) {
  return { pending: '待处理', processing: '处理中', done: '已完成', failed: '失败' }[s] || s
}

async function fetchDataset() {
  try {
    dataset.value = await getDataset(datasetId)
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

async function fetchDocs() {
  try {
    const res = await listDocuments({ dataset_id: datasetId, size: 100 })
    docs.value = res.items.map((d) => ({
      doc_id: d.doc_id,
      filename: d.filename,
      status: d.status,
      error_msg: d.error_msg,
      uploaded_at: d.uploaded_at,
      updated_at: d.updated_at,
    }))
  } catch (e: unknown) {
    message.error((e as Error).message)
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
        uploaded_at: u.uploaded_at,
        updated_at: null,
      })
    }
    message.success('上传成功')
    fetchDataset()
    options.onSuccess?.()
  } catch (e: unknown) {
    message.error((e as Error).message)
    options.onError?.(e as Error)
  } finally {
    uploading.value = false
  }
}

async function handleIngest() {
  if (selectedPending.value.length === 0) return
  ingesting.value = true
  try {
    await ingestDocuments(selectedPending.value)
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
    await ingestDocuments([docId])
    const d = docs.value.find((d) => d.doc_id === docId)
    if (d) d.status = 'processing'
    message.success('已重新提交')
    startPolling()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
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
  padding: 0 24px 24px;
}

.error-text {
  color: #ff4d4f;
  font-size: 12px;
}
</style>
