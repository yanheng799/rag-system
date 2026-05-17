<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
const themeConfig = {
  token: {
    colorPrimary: '#312e81',
    colorInfo: '#312e81',
    colorSuccess: '#059669',
    colorError: '#dc2626',
    colorWarning: '#d97706',
    borderRadius: 8,
    fontFamily: "'Outfit', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    colorBgContainer: '#ffffff',
    colorBgLayout: '#f7f6f3',
    colorBgElevated: '#ffffff',
    colorBorder: '#e5e4df',
    colorBorderSecondary: '#e5e4df',
    colorText: '#1e1b4b',
    colorTextSecondary: '#4b5563',
    colorTextTertiary: '#9ca3af',
    colorTextPlaceholder: '#d1d5db',
    controlHeight: 36,
    fontSize: 14,
  },
  components: {
    Layout: {
      headerBg: '#1e1b4b',
      headerHeight: 60,
      headerPadding: '0 24px',
    },
    Menu: {
      horizontalItemSelectedColor: '#ffffff',
      horizontalItemHoverColor: '#e0e7ff',
      horizontalItemColor: '#a5b4fc',
      itemBg: 'transparent',
      horizontalItemHoverBg: 'rgba(255,255,255,0.08)',
      horizontalItemSelectedBg: 'rgba(255,255,255,0.12)',
    },
    Button: {
      primaryShadow: '0 2px 6px rgba(49, 46, 129, 0.35)',
      defaultBorderColor: '#d1d0cb',
    },
    Card: {
      boxShadowTertiary: '0 1px 3px rgba(30,27,75,0.06), 0 1px 2px rgba(30,27,75,0.03)',
    },
    Table: {
      headerBg: '#f3f2ee',
      headerColor: '#1e1b4b',
      rowHoverBg: '#faf9f7',
      borderColor: '#e5e4df',
    },
    Input: {
      activeBorderColor: '#312e81',
      hoverBorderColor: '#6366f1',
    },
    Select: {
      optionSelectedBg: '#eef2ff',
    },
    Tag: {
      defaultBg: '#f3f2ee',
      defaultColor: '#1e1b4b',
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
    },
  },
}
</script>
