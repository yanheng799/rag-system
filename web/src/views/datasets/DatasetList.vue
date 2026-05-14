<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">知识库管理</h2>
      <a-button type="primary" @click="showCreateModal = true">
        <plus-outlined /> 新建知识库
      </a-button>
    </div>

    <a-row :gutter="[16, 16]">
      <a-col v-for="ds in datasets" :key="ds.dataset_id" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card hoverable @click="router.push(`/datasets/${ds.dataset_id}`)">
          <template #actions>
            <a-tooltip title="问答"><message-outlined @click.stop="router.push({ path: '/query', query: { dataset_ids: ds.dataset_id } })" /></a-tooltip>
            <a-tooltip title="检索"><search-outlined @click.stop="router.push({ path: '/retrieve', query: { dataset_ids: ds.dataset_id } })" /></a-tooltip>
            <a-tooltip title="编辑"><edit-outlined @click.stop="openEdit(ds)" /></a-tooltip>
            <a-tooltip title="删除"><delete-outlined @click.stop="confirmDelete(ds)" /></a-tooltip>
          </template>
          <a-card-meta :title="ds.name">
            <template #description>
              <div>{{ ds.description || '暂无描述' }}</div>
              <div style="margin-top: 8px; color: #999; font-size: 12px">
                {{ ds.doc_count }} 份文档 · {{ formatDate(ds.created_at) }}
              </div>
            </template>
          </a-card-meta>
        </a-card>
      </a-col>
    </a-row>

    <a-empty v-if="!loading && datasets.length === 0" description="暂无知识库，点击右上角创建" />

    <div style="text-align: center; margin-top: 24px">
      <a-pagination
        v-model:current="page"
        :total="total"
        :page-size="pageSize"
        show-quick-jumper
        @change="fetchDatasets"
      />
    </div>

    <a-modal
      v-model:open="showCreateModal"
      :title="editingDataset ? '编辑知识库' : '新建知识库'"
      @ok="handleSubmit"
      :confirm-loading="submitting"
    >
      <a-form layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="form.name" :maxlength="256" placeholder="请输入知识库名称" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" :rows="3" placeholder="可选描述" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Modal, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons-vue'
import {
  listDatasets,
  createDataset,
  updateDataset,
  deleteDataset,
  type DatasetResponse,
} from '@/api/datasets'

const router = useRouter()
const datasets = ref<DatasetResponse[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(12)
const total = ref(0)

const showCreateModal = ref(false)
const submitting = ref(false)
const editingDataset = ref<DatasetResponse | null>(null)
const form = ref({ name: '', description: '' })

function formatDate(d: string | null) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('zh-CN')
}

async function fetchDatasets() {
  loading.value = true
  try {
    const res = await listDatasets({ page: page.value, size: pageSize.value })
    datasets.value = res.items
    total.value = res.total
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

function openEdit(ds: DatasetResponse) {
  editingDataset.value = ds
  form.value = { name: ds.name, description: ds.description || '' }
  showCreateModal.value = true
}

function confirmDelete(ds: DatasetResponse) {
  const hasDocs = ds.doc_count > 0
  Modal.confirm({
    title: '确认删除',
    content: hasDocs
      ? `知识库「${ds.name}」下有 ${ds.doc_count} 份文档，将一并删除。确定？`
      : `确定删除知识库「${ds.name}」？`,
    okText: '删除',
    okType: 'danger',
    onOk: async () => {
      try {
        await deleteDataset(ds.dataset_id, hasDocs)
        message.success('删除成功')
        fetchDatasets()
      } catch (e: unknown) {
        message.error((e as Error).message)
      }
    },
  })
}

async function handleSubmit() {
  if (!form.value.name.trim()) {
    message.warning('请输入名称')
    return
  }
  submitting.value = true
  try {
    if (editingDataset.value) {
      await updateDataset(editingDataset.value.dataset_id, form.value)
      message.success('更新成功')
    } else {
      await createDataset(form.value)
      message.success('创建成功')
    }
    showCreateModal.value = false
    editingDataset.value = null
    form.value = { name: '', description: '' }
    fetchDatasets()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    submitting.value = false
  }
}

onMounted(fetchDatasets)
</script>
