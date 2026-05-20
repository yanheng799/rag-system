<template>
  <div class="detail-page">
    <div class="page-header">
      <a-button type="text" @click="$router.push('/orgs')"><ArrowLeftOutlined /> 返回</a-button>
      <h2 v-if="org">{{ org.name }}</h2>
    </div>
    <a-spin :spinning="loading" v-if="org">
      <a-row :gutter="24">
        <a-col :span="8">
          <a-card title="组织信息">
            <template #extra><a-button v-if="org.role === 'admin'" size="small" @click="showEdit = true">编辑</a-button></template>
            <p><strong>描述:</strong> {{ org.description || '暂无描述' }}</p>
            <p><strong>角色:</strong> {{ org.role === 'admin' ? '管理员' : '成员' }}</p>
          </a-card>
          <a-card v-if="org.role === 'admin'" title="邀请成员" style="margin-top:16px">
            <a-input-search v-model:value="inviteUser" placeholder="用户名" enter-button="邀请" :loading="inviting" @search="handleInvite" />
          </a-card>
        </a-col>
        <a-col :span="16">
          <a-card title="成员列表">
            <a-table :dataSource="members" :pagination="false" rowKey="user_id" size="middle">
              <a-table-column title="用户" key="username">
                <template #default="{ record }">{{ record.username }}<span v-if="record.display_name" class="dim"> ({{ record.display_name }})</span></template>
              </a-table-column>
              <a-table-column title="角色" key="role" width="100">
                <template #default="{ record }"><a-tag :color="record.role==='admin'?'purple':'default'">{{ record.role==='admin'?'管理员':'成员' }}</a-tag></template>
              </a-table-column>
              <a-table-column title="加入" key="joined" width="120">
                <template #default="{ record }">{{ record.joined_at ? new Date(record.joined_at).toLocaleDateString() : '-' }}</template>
              </a-table-column>
              <a-table-column key="actions" width="80">
                <template #default="{ record }">
                  <template v-if="org.role==='admin' && record.user_id!==authStore.user?.user_id">
                    <a-dropdown>
                      <a-button size="small" type="text">操作</a-button>
                      <template #overlay>
                        <a-menu>
                          <a-menu-item @click="handleRole(record)">{{ record.role==='admin'?'降为成员':'升为管理员' }}</a-menu-item>
                          <a-menu-item danger @click="handleRemove(record)">移除</a-menu-item>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </template>
                  <span v-else-if="record.user_id===authStore.user?.user_id" class="dim">我</span>
                </template>
              </a-table-column>
            </a-table>
          </a-card>
          <a-button danger style="margin-top:16px" @click="handleLeave" :loading="leaving">退出组织</a-button>
        </a-col>
      </a-row>
    </a-spin>
    <a-modal v-model:open="showEdit" title="编辑" @ok="handleUpdate" :confirmLoading="updating">
      <a-form layout="vertical">
        <a-form-item label="名称"><a-input v-model:value="editName" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="editDesc" :rows="3" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { getOrg, updateOrg, listMembers, inviteMember, changeMemberRole, removeMember, leaveOrg } from '@/api/orgs'
import { useAuthStore } from '@/stores/auth'
import type { OrgResponse, MemberResponse } from '@/api/orgs'

const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const orgId = route.params.id as string
const loading = ref(true); const org = ref<OrgResponse | null>(null); const members = ref<MemberResponse[]>([])
const inviteUser = ref(''); const inviting = ref(false); const leaving = ref(false)
const showEdit = ref(false); const updating = ref(false); const editName = ref(''); const editDesc = ref('')

async function load() {
  loading.value = true
  try {
    const [o, ms] = await Promise.all([getOrg(orgId), listMembers(orgId)])
    org.value = o; members.value = ms; editName.value = o.name; editDesc.value = o.description || ''
  } catch (err: any) { message.error(err.message); router.push('/orgs') }
  finally { loading.value = false }
}

async function handleInvite() {
  if (!inviteUser.value.trim()) return
  inviting.value = true
  try { await inviteMember(orgId, { username: inviteUser.value.trim() }); message.success('已发送'); inviteUser.value = '' }
  catch (err: any) { message.error(err.message) }
  finally { inviting.value = false }
}

async function handleRole(m: MemberResponse) {
  const r = m.role === 'admin' ? 'member' : 'admin'
  try { const u = await changeMemberRole(orgId, m.user_id, { role: r }); const i = members.value.findIndex(x => x.user_id === m.user_id); if (i>=0) members.value[i] = u; message.success('已更新') }
  catch (err: any) { message.error(err.message) }
}

function handleRemove(m: MemberResponse) {
  Modal.confirm({ title: '移除', content: `移除 ${m.username}？`, okText: '移除', okType: 'danger', cancelText: '取消',
    async onOk() { try { await removeMember(orgId, m.user_id); members.value = members.value.filter(x => x.user_id !== m.user_id); message.success('已移除') } catch (err: any) { message.error(err.message) } }
  })
}

function handleLeave() {
  Modal.confirm({ title: '退出', content: '确定退出？', okText: '退出', okType: 'danger', cancelText: '取消',
    async onOk() { leaving.value = true; try { await leaveOrg(orgId); message.success('已退出'); router.push('/orgs') } catch (err: any) { message.error(err.message) } finally { leaving.value = false } }
  })
}

async function handleUpdate() {
  updating.value = true
  try { const u = await updateOrg(orgId, { name: editName.value, description: editDesc.value }); org.value = u; showEdit.value = false; message.success('已更新') }
  catch (err: any) { message.error(err.message) }
  finally { updating.value = false }
}

onMounted(load)
</script>

<style scoped>
.detail-page { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
.page-header { display: flex; align-items: center; gap: var(--space-4); margin-bottom: var(--space-6); }
.page-header h2 { margin: 0; font-size: 22px; }
.dim { color: #9ca3af; font-size: 13px; }
</style>
