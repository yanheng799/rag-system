<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">知识库管理</h2>
        <p class="page-subtitle">管理文档集合，配置解析策略</p>
      </div>
      <a-button type="primary" size="large" @click="showCreateModal = true" class="create-btn">
        <plus-outlined /> 新建知识库
      </a-button>
    </div>

    <a-row v-if="loading" :gutter="[20, 20]">
      <a-col v-for="i in 4" :key="i" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card class="ds-card"><a-skeleton active :paragraph="{ rows: 2 }" /></a-card>
      </a-col>
    </a-row>

    <a-row v-else :gutter="[20, 20]">
      <a-col v-for="ds in datasets" :key="ds.dataset_id" :xs="24" :sm="12" :md="8" :lg="6">
        <a-card hoverable class="ds-card">
          <router-link :to="`/datasets/${ds.dataset_id}`" class="card-link" aria-label="打开知识库"></router-link>
          <div class="card-visual">
            <div class="card-icon-wrap">
              <database-outlined class="card-icon" />
            </div>
          </div>
          <a-card-meta>
            <template #title>
              <span class="card-title">{{ ds.name }}</span>
            </template>
            <template #description>
              <div class="card-desc">{{ ds.description || '暂无描述' }}</div>
              <div class="card-meta">
                <span class="meta-item">
                  <file-text-outlined /> {{ ds.doc_count }} 份文档
                </span>
                <span class="meta-divider">·</span>
                <span class="meta-item">{{ formatDate(ds.created_at) }}</span>
              </div>
            </template>
          </a-card-meta>
          <template #actions>
            <a-tooltip title="问答"><router-link :to="{ path: '/query', query: { dataset_ids: ds.dataset_id } }" aria-label="问答" class="action-link"><message-outlined /></router-link></a-tooltip>
            <a-tooltip title="检索"><router-link :to="{ path: '/retrieve', query: { dataset_ids: ds.dataset_id } }" aria-label="检索" class="action-link"><search-outlined /></router-link></a-tooltip>
            <a-tooltip title="编辑"><span role="button" tabindex="0" aria-label="编辑" @click.stop="openEdit(ds)" @keydown.enter="openEdit(ds)" class="action-link"><edit-outlined /></span></a-tooltip>
            <a-tooltip title="删除"><span role="button" tabindex="0" aria-label="删除" @click.stop="confirmDelete(ds)" @keydown.enter="confirmDelete(ds)" class="action-link action-danger"><delete-outlined /></span></a-tooltip>
          </template>
        </a-card>
      </a-col>
    </a-row>

    <div v-if="!loading && datasets.length === 0" class="empty-state">
      <div class="empty-icon-wrap">
        <database-outlined class="empty-icon" />
      </div>
      <p class="empty-title">暂无知识库</p>
      <p class="empty-desc">点击右上角按钮创建第一个知识库</p>
    </div>

    <div v-if="total > pageSize" class="pagination-wrap">
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
      :ok-text="editingDataset ? '保存' : '创建'"
      centered
    >
      <a-form layout="vertical" :model="form" :rules="formRules" ref="formRef" style="margin-top: 16px">
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
import { ref, onMounted } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { PlusOutlined, EditOutlined, DeleteOutlined, MessageOutlined, SearchOutlined, DatabaseOutlined, FileTextOutlined } from '@ant-design/icons-vue'
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
.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
}

.create-btn {
  border-radius: var(--radius-md);
  font-weight: 600;
}

.ds-card {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg) !important;
  transition: all var(--transition-normal);
  overflow: hidden;
}

.ds-card:hover {
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.card-link {
  position: absolute;
  inset: 0;
  z-index: 1;
}

:deep(.ant-card-actions) {
  position: relative;
  z-index: 2;
  border-top-color: var(--color-border);
}

:deep(.ant-card-body) {
  padding: var(--space-5);
}

.card-visual {
  margin-bottom: var(--space-4);
}

.card-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-icon {
  font-size: 22px;
  color: var(--color-primary);
}

.card-title {
  font-weight: 600;
  font-size: var(--font-size-lg);
  color: var(--color-text-primary);
}

.card-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.action-link {
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: color var(--transition-fast);
  font-size: 16px;
}

.action-link:hover {
  color: var(--color-primary);
}

.action-danger:hover {
  color: var(--color-error) !important;
}

.empty-state {
  text-align: center;
  padding: var(--space-12) var(--space-6);
}

.empty-icon-wrap {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-xl);
  background: var(--color-primary-bg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-4);
}

.empty-icon {
  font-size: 28px;
  color: var(--color-primary);
}

.empty-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.empty-desc {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
}

.pagination-wrap {
  text-align: center;
  margin-top: var(--space-8);
}
</style>
