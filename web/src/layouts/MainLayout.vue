<template>
  <a-layout style="min-height: 100vh">
    <header class="app-header">
      <router-link to="/datasets" class="header-brand">
        <svg class="brand-icon" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="32" height="32" rx="8" fill="rgba(255,255,255,0.15)"/>
          <path d="M9 7h7.2c2.8 0 5 1.4 5 4.2 0 1.8-1 3.2-2.6 3.9l3.4 9.9h-3.8l-3-7.6H12.2V25H9V7zm3.2 2.8v4.6h3.2c1.6 0 2.6-.9 2.6-2.3s-1-2.3-2.6-2.3h-3.2z" fill="white" fill-opacity="0.95"/>
          <circle cx="24" cy="8" r="3" fill="#f59e0b" fill-opacity="0.9"/>
        </svg>
        <span class="brand-text">RAG 系统</span>
      </router-link>

      <nav class="header-nav">
        <router-link
          v-for="item in navItems"
          :key="item.key"
          :to="item.to"
          class="nav-item"
          :class="{ active: currentNav === item.key }"
        >
          <component :is="item.icon" aria-hidden="true" class="nav-icon" />
          <span>{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="header-right">
        <div class="header-indicator"></div>
      </div>
    </header>
    <a-layout-content>
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRoute } from 'vue-router'
import {
  DatabaseOutlined,
  MessageOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'

interface NavItem {
  key: string
  to: string
  label: string
  icon: Component
}

const route = useRoute()

const navItems: NavItem[] = [
  { key: 'datasets', to: '/datasets', label: '知识库', icon: DatabaseOutlined },
  { key: 'query', to: '/query', label: '问答', icon: MessageOutlined },
  { key: 'retrieve', to: '/retrieve', label: '检索', icon: SearchOutlined },
]

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
  height: var(--layout-header-height);
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
  padding: 0 var(--space-8);
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 12px rgba(30, 27, 75, 0.2);
}

.header-brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  text-decoration: none;
  margin-right: var(--space-10);
}

.brand-icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
}

.brand-text {
  font-size: 17px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.01em;
  white-space: nowrap;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  color: #a5b4fc;
  text-decoration: none;
  font-size: var(--font-size-base);
  font-weight: 500;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.nav-item:hover {
  color: #e0e7ff;
  background: rgba(255, 255, 255, 0.08);
}

.nav-item.active {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.14);
  font-weight: 600;
}

.nav-icon {
  font-size: 16px;
}

.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
}

.header-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #34d399;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.5);
}

@media (max-width: 768px) {
  .app-header {
    padding: 0 var(--space-4);
  }
  .header-brand {
    margin-right: var(--space-4);
  }
  .nav-item span {
    display: none;
  }
}
</style>
