import { defineStore } from 'pinia'
import api from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('rk_token') || null,
    user: JSON.parse(localStorage.getItem('rk_user') || 'null'),
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    async login(username, password) {
      const form = new URLSearchParams({ username, password })
      const { data } = await api.post('/auth/login', form, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      })
      this.token = data.access_token
      this.user = { username: data.username }
      localStorage.setItem('rk_token', this.token)
      localStorage.setItem('rk_user', JSON.stringify(this.user))
      api.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
    },
    async register(username, password, email) {
      await api.post('/auth/register', { username, password, email })
    },
    logout() {
      this.token = null
      this.user = null
      localStorage.removeItem('rk_token')
      localStorage.removeItem('rk_user')
      delete api.defaults.headers.common['Authorization']
    },
    restoreToken() {
      if (this.token) {
        api.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
      }
    },
  }
})
