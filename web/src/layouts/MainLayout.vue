<template>
  <a-layout style="min-height: 100vh">
    <a-layout-header class="app-header">
      <router-link to="/datasets" class="header-logo">RAG 系统</router-link>
      <a-menu mode="horizontal" :selected-keys="[currentNav]">
        <a-menu-item key="datasets">
          <router-link to="/datasets" class="nav-link">
            <database-outlined aria-hidden="true" />
            <span>知识库</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="query">
          <router-link to="/query" class="nav-link">
            <message-outlined aria-hidden="true" />
            <span>问答</span>
          </router-link>
        </a-menu-item>
        <a-menu-item key="retrieve">
          <router-link to="/retrieve" class="nav-link">
            <search-outlined aria-hidden="true" />
            <span>检索</span>
          </router-link>
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
import { useRoute } from 'vue-router'
import {
  DatabaseOutlined,
  MessageOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

const route = useRoute()

const currentNav = computed(() => {
  const path = route.path
  if (path.startsWith('/query')) return 'query'
  if (path.startsWith('/retrieve')) return 'retrieve'
  return 'datasets'
})
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
  text-decoration: none;
}

.app-header :deep(.ant-menu) {
  line-height: 64px;
  border-bottom: none;
}

.nav-link {
  color: inherit;
  text-decoration: none;
}
</style>
