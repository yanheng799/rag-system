<template>
  <a-layout style="min-height: 100vh">
    <header class="app-header">
      <router-link to="/datasets" class="header-brand">
        <svg class="brand-icon" viewBox="0 0 32 32" fill="none"><rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.15)"/><path d="M9 7h7.2c2.8 0 5 1.4 5 4.2 0 1.8-1 3.2-2.6 3.9l3.4 9.9h-3.8l-3-7.6H12.2V25H9V7zm3.2 2.8v4.6h3.2c1.6 0 2.6-.9 2.6-2.3s-1-2.3-2.6-2.3h-3.2z" fill="white"/><circle cx="24" cy="8" r="3" fill="#f59e0b"/></svg>
        <span class="brand-text">RAG 系统</span>
      </router-link>
      <nav class="header-nav">
        <router-link v-for="item in navItems" :key="item.key" :to="item.to" class="nav-item" :class="{ active: currentNav === item.key }">
          <component :is="item.icon" class="nav-icon" /><span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="header-right">
        <a-select
          v-if="authStore.myOrgs.length"
          :value="authStore.currentOrgId"
          size="small"
          class="org-switcher"
          :options="authStore.myOrgs.map((o: any) => ({ value: o.org_id, label: o.name }))"
          @change="handleSwitchOrg"
        />
        <a-dropdown :trigger="['click']">
          <a-button type="text" class="user-btn"><UserOutlined /><span class="user-name">{{ authStore.user?.display_name || authStore.user?.username || '用户' }}</span><DownOutlined class="arrow" /></a-button>
          <template #overlay>
            <a-menu @click="handleMenu">
              <a-menu-item key="orgs"><TeamOutlined /> 组织管理<a-badge v-if="pendingCount" :count="pendingCount" size="small" style="margin-left:8px" /></a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" danger><LogoutOutlined /> 退出登录</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </header>
    <a-alert
      v-if="pendingCount > 0 && route.path !== '/orgs'"
      type="info"
      show-icon
      :message="`您有 ${pendingCount} 个待处理的组织邀请`"
      style="margin: 16px 24px 0; border-radius: 8px"
    >
      <template #action>
        <a-button size="small" type="primary" @click="router.push('/orgs')">查看邀请</a-button>
      </template>
    </a-alert>
    <a-layout-content><router-view /></a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DatabaseOutlined, MessageOutlined, SearchOutlined, UserOutlined, DownOutlined, TeamOutlined, LogoutOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { getMyInvitations } from '@/api/auth'

const route = useRoute(); const router = useRouter(); const authStore = useAuthStore()
const pendingCount = ref(0)

async function refreshPendingCount() {
  try {
    const invs = await getMyInvitations()
    pendingCount.value = invs.filter(i => i.status === 'pending' && !i.expired).length
  } catch { /* ignore */ }
}
const navItems = [
  { key: 'datasets', to: '/datasets', label: '知识库', icon: DatabaseOutlined },
  { key: 'query', to: '/query', label: '问答', icon: MessageOutlined },
  { key: 'retrieve', to: '/retrieve', label: '检索', icon: SearchOutlined },
]
const currentNav = computed(() => {
  const p = route.path
  if (p.startsWith('/query')) return 'query'
  if (p.startsWith('/retrieve')) return 'retrieve'
  return 'datasets'
})
async function handleSwitchOrg(orgId: string) {
  try { await authStore.switchOrg(orgId); message.success('已切换') }
  catch (err: any) { message.error(err.message) }
}
function handleMenu({ key }: { key: string }) {
  if (key === 'orgs') router.push('/orgs')
  else if (key === 'logout') { authStore.logout(); router.push('/login') }
}
onMounted(async () => {
  try { await authStore.fetchUser() }
  catch { authStore.logout(); router.push('/login') }
  await refreshPendingCount()
})
watch(() => route.path, () => refreshPendingCount())
</script>

<style scoped>
.app-header { display: flex; align-items: center; height: 60px; background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 0 24px; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 12px rgba(30,27,75,0.2); }
.header-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; margin-right: 40px; }
.brand-icon { width: 32px; height: 32px; flex-shrink: 0; }
.brand-text { font-size: 17px; font-weight: 700; color: #fff; white-space: nowrap; }
.header-nav { display: flex; align-items: center; gap: 4px; }
.nav-item { display: flex; align-items: center; gap: 8px; padding: 6px 16px; border-radius: 8px; color: #a5b4fc; text-decoration: none; font-size: 14px; font-weight: 500; transition: all 0.15s; white-space: nowrap; }
.nav-item:hover { color: #e0e7ff; background: rgba(255,255,255,0.08); }
.nav-item.active { color: #fff; background: rgba(255,255,255,0.14); }
.nav-icon { font-size: 16px; }
.header-right { margin-left: auto; display: flex; align-items: center; gap: 16px; }
.org-switcher { width: 160px; }
.user-btn { color: #e0e7ff; display: flex; align-items: center; gap: 8px; }
.user-btn:hover { color: #fff; background: rgba(255,255,255,0.1); }
.user-name { max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.arrow { font-size: 10px; }
@media (max-width: 768px) { .app-header { padding: 0 16px; } .nav-item span { display: none; } .user-name { display: none; } }
</style>
