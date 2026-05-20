import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getMe, switchOrg as switchOrgApi } from '@/api/auth'
import type { UserResponse } from '@/api/auth'
import { listMyOrgs } from '@/api/orgs'
import type { OrgResponse } from '@/api/orgs'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const user = ref<UserResponse | null>(null)
  const myOrgs = ref<OrgResponse[]>([])
  const currentOrgId = ref<string>(localStorage.getItem('current_org_id') || '')

  const isLoggedIn = computed(() => !!token.value)
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
    try {
      user.value = await getMe()
      myOrgs.value = await listMyOrgs()
      // 自动选择第一个组织（如果没有已选组织或已选组织不在列表中）
      if (myOrgs.value.length > 0) {
        const found = myOrgs.value.find((o: OrgResponse) => o.org_id === currentOrgId.value)
        if (!found) {
          setCurrentOrg(myOrgs.value[0].org_id)
        }
      }
    } catch {
      logout()
      throw new Error('获取用户信息失败')
    }
  }

  async function switchOrg(orgId: string) {
    const resp = await switchOrgApi(orgId)
    setToken(resp.access_token)
    setCurrentOrg(orgId)
    await fetchUser()
  }

  function logout() {
    token.value = ''
    user.value = null
    myOrgs.value = []
    currentOrgId.value = ''
    localStorage.removeItem('access_token')
    localStorage.removeItem('current_org_id')
  }

  return {
    token, user, myOrgs, currentOrgId, currentOrg, isLoggedIn, isAdmin,
    setToken, setCurrentOrg, fetchUser, switchOrg, logout,
  }
})
