import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')

  const isLoggedIn = computed(() => !!user.value && !!accessToken.value)

  function setTokens(access, refresh) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function clearTokens() {
    accessToken.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function fetchMe() {
    if (!accessToken.value) return
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
    } catch {
      user.value = null
    }
  }

  async function logout() {
    try { await api.post('/auth/logout') } catch { /* ignore */ }
    clearTokens()
  }

  async function refreshAccessToken() {
    if (!refreshToken.value) return false
    try {
      const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken.value })
      setTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      clearTokens()
      return false
    }
  }

  // 初始化时加载用户信息
  if (accessToken.value) fetchMe()

  return {
    user, accessToken, refreshToken, isLoggedIn,
    setTokens, clearTokens, fetchMe, logout, refreshAccessToken
  }
})
