<template>
  <div class="org-detail-page">
    <div class="page-header">
      <a-button type="text" @click="$router.push('/orgs')">
        <ArrowLeftOutlined /> 返回
      </a-button>
      <h2 v-if="org">{{ org.name }}</h2>
    </div>

    <a-spin :spinning="loading">
      <a-row :gutter="24" v-if="org">
        <!-- 组织信息 -->
        <a-col :span="8">
          <a-card title="组织信息">
            <template #extra>
              <a-button v-if="org.role === 'admin'" size="small" @click="showEdit = true">编辑</a-button>
            </template>
            <p><strong>描述:</strong> {{ org.description || '暂无描述' }}</p>
            <p><strong>我的角色:</strong> {{ org.role === 'admin' ? '管理员' : '成员' }}</p>
            <p><strong>创建时间:</strong> {{ org.created_at ? new Date(org.created_at).toLocaleDateString() : '-' }}</p>
          </a-card>
          <a-card title="邀请成员" v-if="org.role === 'admin'" style="margin-top:16px">
            <a-input-search
              v-model:value="inviteUsername"
              placeholder="输入用户名"
              enter-button="邀请"
              :loading="inviting"
              @search="handleInvite"
            />
          </a-card>
        </a-col>

        <!-- 成员列表 -->
        <a-col :span="16">
          <a-card title="成员列表">
            <a-table
              :dataSource="members"
              :columns="columns"
              :pagination="false"
              rowKey="user_id"
              size="middle"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'username'">
                  <span>{{ record.username }}</span>
                  <span v-if="record.display_name" class="display-name">({{ record.display_name }})</span>
                </template>
                <template v-if="column.key === 'role'">
                  <a-tag :color="record.role === 'admin' ? 'purple' : 'default'">
                    {{ record.role === 'admin' ? '管理员' : '成员' }}
                  </a-tag>
                </template>
                <template v-if="column.key === 'joined_at'">
                  {{ record.joined_at ? new Date(record.joined_at).toLocaleDateString() : '-' }}
                </template>
                <template v-if="column.key === 'actions'">
                  <template v-if="org.role === 'admin' && record.user_id !== authStore.user?.user_id">
                    <a-dropdown>
                      <a-button size="small" type="text">操作</a-button>
                      <template #overlay>
                        <a-menu>
                          <a-menu-item @click="handleChangeRole(record)">
                            {{ record.role === 'admin' ? '降为成员' : '升为管理员' }}
                          </a-menu-item>
                          <a-menu-item danger @click="handleRemove(record)">移除成员</a-menu-item>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </template>
                  <span v-else-if="record.user_id === authStore.user?.user_id" class="text-muted">我</span>
                </template>
              </template>
            </a-table>
          </a-card>
          <!-- 退出组织 -->
          <a-button
            danger
            style="margin-top:16px"
            @click="handleLeave"
            :loading="leaving"
          >
            退出组织
          </a-button>
        </a-col>
      </a-row>
    </a-spin>

    <!-- 编辑 Modal -->
    <a-modal v-model:open="showEdit" title="编辑组织" @ok="handleUpdate" :confirmLoading="updating">
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
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { getOrg, updateOrg, listMembers, inviteMember, changeMemberRole, removeMember, leaveOrg } from '@/api/orgs'
import { useAuthStore } from '@/stores/auth'
import type { OrgResponse, MemberResponse } from '@/api/orgs'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const orgId = route.params.id as string

const loading = ref(true)
const org = ref<OrgResponse | null>(null)
const members = ref<MemberResponse[]>([])
const inviteUsername = ref('')
const inviting = ref(false)
const leaving = ref(false)
const showEdit = ref(false)
const updating = ref(false)
const editForm = ref({ name: '', description: '' })

const columns = [
  { title: '用户', key: 'username' },
  { title: '角色', key: 'role', width: 100 },
  { title: '加入时间', key: 'joined_at', width: 140 },
  { title: '', key: 'actions', width: 80 },
]

async function load() {
  loading.value = true
  try {
    const [orgData, membersData] = await Promise.all([
      getOrg(orgId),
      listMembers(orgId),
    ])
    org.value = orgData
    members.value = membersData
    editForm.value = { name: orgData.name, description: orgData.description || '' }
  } catch (err: any) {
    message.error(err.message || '加载失败')
    router.push('/orgs')
  } finally {
    loading.value = false
  }
}

async function handleInvite() {
  if (!inviteUsername.value.trim()) return
  inviting.value = true
  try {
    await inviteMember(orgId, { username: inviteUsername.value.trim() })
    message.success('邀请已发送')
    inviteUsername.value = ''
  } catch (err: any) {
    message.error(err.message || '邀请失败')
  } finally {
    inviting.value = false
  }
}

async function handleChangeRole(member: MemberResponse) {
  const newRole = member.role === 'admin' ? 'member' : 'admin'
  try {
    const updated = await changeMemberRole(orgId, member.user_id, { role: newRole })
    const idx = members.value.findIndex((m: MemberResponse) => m.user_id === member.user_id)
    if (idx >= 0) members.value[idx] = updated
    message.success('角色已更新')
  } catch (err: any) {
    message.error(err.message || '操作失败')
  }
}

function handleRemove(member: MemberResponse) {
  Modal.confirm({
    title: '移除成员',
    content: `确定要移除 ${member.username} 吗？`,
    okText: '移除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        await removeMember(orgId, member.user_id)
        members.value = members.value.filter((m: MemberResponse) => m.user_id !== member.user_id)
        message.success('已移除')
      } catch (err: any) {
        message.error(err.message || '操作失败')
      }
    },
  })
}

async function handleLeave() {
  Modal.confirm({
    title: '退出组织',
    content: '确定要退出该组织吗？',
    okText: '退出',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      leaving.value = true
      try {
        await leaveOrg(orgId)
        message.success('已退出组织')
        router.push('/orgs')
      } catch (err: any) {
        message.error(err.message || '退出失败')
      } finally {
        leaving.value = false
      }
    },
  })
}

async function handleUpdate() {
  updating.value = true
  try {
    const updated = await updateOrg(orgId, {
      name: editForm.value.name,
      description: editForm.value.description,
    })
    org.value = updated
    showEdit.value = false
    message.success('已更新')
  } catch (err: any) {
    message.error(err.message || '更新失败')
  } finally {
    updating.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.org-detail-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-6);
}

.page-header {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

.page-header h2 {
  margin: 0;
  font-size: 22px;
}

.display-name {
  color: #9ca3af;
  font-size: 13px;
  margin-left: 4px;
}

.text-muted {
  color: #9ca3af;
  font-size: 13px;
}
</style>
