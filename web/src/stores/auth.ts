import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, switchOrg as switchOrgApi } from '@/api/auth'
import type { UserResponse } from '@/api/auth'
import { listMyOrgs } from '@/api/orgs'
import type { OrgResponse } from '@/api/orgs'

function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    if (payload.exp) return Date.now() / 1000 > payload.exp
    return false
  } catch { return false }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const user = ref<UserResponse | null>(null)
  const myOrgs = ref<OrgResponse[]>([])
  const currentOrgId = ref(localStorage.getItem('current_org_id') || '')

  const isLoggedIn = computed(() => token.value && !isTokenExpired(token.value))
  const currentOrg = computed(() => myOrgs.value.find((o: OrgResponse) => o.org_id === currentOrgId.value))
  const isAdmin = computed(() => currentOrg.value?.role === 'admin')

  function setToken(t: string) {
    token.value = t
    localStorage.setItem('access_token', t)
  }

  function setCurrentOrg(orgId: string) {
    currentOrgId.value = orgId
    localStorage.setItem('current_org_id', orgId)
  }

  async function fetchUser() {
    user.value = await getMe()
    const orgs = await listMyOrgs()
    myOrgs.value = orgs
    if (orgs.length > 0) {
      const found = orgs.find((o) => o.org_id === currentOrgId.value)
      if (!found) {
        // 自动切换到第一个组织，获取含 org_id 的有效 token
        const resp = await switchOrgApi(orgs[0].org_id)
        setToken(resp.access_token)
        setCurrentOrg(orgs[0].org_id)
        // 用新 token 刷新用户信息
        user.value = await getMe()
        myOrgs.value = await listMyOrgs()
      }
    }
  }

  async function switchOrg(orgId: string) {
    const resp = await switchOrgApi(orgId)
    setToken(resp.access_token)
    setCurrentOrg(orgId)
    await fetchUser()
  }

  function logout() {
    token.value = ''; user.value = null; myOrgs.value = []; currentOrgId.value = ''
    localStorage.removeItem('access_token'); localStorage.removeItem('current_org_id')
  }

  return { token, user, myOrgs, currentOrgId, currentOrg, isLoggedIn, isAdmin,
    setToken, setCurrentOrg, fetchUser, switchOrg, logout }
})
