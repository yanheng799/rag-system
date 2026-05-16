<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">知识库管理</h2>
      <a-button type="primary" @click="showCreateModal = true">
        <plus-outlined /> 新建知识库
      </a-button>
    </div>

    <a-row v-if="loading" :gutter="[16, 16]">
      <a-col v-for="i in 4" :key="i" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card><a-skeleton active :paragraph="{ rows: 2 }" /></a-card>
      </a-col>
    </a-row>

    <a-row v-else :gutter="[16, 16]">
      <a-col v-for="ds in datasets" :key="ds.dataset_id" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card hoverable>
          <router-link :to="`/datasets/${ds.dataset_id}`" class="card-link" aria-label="打开知识库"></router-link>
          <template #actions>
            <a-tooltip title="问答"><router-link :to="{ path: '/query', query: { dataset_ids: ds.dataset_id } }" aria-label="问答"><message-outlined /></router-link></a-tooltip>
            <a-tooltip title="检索"><router-link :to="{ path: '/retrieve', query: { dataset_ids: ds.dataset_id } }" aria-label="检索"><search-outlined /></router-link></a-tooltip>
            <a-tooltip title="编辑"><span role="button" tabindex="0" aria-label="编辑" @click.stop="openEdit(ds)" @keydown.enter="openEdit(ds)"><edit-outlined /></span></a-tooltip>
            <a-tooltip title="删除"><span role="button" tabindex="0" aria-label="删除" @click.stop="confirmDelete(ds)" @keydown.enter="confirmDelete(ds)"><delete-outlined /></span></a-tooltip>
          </template>
          <a-card-meta :title="ds.name">
            <template #description>
              <div>{{ ds.description || '暂无描述' }}</div>
              <div style="margin-top: var(--space-2); color: var(--color-text-tertiary); font-size: var(--font-size-xs)">
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
      <a-form layout="vertical" :model="form" :rules="formRules" ref="formRef">
        <a-form-item label="名称" name="name">
          <a-input v-model:value="form.name" :maxlength="256" placeholder="请输入知识库名称…" name="name" autocomplete="off" />
        </a-form-item>
        <a-form-item label="描述" name="description">
          <a-textarea v-model:value="form.description" :rows="3" placeholder="可选描述…" name="description" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, MessageOutlined, SearchOutlined } from '@ant-design/icons-vue'
import {
  listDatasets,
  createDataset,
  updateDataset,
  deleteDataset,
  type DatasetResponse,
} from '@/api/datasets'

const datasets = ref<DatasetResponse[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(12)
const total = ref(0)

const showCreateModal = ref(false)
const submitting = ref(false)
const editingDataset = ref<DatasetResponse | null>(null)
const form = ref({ name: '', description: '' })
const formRef = ref()

const formRules = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
}

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
  try {
    await formRef.value?.validateFields()
  } catch {
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

<style scoped>
.card-link {
  position: absolute;
  inset: 0;
  z-index: 1;
}

:deep(.ant-card) {
  position: relative;
}

:deep(.ant-card-actions) {
  position: relative;
  z-index: 2;
}
</style>
