<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h2 class="page-title">API Key</h2>
        <p class="page-subtitle">管理用于外部系统集成访问的 API 凭证</p>
      </div>
      <a-button type="primary" @click="openCreateModal">
        <plus-outlined /> 创建 Key
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <div v-if="!loading && keys.length === 0" class="empty-state">
        <div class="empty-icon-wrap">
          <key-outlined class="empty-icon" />
        </div>
        <h3 class="empty-title">暂无 API Key</h3>
        <p class="empty-desc">创建一个 API Key，让外部系统通过 <code>Authorization: Bearer rag-ak-...</code> 调用接口</p>
      </div>

      <div v-else class="key-list">
        <div v-for="key in keys" :key="key.key_id" class="key-card">
          <div class="key-main">
            <div class="key-icon-box">
              <key-outlined />
            </div>
            <div class="key-info">
              <div class="key-name-row">
                <span class="key-name">{{ key.name || '未命名 Key' }}</span>
                <a-tag v-if="isExpired(key)" color="red" size="small">已过期</a-tag>
                <a-tag v-else color="green" size="small">有效</a-tag>
              </div>
              <div class="key-meta">
                <span class="key-prefix-badge">{{ key.key_prefix }}…</span>
                <span class="meta-divider">·</span>
                <span class="meta-text">组织 {{ key.org_id }}</span>
                <span class="meta-divider">·</span>
                <span class="meta-text">创建于 {{ formatDate(key.created_at) }}</span>
                <template v-if="key.expires_at">
                  <span class="meta-divider">·</span>
                  <span class="meta-text">有效期至 {{ formatDate(key.expires_at) }}</span>
                </template>
                <template v-if="key.last_used_at">
                  <span class="meta-divider">·</span>
                  <span class="meta-text">最后使用 {{ formatDate(key.last_used_at) }}</span>
                </template>
              </div>
            </div>
          </div>
          <div class="key-actions">
            <a-popconfirm title="确定撤销？撤销后立即失效。" @confirm="handleRevoke(key.key_id)" ok-text="撤销" cancel-text="取消">
              <a-button type="text" danger size="small">撤销</a-button>
            </a-popconfirm>
          </div>
        </div>
      </div>
    </a-spin>

    <!-- 创建 Modal -->
    <a-modal
      v-model:open="createVisible"
      title="创建 API Key"
      :confirm-loading="creating"
      @ok="handleCreate"
      centered
      width="480px"
    >
      <a-form layout="vertical">
        <a-form-item label="名称">
          <a-input v-model:value="createForm.name" placeholder="如：测试环境、外部系统 A" :maxlength="128" />
        </a-form-item>
        <a-form-item label="绑定组织" required>
          <a-select v-model:value="createForm.org_id" placeholder="选择组织">
            <a-select-option v-for="org in orgs" :key="org.org_id" :value="org.org_id">
              {{ org.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="过期时间（可选）">
          <a-input v-model:value="createForm.expires_at" placeholder="如：2026-12-31T23:59:59Z" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 创建成功展示 Modal -->
    <a-modal
      v-model:open="resultVisible"
      title="API Key 创建成功"
      :footer="null"
      centered
      width="560px"
      :closable="true"
    >
      <a-alert type="warning" show-icon style="margin-bottom: 16px">
        <template #message>
          <strong>请立即复制保存</strong>，此 Key 仅显示一次，关闭后无法再次查看。
        </template>
      </a-alert>
      <div class="result-key-box">
        <code class="result-key">{{ createdKeyRaw }}</code>
        <a-button type="text" size="small" @click="copyKey">
          <copy-outlined /> 复制
        </a-button>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { KeyOutlined, PlusOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { createApiKey, listApiKeys, revokeApiKey, type ApiKeyItem } from '@/api/apiKeys'
import { listMyOrgs, type OrgResponse } from '@/api/orgs'

const keys = ref<ApiKeyItem[]>([])
const loading = ref(false)
const orgs = ref<OrgResponse[]>([])

const createVisible = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', org_id: '', expires_at: '' })

const resultVisible = ref(false)
const createdKeyRaw = ref('')

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

function isExpired(key: ApiKeyItem): boolean {
  if (!key.expires_at) return false
  return new Date(key.expires_at) < new Date()
}

async function fetchKeys() {
  loading.value = true
  try {
    keys.value = await listApiKeys()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function fetchOrgs() {
  try {
    orgs.value = await listMyOrgs()
  } catch { /* ignore */ }
}

function openCreateModal() {
  createForm.value = { name: '', org_id: orgs.value[0]?.org_id || '', expires_at: '' }
  createVisible.value = true
}

async function handleCreate() {
  if (!createForm.value.org_id) {
    message.error('请选择组织')
    return
  }
  creating.value = true
  try {
    const res = await createApiKey({
      name: createForm.value.name || undefined,
      org_id: createForm.value.org_id,
      expires_at: createForm.value.expires_at || undefined,
    })
    createdKeyRaw.value = res.key
    createVisible.value = false
    resultVisible.value = true
    fetchKeys()
  } catch (e: unknown) {
    message.error((e as Error).message)
  } finally {
    creating.value = false
  }
}

async function handleRevoke(keyId: string) {
  try {
    await revokeApiKey(keyId)
    message.success('已撤销')
    fetchKeys()
  } catch (e: unknown) {
    message.error((e as Error).message)
  }
}

function copyKey() {
  navigator.clipboard.writeText(createdKeyRaw.value).then(() => {
    message.success('已复制到剪贴板')
  })
}

onMounted(() => {
  fetchOrgs()
  fetchKeys()
})
</script>

<style scoped>
.page-container {
  padding: var(--space-8) var(--space-6);
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-8);
}

.page-title {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.page-subtitle {
  font-size: var(--font-size-sm);
  color: var(--color-text-tertiary);
  margin-top: var(--space-1);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.empty-icon-wrap {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-lg);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-5);
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
  max-width: 400px;
}

.empty-desc code {
  background: var(--color-bg-sunken);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  color: var(--color-primary);
}

/* Key List */
.key-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.key-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  transition: all var(--transition-fast);
}

.key-card:hover {
  border-color: var(--color-primary-border);
  box-shadow: var(--shadow-sm);
}

.key-main {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  flex: 1;
  min-width: 0;
}

.key-icon-box {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--color-primary);
  flex-shrink: 0;
}

.key-info {
  min-width: 0;
}

.key-name-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: 2px;
}

.key-name {
  font-size: var(--font-size-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.key-meta {
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
}

.key-prefix-badge {
  display: inline-block;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px;
  background: var(--color-bg-sunken);
  padding: 1px 8px;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
}

.meta-divider {
  color: var(--color-text-quaternary);
  margin: 0 var(--space-2);
  font-size: 11px;
}

.meta-text {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

/* Result Modal */
.result-key-box {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  background: var(--color-bg-sunken);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.result-key {
  flex: 1;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: var(--font-size-xs);
  color: var(--color-text-primary);
  word-break: break-all;
}
</style>
