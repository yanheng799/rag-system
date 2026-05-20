import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 无需登录
    { path: '/login', component: () => import('@/views/auth/Login.vue') },
    { path: '/register', component: () => import('@/views/auth/Register.vue') },

    // 需要登录
    {
      path: '/',
      component: MainLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', redirect: '/datasets' },
        { path: 'datasets', component: () => import('@/views/datasets/DatasetList.vue') },
        { path: 'datasets/:id', component: () => import('@/views/datasets/DatasetDetail.vue') },
        { path: 'query', component: () => import('@/views/query/QueryPage.vue') },
        { path: 'retrieve', component: () => import('@/views/retrieve/RetrievePage.vue') },
        { path: 'orgs', component: () => import('@/views/orgs/OrgList.vue') },
        { path: 'orgs/:id', component: () => import('@/views/orgs/OrgDetail.vue') },
        { path: 'documents/:docId/chunks', component: () => import('@/views/chunks/ChunkList.vue') },
        { path: 'documents/:docId/viewer', component: () => import('@/views/documents/DocumentViewer.vue') },
        { path: 'chunks/:chunkId', component: () => import('@/views/chunks/ChunkDetail.vue') },
      ],
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const hasToken = !!localStorage.getItem('access_token')
  const requiresAuth = to.matched.some((r) => r.meta.requiresAuth)

  // 已登录用户访问登录/注册页 → 重定向到首页
  if ((to.path === '/login' || to.path === '/register') && hasToken) {
    return next('/datasets')
  }

  // 需要登录但无 token → 跳转登录
  if (requiresAuth && !hasToken) {
    return next({ path: '/login', query: { redirect: to.fullPath } })
  }

  next()
})

export default router
