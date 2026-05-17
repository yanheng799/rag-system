import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: MainLayout,
      children: [
        { path: '', redirect: '/datasets' },
        { path: 'datasets', component: () => import('@/views/datasets/DatasetList.vue') },
        { path: 'datasets/:id', component: () => import('@/views/datasets/DatasetDetail.vue') },
        { path: 'query', component: () => import('@/views/query/QueryPage.vue') },
        { path: 'retrieve', component: () => import('@/views/retrieve/RetrievePage.vue') },
        { path: 'documents/:docId/chunks', component: () => import('@/views/chunks/ChunkList.vue') },
        { path: 'documents/:docId/viewer', component: () => import('@/views/documents/DocumentViewer.vue') },
        { path: 'chunks/:chunkId', component: () => import('@/views/chunks/ChunkDetail.vue') },
      ],
    },
  ],
})

export default router
