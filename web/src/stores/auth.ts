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
    const resp = await getMe()
    user.value = resp
    const orgs = await listMyOrgs()
    myOrgs.value = orgs
    if (orgs.length > 0) {
      const found = orgs.find((o) => o.org_id === currentOrgId.value)
      if (!found) setCurrentOrg(orgs[0].org_id)
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
