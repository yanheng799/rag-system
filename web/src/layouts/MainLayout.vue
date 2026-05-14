<template>
  <a-layout style="min-height: 100vh">
    <a-layout-header class="app-header">
      <div class="header-logo" @click="router.push('/datasets')">RAG 系统</div>
      <a-menu mode="horizontal" :selected-keys="[currentNav]" @click="onMenuClick">
        <a-menu-item key="datasets">
          <database-outlined />
          <span>知识库</span>
        </a-menu-item>
        <a-menu-item key="query">
          <message-outlined />
          <span>问答</span>
        </a-menu-item>
        <a-menu-item key="retrieve">
          <search-outlined />
          <span>检索</span>
        </a-menu-item>
      </a-menu>
    </a-layout-header>
    <a-layout-content>
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  DatabaseOutlined,
  MessageOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

const router = useRouter()
const route = useRoute()

const currentNav = computed(() => {
  const path = route.path
  if (path.startsWith('/query')) return 'query'
  if (path.startsWith('/retrieve')) return 'retrieve'
  return 'datasets'
})

const onMenuClick = ({ key }: { key: string }) => {
  router.push(`/${key}`)
}
</script>

<style scoped>
.app-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
  padding: 0 24px;
}

.header-logo {
  font-size: 18px;
  font-weight: 700;
  color: #1677ff;
  cursor: pointer;
  margin-right: 32px;
  white-space: nowrap;
}

.app-header :deep(.ant-menu) {
  line-height: 64px;
  border-bottom: none;
}
</style>
