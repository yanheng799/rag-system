import axios from 'axios'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

// 请求拦截：注入 Bearer token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 跳转登录
request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      const currentPath = window.location.pathname
      if (currentPath !== '/login' && currentPath !== '/register') {
        window.location.href = '/login'
      }
    }
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(msg))
  },
)

export default request
