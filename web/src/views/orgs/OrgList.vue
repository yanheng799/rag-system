<template>
  <div class="org-page">
    <div class="page-header">
      <h2>组织管理</h2>
      <a-button type="primary" @click="showCreate = true">创建组织</a-button>
    </div>

    <!-- 邀请优先展示 -->
    <a-alert
      v-if="invitations.length"
      type="info"
      show-icon
      :message="`您有 ${invitations.length} 个待处理的组织邀请`"
      style="margin-bottom: 20px"
    />
    <div v-if="invitations.length" class="inv-section">
      <h3>待处理的邀请</h3>
      <a-list :dataSource="invitations">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>{{ item.org_name }}</template>
              <template #description>
                {{ item.created_at ? new Date(item.created_at).toLocaleDateString() : '-' }}
                <a-tag v-if="item.expired" color="red">已过期</a-tag>
              </template>
            </a-list-item-meta>
            <template #actions>
              <template v-if="!item.expired">
                <a-button type="primary" size="small" @click="handleAccept(item.invitation_id)">接受</a-button>
                <a-button size="small" @click="handleReject(item.invitation_id)">拒绝</a-button>
              </template>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </div>

    <a-spin :spinning="loading">
      <div v-if="myOrgs.length" class="org-grid">
        <a-card v-for="org in myOrgs" :key="org.org_id" hoverable class="org-card" :class="{ active: org.org_id === authStore.currentOrgId }" @click="handleSwitch(org.org_id)">
          <template #title>
            <span>{{ org.name }}</span>
            <a-tag v-if="org.org_id === authStore.currentOrgId" color="blue" style="margin-left:8px">当前</a-tag>
          </template>
          <template #extra><a-tag :color="org.role === 'admin' ? 'purple' : 'default'">{{ org.role === 'admin' ? '管理员' : '成员' }}</a-tag></template>
          <p class="org-desc">{{ org.description || '暂无描述' }}</p>
          <template #actions><router-link :to="`/orgs/${org.org_id}`">管理</router-link></template>
        </a-card>
      </div>
      <a-empty v-else description="暂未加入任何组织" />
    </a-spin>

    <a-modal v-model:open="showCreate" title="创建组织" @ok="handleCreate" :confirmLoading="creating">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="createName" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="createDesc" :rows="3" /></a-form-item>
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
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createName = ref('')
const createDesc = ref('')
const invitations = ref<any[]>([])
const myOrgs = computed(() => authStore.myOrgs)

async function load() {
  loading.value = true
  try {
    await authStore.fetchUser()
  } catch { /* fetchUser 失败不阻塞邀请加载 */ }
  try {
    invitations.value = await getMyInvitations()
  } catch { /* ignore */ }
  loading.value = false
}

async function handleCreate() {
  if (!createName.value.trim()) { message.warning('请输入名称'); return }
  creating.value = true
  try {
    await createOrg({ name: createName.value, description: createDesc.value || undefined })
    message.success('创建成功')
    showCreate.value = false; createName.value = ''; createDesc.value = ''
    await authStore.fetchUser()
  } catch (err: any) { message.error(err.message || '创建失败') }
  finally { creating.value = false }
}

async function handleSwitch(orgId: string) {
  try { await authStore.switchOrg(orgId); message.success('已切换') }
  catch (err: any) { message.error(err.message || '切换失败') }
}

async function handleAccept(id: string) {
  try { await acceptInvitation(id); message.success('已加入'); await authStore.fetchUser(); invitations.value = await getMyInvitations() }
  catch (err: any) { message.error(err.message) }
}

async function handleReject(id: string) {
  try { await rejectInvitation(id); message.success('已拒绝'); invitations.value = await getMyInvitations() }
  catch (err: any) { message.error(err.message) }
}

onMounted(load)
</script>

<style scoped>
.org-page { max-width: 900px; margin: 0 auto; padding: var(--space-6); }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-6); }
.page-header h2 { margin: 0; font-size: 22px; }
.org-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); }
.org-card.active { border-color: #312e81; box-shadow: 0 0 0 2px rgba(49,46,129,0.15); }
.org-desc { color: #6b7280; margin: 0; font-size: 14px; }
.inv-section { margin-top: var(--space-8); }
.inv-section h3 { font-size: 18px; margin-bottom: var(--space-4); }
</style>
