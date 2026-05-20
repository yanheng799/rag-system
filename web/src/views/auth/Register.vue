<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-header">
        <router-link to="/login" class="auth-logo">
          <svg viewBox="0 0 32 32" fill="none" width="40" height="40">
            <rect width="32" height="32" rx="8" fill="#312e81"/>
            <path d="M9 7h7.2c2.8 0 5 1.4 5 4.2 0 1.8-1 3.2-2.6 3.9l3.4 9.9h-3.8l-3-7.6H12.2V25H9V7zm3.2 2.8v4.6h3.2c1.6 0 2.6-.9 2.6-2.3s-1-2.3-2.6-2.3h-3.2z" fill="white"/>
          </svg>
          <span>RAG 系统</span>
        </router-link>
      </div>
      <h1 class="auth-title">注册</h1>
      <a-form :model="form" layout="vertical" @finish="handleRegister">
        <a-form-item name="username" :rules="[{ required: true, message: '请输入用户名' }, { min: 3, max: 64, message: '3-64 字符' }, { pattern: /^[a-zA-Z0-9_-]+$/, message: '仅字母数字下划线短横线' }]">
          <a-input v-model:value="form.username" placeholder="用户名" size="large" />
        </a-form-item>
        <a-form-item name="display_name">
          <a-input v-model:value="form.display_name" placeholder="显示名称（可选）" size="large" />
        </a-form-item>
        <a-form-item name="password" :rules="[{ required: true, message: '请输入密码' }, { min: 8, message: '最少 8 字符' }]">
          <a-input-password v-model:value="form.password" placeholder="密码" size="large" />
        </a-form-item>
        <a-form-item name="pw2" :rules="[{ required: true, message: '请确认密码' }, { validator: validatePw2 }]">
          <a-input-password v-model:value="form.password_confirm" placeholder="确认密码" size="large" />
        </a-form-item>
        <a-form-item>
          <a-button type="primary" html-type="submit" size="large" :loading="loading" block>注册</a-button>
        </a-form-item>
      </a-form>
      <div class="auth-footer">已有账号？<router-link to="/login">立即登录</router-link></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { register, login } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter(); const authStore = useAuthStore(); const loading = ref(false)
const form = reactive({ username: '', display_name: '', password: '', password_confirm: '' })

function validatePw2() {
  if (form.password !== form.password_confirm) return Promise.reject('两次密码不一致')
  return Promise.resolve()
}

async function handleRegister() {
  loading.value = true
  try {
    await register({ username: form.username, password: form.password, display_name: form.display_name || undefined })
    message.success('注册成功')
    const resp = await login({ username: form.username, password: form.password })
    authStore.setToken(resp.access_token)
    await authStore.fetchUser()
    router.push(authStore.myOrgs.length === 0 ? '/orgs' : '/datasets')
  } catch (err: any) { message.error(err.message || '注册失败') }
  finally { loading.value = false }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #f7f6f3 0%, #eef2ff 50%, #f7f6f3 100%); }
.auth-card { width: 420px; padding: 40px; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(30,27,75,0.08); }
.auth-header { text-align: center; margin-bottom: 24px; }
.auth-logo { display: inline-flex; align-items: center; gap: 10px; text-decoration: none; font-size: 20px; font-weight: 700; color: #1e1b4b; }
.auth-title { font-size: 24px; font-weight: 600; text-align: center; margin-bottom: 32px; color: #1e1b4b; }
.auth-footer { text-align: center; color: #6b7280; font-size: 14px; }
.auth-footer a { color: #312e81; font-weight: 500; }
</style>
