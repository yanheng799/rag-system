<template>
  <div class="org-page">
    <div class="page-header">
      <h2>组织管理</h2>
      <a-button type="primary" @click="showCreate = true">创建组织</a-button>
    </div>

    <!-- 我的组织 -->
    <a-spin :spinning="loadingOrgs">
      <div v-if="myOrgs.length" class="org-grid">
        <a-card
          v-for="org in myOrgs"
          :key="org.org_id"
          hoverable
          class="org-card"
          :class="{ active: org.org_id === authStore.currentOrgId }"
          @click="handleSwitchOrg(org.org_id)"
        >
          <template #title>
            <span>{{ org.name }}</span>
            <a-tag v-if="org.org_id === authStore.currentOrgId" color="blue" style="margin-left:8px">当前</a-tag>
          </template>
          <template #extra>
            <a-tag :color="org.role === 'admin' ? 'purple' : 'default'">{{ org.role === 'admin' ? '管理员' : '成员' }}</a-tag>
          </template>
          <p class="org-desc">{{ org.description || '暂无描述' }}</p>
          <template #actions>
            <router-link :to="`/orgs/${org.org_id}`">管理</router-link>
          </template>
        </a-card>
      </div>
      <a-empty v-else description="暂未加入任何组织" />
    </a-spin>

    <!-- 待处理邀请 -->
    <div v-if="invitations.length" class="invitations-section">
      <h3>待处理的邀请</h3>
      <a-list :dataSource="invitations">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>{{ item.org_name }}</template>
              <template #description>
                邀请时间: {{ item.created_at ? new Date(item.created_at).toLocaleDateString() : '-' }}
                <a-tag v-if="item.expired" color="red">已过期</a-tag>
              </template>
            </a-list-item-meta>
            <template #actions>
              <template v-if="!item.expired">
                <a-button type="primary" size="small" @click="handleAccept(item.invitation_id)">接受</a-button>
                <a-button size="small" @click="handleReject(item.invitation_id)">拒绝</a-button>
              </template>
              <span v-else class="expired-text">已过期</span>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </div>

    <!-- 创建组织 Modal -->
    <a-modal v-model:open="showCreate" title="创建组织" @ok="handleCreate" :confirmLoading="creating">
      <a-form :model="createForm" layout="vertical">
        <a-form-item label="组织名称" required>
          <a-input v-model:value="createForm.name" placeholder="输入组织名称" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="createForm.description" placeholder="组织描述（可选）" :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { createOrg } from '@/api/orgs'
import { getMyInvitations, acceptInvitation, rejectInvitation } from '@/api/auth'

const authStore = useAuthStore()
const loadingOrgs = ref(false)
const creating = ref(false)
const showCreate = ref(false)
const invitations = ref<any[]>([])

const myOrgs = computed(() => authStore.myOrgs)

const createForm = ref({ name: '', description: '' })

async function loadOrgs() {
  loadingOrgs.value = true
  try {
    await authStore.fetchUser()
    invitations.value = await getMyInvitations()
  } finally {
    loadingOrgs.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    message.warning('请输入组织名称')
    return
  }
  creating.value = true
  try {
    await createOrg({ name: createForm.value.name, description: createForm.value.description || undefined })
    message.success('组织创建成功')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await authStore.fetchUser()
  } catch (err: any) {
    message.error(err.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function handleSwitchOrg(orgId: string) {
  try {
    await authStore.switchOrg(orgId)
    message.success('已切换到 ' + authStore.currentOrg?.name)
  } catch (err: any) {
    message.error(err.message || '切换失败')
  }
}

async function handleAccept(invId: string) {
  try {
    await acceptInvitation(invId)
    message.success('已加入组织')
    await authStore.fetchUser()
    invitations.value = await getMyInvitations()
  } catch (err: any) {
    message.error(err.message || '操作失败')
  }
}

async function handleReject(invId: string) {
  try {
    await rejectInvitation(invId)
    message.success('已拒绝邀请')
    invitations.value = await getMyInvitations()
  } catch (err: any) {
    message.error(err.message || '操作失败')
  }
}

onMounted(loadOrgs)
</script>

<style scoped>
.org-page {
  max-width: 900px;
  margin: 0 auto;
  padding: var(--space-6);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-6);
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.org-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}

.org-card {
  border-radius: var(--radius-lg);
}

.org-card.active {
  border-color: #312e81;
  box-shadow: 0 0 0 2px rgba(49, 46, 129, 0.15);
}

.org-desc {
  color: #6b7280;
  margin: 0;
  font-size: 14px;
}

.invitations-section {
  margin-top: var(--space-8);
}

.invitations-section h3 {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: var(--space-4);
}

.expired-text {
  color: #9ca3af;
  font-size: 13px;
}
</style>
